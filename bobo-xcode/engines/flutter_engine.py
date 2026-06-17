"""
Flutter compilation engine for BoboXcode.
Wraps the `flutter` CLI for cross-platform builds (incl. iOS targets, which
are assembled on the Mac cloud via the Bridge).
"""
import subprocess
import os
import shutil
from typing import Callable, Optional
from engines.swift_engine import BuildResult


class FlutterEngine:
    def __init__(self):
        self.flutter_bin = self._find_flutter()

    def _find_flutter(self) -> Optional[str]:
        for cand in [shutil.which("flutter"), "/opt/flutter/bin/flutter",
                     os.path.expanduser("~/flutter/bin/flutter")]:
            if cand and os.path.exists(cand):
                return cand
        return None

    def is_available(self) -> bool:
        return self.flutter_bin is not None

    def version(self) -> str:
        if not self.flutter_bin:
            return "Flutter SDK not installed"
        try:
            return subprocess.run([self.flutter_bin, "--version"],
                                  capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        except Exception:
            return "unknown"

    def pub_get(self, project_path: str, callback: Callable = None) -> BuildResult:
        """Resolve Dart/Flutter dependencies (pubspec.yaml)."""
        return self._run(["pub", "get"], project_path, callback)

    def build(self, project_path: str, target: str = "linux",
              callback: Callable = None) -> BuildResult:
        """
        Build the Flutter app. target in {linux, apk, ios, web}.
        'ios' produces a build that the Bridge finalizes on macOS.
        """
        args = ["build", target, "--debug"] if target == "linux" else ["build", target]
        return self._run(args, project_path, callback)

    def run(self, project_path: str, device: str = "linux",
            callback: Callable = None) -> BuildResult:
        return self._run(["run", "-d", device], project_path, callback)

    def test(self, project_path: str, callback: Callable = None) -> BuildResult:
        return self._run(["test"], project_path, callback)

    def create_project(self, path: str, name: str) -> str:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if self.flutter_bin:
            subprocess.run([self.flutter_bin, "create", "--project-name", name, path],
                           check=False)
        return path

    def _run(self, args: list, cwd: str, callback: Callable) -> BuildResult:
        if not self.flutter_bin:
            return BuildResult(False, "", "Flutter SDK not installed. "
                               "Install with: bobo-xcode --install-flutter")
        out, errors = [], []
        try:
            p = subprocess.Popen([self.flutter_bin] + args, cwd=cwd,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1)
        except FileNotFoundError as e:
            return BuildResult(False, "", str(e))
        for line in p.stdout:
            out.append(line)
            if "error" in line.lower():
                errors.append(line)
            if callback:
                callback(line)
        p.wait()
        return BuildResult(p.returncode == 0, "".join(out), "".join(errors))
