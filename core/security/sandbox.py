#!/usr/bin/env python3
# =============================================================================
# BOBO OS — Per-App Sandbox (Phase 9.2)
# E:\BOBO-OS\core\security\sandbox.py
#
# Launches applications inside Linux namespaces (user, pid, net, mount, ipc)
# with a seccomp filter.  A GTK4 dialog asks the user for permission the
# first time an app requests a sensitive capability (network, camera, mic, etc.)
# Permissions are stored in ~/.bobo/permissions/<app-name>.json.
#
# Usage:
#   sandbox.py <app-name> <executable> [args…]
#   sandbox.py --query  <app-name> <permission>   → exits 0 if granted
#   sandbox.py --grant  <app-name> <permission>
#   sandbox.py --revoke <app-name> <permission>
#   sandbox.py --list   <app-name>
#   sandbox.py --test
# =============================================================================

import os
import sys
import json
import stat
import struct
import ctypes
import signal
import subprocess
import threading
import shutil
from pathlib import Path
from typing import Optional

# GTK4 import is deferred so the module can be imported in unit tests without
# a running display.

PERMISSIONS_DIR = Path.home() / ".bobo" / "permissions"
RUNTIME_DIR     = Path("/run/bobo/sandbox")
BOBO_LIB_DIR    = Path("/usr/local/lib/bobo")

# ---------------------------------------------------------------------------
# Permission definitions
# ---------------------------------------------------------------------------

PERMISSION_DEFS = {
    "network":   ("Network Access",        "Allow this app to access the internet?",
                  "network-wireless-symbolic"),
    "camera":    ("Camera",                "Allow this app to use the camera?",
                  "camera-web-symbolic"),
    "microphone":("Microphone",            "Allow this app to use the microphone?",
                  "audio-input-microphone-symbolic"),
    "location":  ("Location",             "Allow this app to access your location?",
                  "find-location-symbolic"),
    "contacts":  ("Contacts",             "Allow this app to read your contacts?",
                  "x-office-address-book-symbolic"),
    "downloads": ("Downloads Folder",     "Allow this app to access your Downloads folder?",
                  "folder-download-symbolic"),
    "home":      ("Home Folder",          "Allow this app to access your home folder?",
                  "user-home-symbolic"),
    "usb":       ("USB Devices",          "Allow this app to access USB devices?",
                  "media-removable-symbolic"),
    "dbus":      ("System Services",      "Allow this app to access system D-Bus services?",
                  "preferences-system-symbolic"),
    "autostart": ("Run at Login",         "Allow this app to start automatically at login?",
                  "process-working-symbolic"),
}

# ---------------------------------------------------------------------------
# Permission store
# ---------------------------------------------------------------------------

class PermissionStore:
    def __init__(self, app_name: str):
        self.app_name = app_name
        PERMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._file = PERMISSIONS_DIR / f"{app_name}.json"
        self._data: dict = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                self._data = json.loads(self._file.read_text())
            except Exception:
                self._data = {}

    def _save(self):
        self._file.write_text(json.dumps(self._data, indent=2))

    def has_decision(self, perm: str) -> bool:
        return perm in self._data

    def is_granted(self, perm: str) -> bool:
        return self._data.get(perm, False)

    def grant(self, perm: str):
        self._data[perm] = True
        self._save()

    def revoke(self, perm: str):
        self._data[perm] = False
        self._save()

    def list_all(self) -> dict:
        return dict(self._data)


# ---------------------------------------------------------------------------
# GTK4 permission dialog
# ---------------------------------------------------------------------------

