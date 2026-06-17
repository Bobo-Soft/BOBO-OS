#!/usr/bin/env python3
# =============================================================================
# BoboMonitor - System Monitor / Task Manager pentru BOBO OS (APP 02)
# GTK4 + psutil. Tab-uri: Procese, Resurse (grafice live), Stocare, Retea.
# =============================================================================
import os
import sys
import time
import socket
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Gio  # noqa: E402

try:
    import psutil
except ImportError:
    psutil = None

APP_ID = "os.bobo.Monitor"
HISTORY_LEN = 60  # secunde afisate in grafice


class Graph(Gtk.DrawingArea):
    """Grafic scrolling simplu (ultimele HISTORY_LEN valori) desenat cu Cairo."""

    def __init__(self, color=(0.29, 0.62, 1.0), maximum=100.0, label=""):
        super().__init__()
        self.values = [0.0] * HISTORY_LEN
        self.color = color
        self.maximum = maximum
        self.label = label
        self.set_content_height(110)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, value):
        self.values.append(value)
        self.values = self.values[-HISTORY_LEN:]
        self.queue_draw()

    def _draw(self, area, cr, w, h, *args):
        cr.set_source_rgb(0.086, 0.13, 0.24)  # fundal card
        cr.rectangle(0, 0, w, h)
        cr.fill()
        # grila
        cr.set_source_rgba(1, 1, 1, 0.08)
        for i in range(1, 4):
            y = h * i / 4
            cr.move_to(0, y)
            cr.line_to(w, y)
        cr.stroke()
        # linia de date
        mx = max(self.maximum, max(self.values) or 1)
        n = len(self.values)
        cr.set_source_rgb(*self.color)
        cr.set_line_width(2)
        for i, v in enumerate(self.values):
            x = w * i / (n - 1)
            y = h - (v / mx) * h
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        # eticheta + valoare curenta
        cr.set_source_rgb(0.91, 0.92, 0.96)
        cr.move_to(8, 18)
        cr.show_text("%s  %.0f" % (self.label, self.values[-1]))


class BoboMonitorWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboMonitor")
        self.set_default_size(900, 640)
        self.refresh_interval = 1.0
        self.search_text = ""
        self.sort_col = "cpu"
        self.sort_desc = True
        self._public_ip = "..."

        self._build_ui()
        if psutil:
            psutil.cpu_percent(percpu=True)  # primul apel = baseline
            GLib.timeout_add(int(self.refresh_interval * 1000), self._refresh)
            threading.Thread(target=self._fetch_public_ip, daemon=True).start()
        else:
            self._no_psutil()

    def _build_ui(self):
        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.status_label = Gtk.Label(label="CPU --  RAM --  uptime --")
        header.set_title_widget(self.status_label)

        # selector interval refresh
        self.interval_combo = Gtk.DropDown.new_from_strings(["0.5s", "1s", "2s", "5s"])
        self.interval_combo.set_selected(1)
        self.interval_combo.connect("notify::selected", self._on_interval_changed)
        header.pack_end(self.interval_combo)

        notebook = Gtk.Notebook()
        self.set_child(notebook)
        notebook.append_page(self._build_proc_tab(), Gtk.Label(label="Procese"))
        notebook.append_page(self._build_res_tab(), Gtk.Label(label="Resurse"))
        notebook.append_page(self._build_storage_tab(), Gtk.Label(label="Stocare"))
        notebook.append_page(self._build_net_tab(), Gtk.Label(label="Retea"))

    # --------------------------------------------------------- tab Procese
    def _build_proc_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Cauta proces...")
        search.connect("search-changed", lambda e: self._set_search(e.get_text()))
        box.append(search)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        # coloane: PID, Nume, User, CPU%, RAM MB, Status, Nice
        self.store = Gtk.ListStore(int, str, str, float, float, str, int)
        self.tree = Gtk.TreeView(model=self.store)
        cols = [("PID", 0), ("Nume", 1), ("User", 2), ("CPU%", 3),
                ("RAM MB", 4), ("Status", 5), ("Nice", 6)]
        for title, idx in cols:
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=idx)
            col.set_sort_column_id(idx)
            col.set_resizable(True)
            self.tree.append_column(col)
        scroller.set_child(self.tree)
        box.append(scroller)

        # meniu click-dreapta
        gesture = Gtk.GestureClick()
        gesture.set_button(3)
        gesture.connect("pressed", self._on_proc_right_click)
        self.tree.add_controller(gesture)
        return box

    def _on_proc_right_click(self, gesture, n_press, x, y):
        path_info = self.tree.get_path_at_pos(int(x), int(y))
        if not path_info:
            return
        self.tree.get_selection().select_path(path_info[0])
        model, it = self.tree.get_selection().get_selected()
        if it is None:
            return
        pid = model.get_value(it, 0)
        menu = Gio.Menu()
        menu.append("Termina (SIGTERM)", "proc.kill")
        menu.append("Fortat (SIGKILL)", "proc.forcekill")
        menu.append("Schimba prioritate (renice)", "proc.renice")
        menu.append("Fisiere deschise", "proc.openfiles")
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(self.tree)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        self._ctx_pid = pid
        # actiuni
        ag = Gio.SimpleActionGroup()
        for name, fn in [("kill", lambda *a: self._kill(pid, 15)),
                         ("forcekill", lambda *a: self._kill(pid, 9)),
                         ("renice", lambda *a: self._renice(pid)),
                         ("openfiles", lambda *a: self._open_files(pid))]:
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", fn)
            ag.add_action(act)
        self.tree.insert_action_group("proc", ag)
        pop.popup()

    def _kill(self, pid, sig):
        try:
            psutil.Process(pid).send_signal(sig)
        except Exception as e:
            self._toast("Nu pot opri PID %s: %s" % (pid, e))

    def _renice(self, pid):
        dialog = Gtk.Window(title="Renice PID %s" % pid, transient_for=self, modal=True)
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12,
                    margin_bottom=12, margin_start=12, margin_end=12)
        spin = Gtk.SpinButton.new_with_range(-20, 19, 1)
        try:
            spin.set_value(psutil.Process(pid).nice())
        except Exception:
            pass
        apply_btn = Gtk.Button(label="Aplica")
        apply_btn.connect("clicked", lambda *a: (self._do_renice(pid, int(spin.get_value())), dialog.close()))
        b.append(Gtk.Label(label="Prioritate nice (-20 prioritar .. 19):"))
        b.append(spin)
        b.append(apply_btn)
        dialog.set_child(b)
        dialog.present()

    def _do_renice(self, pid, nice):
        try:
            psutil.Process(pid).nice(nice)
        except Exception as e:
            self._toast("renice esuat: %s" % e)

    def _open_files(self, pid):
        try:
            files = psutil.Process(pid).open_files()
            text = "\n".join(f.path for f in files) or "(niciun fisier)"
        except Exception as e:
            text = "Eroare: %s" % e
        dialog = Gtk.Window(title="Fisiere deschise PID %s" % pid, transient_for=self)
        dialog.set_default_size(560, 400)
        sw = Gtk.ScrolledWindow()
        tv = Gtk.TextView()
        tv.get_buffer().set_text(text)
        tv.set_editable(False)
        sw.set_child(tv)
        dialog.set_child(sw)
        dialog.present()

    # --------------------------------------------------------- tab Resurse
    def _build_res_tab(self):
        sw = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        self.cpu_graph = Graph(color=(0.29, 0.62, 1.0), label="CPU %")
        self.ram_graph = Graph(color=(0.4, 0.85, 0.5), label="RAM %")
        self.swap_graph = Graph(color=(1.0, 0.7, 0.33), label="Swap %")
        self.disk_graph = Graph(color=(0.7, 0.5, 1.0), maximum=50, label="Disk MB/s")
        self.net_graph = Graph(color=(0.4, 0.85, 0.95), maximum=1000, label="Net KB/s")
        for g in (self.cpu_graph, self.ram_graph, self.swap_graph, self.disk_graph, self.net_graph):
            box.append(g)
        sw.set_child(box)
        self._last_disk = None
        self._last_net = None
        return sw

    # --------------------------------------------------------- tab Stocare
    def _build_storage_tab(self):
        sw = Gtk.ScrolledWindow()
        self.storage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.storage_box.set_margin_top(8)
        self.storage_box.set_margin_start(8)
        self.storage_box.set_margin_end(8)
        sw.set_child(self.storage_box)
        return sw

    def _refresh_storage(self):
        child = self.storage_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.storage_box.remove(child)
            child = nxt
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row.add_css_class("card")
            row.set_margin_bottom(4)
            lbl = Gtk.Label(xalign=0)
            lbl.set_markup("<b>%s</b>  %s  (%s)" % (part.device, part.mountpoint, part.fstype))
            bar = Gtk.ProgressBar()
            bar.set_fraction(usage.percent / 100.0)
            bar.set_text("%.1f / %.1f GB  (%.0f%%)" % (
                usage.used / 1e9, usage.total / 1e9, usage.percent))
            bar.set_show_text(True)
            row.append(lbl)
            row.append(bar)
            self.storage_box.append(row)

    # --------------------------------------------------------- tab Retea
    def _build_net_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        self.net_info = Gtk.Label(xalign=0)
        box.append(self.net_info)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        self.conn_store = Gtk.ListStore(str, str, str, str)
        tv = Gtk.TreeView(model=self.conn_store)
        for i, t in enumerate(["Proto", "Local", "Remote", "Status"]):
            tv.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        sw.set_child(tv)
        box.append(sw)
        return box

    def _refresh_net(self):
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "?"
        self.net_info.set_markup("IP local: <b>%s</b>    IP public: <b>%s</b>" % (local_ip, self._public_ip))
        self.conn_store.clear()
        try:
            for c in psutil.net_connections(kind="inet")[:200]:
                laddr = "%s:%s" % (c.laddr.ip, c.laddr.port) if c.laddr else "-"
                raddr = "%s:%s" % (c.raddr.ip, c.raddr.port) if c.raddr else "-"
                proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
                self.conn_store.append([proto, laddr, raddr, c.status])
        except Exception:
            pass

    def _fetch_public_ip(self):
        try:
            import urllib.request
            self._public_ip = urllib.request.urlopen("https://api.ipify.org", timeout=5).read().decode()
        except Exception:
            self._public_ip = "indisponibil"

    # --------------------------------------------------------- refresh loop
    def _refresh(self):
        if not psutil:
            return False
        # bara de sus
        cpu = psutil.cpu_percent()
        vm = psutil.virtual_memory()
        up = time.time() - psutil.boot_time()
        temp = ""
        try:
            temps = psutil.sensors_temperatures()
            for vals in temps.values():
                if vals:
                    temp = "  %.0f°C" % vals[0].current
                    break
        except Exception:
            pass
        self.status_label.set_text("CPU %.0f%%  RAM %.0f%%%s  uptime %dh%02dm" % (
            cpu, vm.percent, temp, int(up // 3600), int((up % 3600) // 60)))

        # grafice
        self.cpu_graph.push(cpu)
        self.ram_graph.push(vm.percent)
        self.swap_graph.push(psutil.swap_memory().percent)
        dio = psutil.disk_io_counters()
        if dio and self._last_disk:
            mbps = (dio.read_bytes + dio.write_bytes - self._last_disk) / 1e6 / self.refresh_interval
            self.disk_graph.push(max(0, mbps))
        self._last_disk = (dio.read_bytes + dio.write_bytes) if dio else 0
        nio = psutil.net_io_counters()
        if nio and self._last_net:
            kbps = (nio.bytes_sent + nio.bytes_recv - self._last_net) / 1e3 / self.refresh_interval
            self.net_graph.push(max(0, kbps))
        self._last_net = (nio.bytes_sent + nio.bytes_recv) if nio else 0

        # lista procese
        self._refresh_processes()
        self._refresh_storage()
        self._refresh_net()
        return True

    def _refresh_processes(self):
        self.store.clear()
        procs = []
        for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "status", "nice"]):
            try:
                info = p.info
                if self.search_text and self.search_text.lower() not in (info["name"] or "").lower():
                    continue
                ram = info["memory_info"].rss / 1e6 if info["memory_info"] else 0
                procs.append([info["pid"], info["name"] or "?", info["username"] or "?",
                              round(info["cpu_percent"] or 0, 1), round(ram, 1),
                              info["status"] or "?", info["nice"] or 0])
            except Exception:
                continue
        procs.sort(key=lambda r: r[3], reverse=True)
        for row in procs[:400]:
            self.store.append(row)

    # --------------------------------------------------------- helpers
    def _set_search(self, text):
        self.search_text = text

    def _on_interval_changed(self, combo, _):
        self.refresh_interval = [0.5, 1.0, 2.0, 5.0][combo.get_selected()]

    def _toast(self, text):
        print("[bobo-monitor] %s" % text)

    def _no_psutil(self):
        self.status_label.set_text("psutil lipseste - instaleaza python3-psutil")


class BoboMonitorApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboMonitorWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboMonitor 1.0.0 (BOBO OS)")
        return 0
    return BoboMonitorApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