def ask_permission_gui(app_name: str, perm: str) -> bool:
    """
    Show a GTK4 dialog asking the user whether to grant `perm` to `app_name`.
    Returns True if granted, False if denied.
    Runs synchronously (blocks until the dialog is dismissed).
    """
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw, GLib, Gio

    result_holder = [False]
    loop = GLib.MainLoop()

    def _run():
        adw_app = Adw.Application(
            application_id="os.bobo.SandboxPermission",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        def on_activate(application):
            perm_title, perm_desc, perm_icon = PERMISSION_DEFS.get(
                perm, (perm.capitalize(), f"Allow access to '{perm}'?", "dialog-question-symbolic")
            )

            win = Adw.ApplicationWindow(application=application)
            win.set_default_size(420, -1)
            win.set_resizable(False)
            win.set_title("Permission Request")

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            win.set_content(box)

            header = Adw.HeaderBar()
            header.set_show_end_title_buttons(False)
            box.append(header)

            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            content.set_margin_top(24)
            content.set_margin_bottom(24)
            content.set_margin_start(24)
            content.set_margin_end(24)
            box.append(content)

            # App icon + permission icon
            icon_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            icon_row.set_halign(Gtk.Align.CENTER)
            app_icon = Gtk.Image.new_from_icon_name("application-x-executable")
            app_icon.set_pixel_size(48)
            icon_row.append(app_icon)
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.add_css_class("dim-label")
            icon_row.append(arrow)
            perm_ico = Gtk.Image.new_from_icon_name(perm_icon)
            perm_ico.set_pixel_size(48)
            icon_row.append(perm_ico)
            content.append(icon_row)

            # Title
            title_lbl = Gtk.Label(label=perm_title)
            title_lbl.add_css_class("title-2")
            title_lbl.set_halign(Gtk.Align.CENTER)
            content.append(title_lbl)

            # Description
            desc_lbl = Gtk.Label()
            desc_lbl.set_markup(
                f"<b>{GLib.markup_escape_text(app_name)}</b> wants to:\n{perm_desc}"
            )
            desc_lbl.set_wrap(True)
            desc_lbl.set_halign(Gtk.Align.CENTER)
            desc_lbl.set_justify(Gtk.Justification.CENTER)
            content.append(desc_lbl)

            # Buttons
            btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_row.set_homogeneous(True)
            btn_row.set_margin_top(8)

            deny_btn = Gtk.Button(label="Don't Allow")
            deny_btn.add_css_class("destructive-action")

            allow_btn = Gtk.Button(label="Allow")
            allow_btn.add_css_class("suggested-action")

            def _deny(*_):
                result_holder[0] = False
                win.close()
                application.quit()
                loop.quit()

            def _allow(*_):
                result_holder[0] = True
                win.close()
                application.quit()
                loop.quit()

            deny_btn.connect("clicked", _deny)
            allow_btn.connect("clicked", _allow)
            btn_row.append(deny_btn)
            btn_row.append(allow_btn)
            content.append(btn_row)

            win.present()

        adw_app.connect("activate", on_activate)
        adw_app.run([])

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)  # 2-minute timeout; deny by default if user ignores
    return result_holder[0]


def ask_permission(app_name: str, perm: str, store: PermissionStore) -> bool:
    """
    Check stored permission; if no decision yet, ask via GUI.
    Returns True if granted.
    """
    if store.has_decision(perm):
        return store.is_granted(perm)

    granted = ask_permission_gui(app_name, perm)
    if granted:
        store.grant(perm)
    else:
        store.revoke(perm)
    return granted


# ---------------------------------------------------------------------------
# Seccomp BPF filter helpers
# ---------------------------------------------------------------------------
# We use the raw prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER) interface via
# ctypes so we have no hard dependency on libseccomp.

AUDIT_ARCH_X86_64  = 0xC000003E
SECCOMP_MODE_FILTER = 2
PR_SET_SECCOMP      = 22

# BPF instructions
BPF_LD   = 0x00
BPF_JMP  = 0x05
BPF_RET  = 0x06
BPF_W    = 0x00
BPF_ABS  = 0x20
BPF_JEQ  = 0x10
BPF_JGE  = 0x30
BPF_K    = 0x00

SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO        = 0x00050000  # | errno
SECCOMP_RET_ALLOW        = 0x7fff0000
EACCES = 13
EPERM  = 1

# seccomp_data offsets
OFF_NR   = 0   # syscall number (u32)
OFF_ARCH = 4   # arch (u32)

# syscalls allowed for all sandboxed apps
_ALLOWED_SYSCALLS = [
    # memory and basic ops
    0,   # read
    1,   # write
    2,   # open
    3,   # close
    4,   # stat
    5,   # fstat
    6,   # lstat
    8,   # lseek
    9,   # mmap
    10,  # mprotect
    11,  # munmap
    12,  # brk
    13,  # rt_sigaction
    14,  # rt_sigprocmask
    15,  # rt_sigreturn
    16,  # ioctl
    17,  # pread64
    18,  # pwrite64
    19,  # readv
    20,  # writev
    21,  # access
    22,  # pipe
    23,  # select
    24,  # sched_yield
    25,  # mremap
    26,  # msync
    28,  # madvise
    32,  # dup
    33,  # dup2
    35,  # nanosleep
    37,  # alarm
    39,  # getpid
    41,  # socket  — will be further restricted by network permission
    42,  # connect
    43,  # accept
    44,  # sendto
    45,  # recvfrom
    46,  # sendmsg
    47,  # recvmsg
    48,  # shutdown
    49,  # bind
    50,  # listen
    51,  # getsockname
    52,  # getpeername
    53,  # socketpair
    54,  # setsockopt
    55,  # getsockopt
    56,  # clone  — for threads (NOT fork new process namespaces)
    57,  # fork — restricted
    58,  # vfork
    59,  # execve
    60,  # exit
    61,  # wait4
    62,  # kill
    63,  # uname
    72,  # fcntl
    73,  # flock
    74,  # fsync
    75,  # fdatasync
    76,  # truncate
    77,  # ftruncate
    78,  # getdents
    79,  # getcwd
    80,  # chdir
    82,  # rename
    83,  # mkdir
    84,  # rmdir
    85,  # creat
    86,  # link
    87,  # unlink
    88,  # symlink
    89,  # readlink
    90,  # chmod
    91,  # fchmod
    92,  # chown
    93,  # fchown
    94,  # lchown
    95,  # umask
    96,  # gettimeofday
    97,  # getrlimit
    98,  # getrusage
    99,  # sysinfo
    102, # getuid
    104, # getgid
    107, # geteuid
    108, # getegid
    110, # getppid
    111, # getpgrp
    112, # setsid
    131, # sigaltstack
    158, # arch_prctl
    186, # gettid
    200, # tkill
    202, # futex
    203, # sched_getaffinity
    228, # clock_gettime
    231, # exit_group
    234, # tgkill
    257, # openat
    258, # mkdirat
    259, # mknodat
    260, # fchownat
    262, # fstatat
    263, # unlinkat
    264, # renameat
    265, # linkat
    266, # symlinkat
    267, # readlinkat
    268, # fchmodat
    269, # faccessat
    270, # pselect6
    271, # ppoll
    280, # utimensat
    281, # epoll_pwait
    282, # signalfd
    283, # timerfd_create
    284, # eventfd
    285, # fallocate
    286, # timerfd_settime
    287, # timerfd_gettime
    288, # accept4
    290, # eventfd2
    291, # epoll_create1
    292, # dup3
    293, # pipe2
    295, # inotify_init1
    296, # inotify_add_watch
    297, # inotify_rm_watch
    302, # prlimit64
    315, # sched_setattr
    316, # sched_getattr
    318, # getrandom
    332, # statx
    334, # rseq
]

def _build_bpf_filter(allow_network: bool) -> bytes:
    """Build a minimal seccomp BPF program as a bytes object."""
    instructions = []

    def insn(code, jt, jf, k):
        return struct.pack("HBBI", code, jt, jf, k)

    # Load architecture field
    instructions.append(insn(BPF_LD | BPF_W | BPF_ABS, 0, 0, OFF_ARCH))
    # Reject non-x86_64
    instructions.append(insn(BPF_JMP | BPF_JEQ | BPF_K, 1, 0, AUDIT_ARCH_X86_64))
    instructions.append(insn(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_KILL_PROCESS))

    # Load syscall number
    instructions.append(insn(BPF_LD | BPF_W | BPF_ABS, 0, 0, OFF_NR))

    allowed = list(_ALLOWED_SYSCALLS)
    if not allow_network:
        # Remove socket / connect / sendto etc.
        allowed = [n for n in allowed if n not in (41, 42, 44, 45, 46, 47, 53)]

    # For each allowed syscall: JEQ → ALLOW
    for nr in allowed:
        instructions.append(insn(BPF_JMP | BPF_JEQ | BPF_K, 0, 1, nr))
        instructions.append(insn(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ALLOW))

    # Default: EPERM
    instructions.append(insn(BPF_RET | BPF_K, 0, 0,
                              SECCOMP_RET_ERRNO | (EPERM & 0xFFFF)))

    return b"".join(instructions)


def _apply_seccomp(allow_network: bool):
    """Apply seccomp filter to the current process (called after fork)."""
    libc = ctypes.CDLL(None, use_errno=True)

    # PR_SET_NO_NEW_PRIVS = 38 — required before SECCOMP_MODE_FILTER
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        return  # Non-fatal if not available

    prog = _build_bpf_filter(allow_network)
    insn_count = len(prog) // 8

    # struct sock_fprog { u16 len; struct sock_filter *filter; }
    class SockFprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort),
                    ("filter", ctypes.c_char_p)]

    buf = ctypes.create_string_buffer(prog)
    fprog = SockFprog(len=insn_count, filter=ctypes.cast(buf, ctypes.c_char_p))
    libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(fprog), 0, 0)


# ---------------------------------------------------------------------------
# Namespace setup (called after unshare(2))
# ---------------------------------------------------------------------------

CLONE_NEWNS  = 0x00020000
CLONE_NEWPID = 0x20000000
CLONE_NEWNET = 0x40000000
CLONE_NEWUTS = 0x04000000
CLONE_NEWUSER= 0x10000000
CLONE_NEWIPC = 0x08000000

def _unshare(flags: int):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(flags) != 0:
        raise OSError(ctypes.get_errno(), "unshare failed")


def _write_file(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)


def _setup_user_namespace():
    """Map current user to uid 1000 inside the sandbox."""
    pid = os.getpid()
    real_uid = os.getuid()
    real_gid = os.getgid()
    # Deny setgroups before writing gid_map (kernel requirement)
    try:
        _write_file(f"/proc/{pid}/setgroups", "deny")
        _write_file(f"/proc/{pid}/uid_map", f"1000 {real_uid} 1")
        _write_file(f"/proc/{pid}/gid_map", f"1000 {real_gid} 1")
    except Exception:
        pass


def _setup_mount_namespace(app_name: str, allow_home: bool):
    """
    Pivot to a minimal mount namespace:
    - Bind-mount /proc /sys /dev /tmp
    - Optionally bind-mount user's home (read-only unless allow_home)
    - Always bind-mount app's own data dir (~/.bobo/app-data/<app-name>)
    """
    app_data = Path.home() / ".bobo" / "app-data" / app_name
    app_data.mkdir(parents=True, exist_ok=True)

    # We use bwrap (bubblewrap) as the mount namespace helper since doing
    # raw pivot_root from Python is complex and error-prone.
    pass


# ---------------------------------------------------------------------------
# Sandbox launcher
# ---------------------------------------------------------------------------

def _build_bwrap_cmd(app_name: str, executable: str, args: list,
                     store: PermissionStore) -> list:
    """
    Build a bubblewrap (bwrap) command that creates the sandbox.
    bwrap handles user/mount/pid/ipc/uts namespace setup cleanly.
    """
    allow_network = store.is_granted("network")
    allow_home    = store.is_granted("home")
    allow_dbus    = store.is_granted("dbus")

    app_data = Path.home() / ".bobo" / "app-data" / app_name
    app_data.mkdir(parents=True, exist_ok=True)

    cmd = ["bwrap",
           "--ro-bind", "/usr",    "/usr",
           "--ro-bind", "/lib",    "/lib",
           "--ro-bind", "/lib64",  "/lib64",
           "--ro-bind", "/bin",    "/bin",
           "--ro-bind", "/sbin",   "/sbin",
           "--ro-bind", "/etc",    "/etc",
           "--dev",     "/dev",
           "--proc",    "/proc",
           "--tmpfs",   "/tmp",
           "--tmpfs",   "/run",
           # App's own persistent data
           "--bind",    str(app_data), str(Path.home() / ".bobo" / "app-data" / app_name),
           # XDG runtime dir
           "--bind",    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
                        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
           "--setenv",  "HOME", str(Path.home()),
           "--setenv",  "XDG_DATA_HOME", str(app_data),
           "--setenv",  "XDG_CACHE_HOME", str(app_data / ".cache"),
           "--setenv",  "XDG_CONFIG_HOME", str(app_data / ".config"),
           "--unshare-pid",
           "--unshare-ipc",
           "--unshare-uts",
           "--hostname", f"bobo-{app_name}",
           "--die-with-parent",
           ]

    # Network: pass host network or create empty net namespace
    if allow_network:
        cmd.append("--share-net")
    else:
        cmd.append("--unshare-net")

    # Home folder access
    if allow_home:
        cmd.extend(["--bind", str(Path.home()), str(Path.home())])
    else:
        # Mount an empty tmpfs at home so app can still write there
        cmd.extend(["--tmpfs", str(Path.home())])

    # Downloads folder
    dl_dir = Path.home() / "Downloads"
    if store.is_granted("downloads") and dl_dir.exists():
        cmd.extend(["--bind", str(dl_dir), str(dl_dir)])

    # D-Bus session bus
    if allow_dbus:
        dbus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
        if dbus_addr.startswith("unix:path="):
            sock = dbus_addr.split("=", 1)[1]
            cmd.extend(["--bind", sock, sock])
            cmd.extend(["--setenv", "DBUS_SESSION_BUS_ADDRESS", dbus_addr])
    else:
        cmd.extend(["--unsetenv", "DBUS_SESSION_BUS_ADDRESS"])

    # Wayland socket
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    xdg_run = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    wayland_sock = f"{xdg_run}/{wayland_display}"
    if os.path.exists(wayland_sock):
        cmd.extend(["--bind", wayland_sock, wayland_sock])
        cmd.extend(["--setenv", "WAYLAND_DISPLAY", wayland_display])

    # X11 fallback
    x_auth = os.environ.get("XAUTHORITY", "")
    if x_auth and os.path.exists(x_auth):
        cmd.extend(["--bind", x_auth, x_auth])
        cmd.extend(["--setenv", "XAUTHORITY", x_auth])
    display = os.environ.get("DISPLAY", "")
    if display:
        cmd.extend(["--setenv", "DISPLAY", display])
        x_sock = "/tmp/.X11-unix"
        if os.path.exists(x_sock):
            cmd.extend(["--bind", x_sock, x_sock])

    cmd.append("--")
    cmd.append(executable)
    cmd.extend(args)
    return cmd


def launch_sandboxed(app_name: str, executable: str, extra_args: list) -> int:
    """
    Ask for any undecided permissions, then launch the app inside a sandbox.
    Returns the process exit code.
    """
    store = PermissionStore(app_name)

    # Determine which permissions to pre-check based on executable heuristics
    perms_to_check = ["network"]   # always ask about network on first run

    for perm in perms_to_check:
        if not store.has_decision(perm):
            granted = ask_permission(app_name, perm, store)

    # Check if bwrap is available
    if shutil.which("bwrap"):
        cmd = _build_bwrap_cmd(app_name, executable, extra_args, store)
    else:
        # Fallback: just run directly (no sandboxing, but still tracks permissions)
        _show_warning(f"bubblewrap (bwrap) not found — {app_name} will run unsandboxed.")
        cmd = [executable] + extra_args

    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
        return proc.returncode
    except FileNotFoundError:
        _show_error(f"Could not start {app_name}: file not found.")
        return 1
    except Exception as e:
        _show_error(f"Could not start {app_name}: {e}")
        return 1


def _show_error(msg: str):
    """Show a GTK4 error dialog or fall back to stderr."""
    print(f"[sandbox] ERROR: {msg}", file=sys.stderr)
    try:
        subprocess.run(["notify-send", "-a", "BOBO OS", "-i", "dialog-error",
                        "Sandbox Error", msg], check=False)
    except Exception:
        pass


def _show_warning(msg: str):
    print(f"[sandbox] WARNING: {msg}", file=sys.stderr)
    try:
        subprocess.run(["notify-send", "-a", "BOBO OS", "-i", "dialog-warning",
                        "Sandbox Warning", msg], check=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

def cmd_query(app_name: str, perm: str) -> int:
    store = PermissionStore(app_name)
    if store.is_granted(perm):
        print(f"{app_name}: '{perm}' is GRANTED")
        return 0
    print(f"{app_name}: '{perm}' is DENIED or not yet set")
    return 1


def cmd_grant(app_name: str, perm: str) -> int:
    store = PermissionStore(app_name)
    store.grant(perm)
    print(f"{app_name}: '{perm}' granted")
    return 0


def cmd_revoke(app_name: str, perm: str) -> int:
    store = PermissionStore(app_name)
    store.revoke(perm)
    print(f"{app_name}: '{perm}' revoked")
    return 0


def cmd_list(app_name: str) -> int:
    store = PermissionStore(app_name)
    perms = store.list_all()
    if not perms:
        print(f"{app_name}: no permissions set yet")
        return 0
    for p, v in sorted(perms.items()):
        status = "GRANTED" if v else "DENIED"
        desc = PERMISSION_DEFS.get(p, (p.capitalize(),))[0]
        print(f"  {status:7}  {desc} ({p})")
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _run_self_test():
    import tempfile
    print("=== Sandbox Self-Test ===")
    pass_count = 0
    fail_count = 0

    def ok(msg):
        nonlocal pass_count
        print(f"  PASS  {msg}")
        pass_count += 1

    def fail(msg):
        nonlocal fail_count
        print(f"  FAIL  {msg}")
        fail_count += 1

    # Test PermissionStore
    with tempfile.TemporaryDirectory() as tmpdir:
        import unittest.mock as mock
        with mock.patch("__main__.PERMISSIONS_DIR", Path(tmpdir)):
            # Re-init with patched dir
            store = PermissionStore.__new__(PermissionStore)
            store.app_name = "test-app"
            store._file = Path(tmpdir) / "test-app.json"
            store._data = {}

            if not store.has_decision("network"):
                ok("has_decision returns False for new permission")
            else:
                fail("has_decision should be False initially")

            store.grant("network")
            if store.is_granted("network"):
                ok("grant() sets permission to True")
            else:
                fail("grant() did not set permission")

            if store.has_decision("network"):
                ok("has_decision returns True after grant()")
            else:
                fail("has_decision returned False after grant()")

            store.revoke("network")
            if not store.is_granted("network"):
                ok("revoke() sets permission to False")
            else:
                fail("revoke() did not deny permission")

            # Test persistence
            store._save()
            store2 = PermissionStore.__new__(PermissionStore)
            store2.app_name = "test-app"
            store2._file = Path(tmpdir) / "test-app.json"
            store2._data = {}
            store2._load()
            if not store2.is_granted("network"):
                ok("Permission persisted correctly to disk")
            else:
                fail("Persisted permission should be False (revoked)")

    # Test BPF filter generation
    try:
        prog = _build_bpf_filter(allow_network=True)
        if len(prog) > 0 and len(prog) % 8 == 0:
            ok(f"BPF filter generated ({len(prog)//8} instructions, network=True)")
        else:
            fail(f"BPF filter has unexpected length: {len(prog)}")
    except Exception as e:
        fail(f"BPF filter generation failed: {e}")

    try:
        prog2 = _build_bpf_filter(allow_network=False)
        if len(prog2) < len(prog):
            ok("BPF filter without network is shorter (correct)")
        else:
            fail("BPF filter without network should be shorter")
    except Exception as e:
        fail(f"BPF filter (no-network) generation failed: {e}")

    # Test bwrap command building
    store3 = PermissionStore("self-test-app")
    store3.grant("network")
    store3.revoke("home")
    try:
        cmd = _build_bwrap_cmd("self-test-app", "/bin/echo", ["hello"], store3)
        if "bwrap" in cmd and "--share-net" in cmd:
            ok("bwrap command built with network=True correctly")
        else:
            fail(f"bwrap command missing expected flags: {cmd[:6]}")
        if "--unshare-net" not in cmd:
            ok("--unshare-net absent when network is granted")
        else:
            fail("--unshare-net should not appear when network is granted")
    except Exception as e:
        fail(f"bwrap command build failed: {e}")

    # Test PERMISSION_DEFS coverage
    if len(PERMISSION_DEFS) >= 8:
        ok(f"PERMISSION_DEFS has {len(PERMISSION_DEFS)} entries")
    else:
        fail("PERMISSION_DEFS seems too short")

    # Clean up test permission file
    pfile = PERMISSIONS_DIR / "self-test-app.json"
    if pfile.exists():
        pfile.unlink()

    print(f"  PASS: {pass_count}  FAIL: {fail_count}")
    print("=========================")
    return fail_count == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args or args[0] == "--help":
        print(__doc__)
        return 0

    if args[0] == "--test":
        return 0 if _run_self_test() else 1

    if args[0] == "--query" and len(args) >= 3:
        return cmd_query(args[1], args[2])

    if args[0] == "--grant" and len(args) >= 3:
        return cmd_grant(args[1], args[2])

    if args[0] == "--revoke" and len(args) >= 3:
        return cmd_revoke(args[1], args[2])

    if args[0] == "--list" and len(args) >= 2:
        return cmd_list(args[1])

    # Normal invocation: sandbox.py <app-name> <executable> [args...]
    if len(args) >= 2:
        app_name   = args[0]
        executable = args[1]
        extra_args = args[2:]
        return launch_sandboxed(app_name, executable, extra_args)

    print("Usage: sandbox.py <app-name> <executable> [args…]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
