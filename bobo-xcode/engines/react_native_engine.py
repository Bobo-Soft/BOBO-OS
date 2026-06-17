"""
React Native compilation engine for BoboXcode.
Wraps npm / npx react-native. iOS builds are finalized on the Mac cloud.
"""
import subprocess
import os
import shutil
from typing import Callable, Optional
from engines.swift_engine import BuildResult


class ReactNativeEngine:
    def __init__(self):
        self.npm = shutil.which("npm")
        self.npx = shutil.which("npx")
        self.node = shutil.which("node")

    def is_available(self) -> bool:
        return self.npm is not None and self.node is not None

    def version(self) -> str:
        if not self.node:
            return "Node.js not installed"
        try:
            nv = subprocess.run([self.node, "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
            return "Node %s" % nv
        except Exception:
            return "unknown"

    def install_deps(self, project_path: str, callback: Callable = None) -> BuildResult:
        """npm install (resolve node_modules)."""
        return self._run([self.npm, "install"], project_path, callback)

    def start_metro(self, project_path: str, callback: Callable = None) -> BuildResult:
        """Start the Metro bundler."""
        return self._run([self.npx, "react-native", "start"], project_path, callback)

    def run_ios(self, project_path: str, callback: Callable = None) -> BuildResult:
        """Build for iOS (assembled on the Mac via the Bridge)."""
        return self._run([self.npx, "react-native", "build-ios", "--mode", "Debug"],
                         project_path, callback)

    def run_android(self, project_path: str, callback: Callable = None) -> BuildResult:
        return self._run([self.npx, "react-native", "run-android"], project_path, callback)

    def test(self, project_path: str, callback: Callable = None) -> BuildResult:
        return self._run([self.npm, "test"], project_path, callback)

    def create_project(self, path: str, name: str) -> str:
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)
        if self.npx:
            subprocess.run([self.npx, "react-native@latest", "init", name],
                           cwd=parent, check=False)
        return path

    def _run(self, cmd: list, cwd: str, callback: Callable) -> BuildResult:
        if not cmd[0]:
            return BuildResult(False, "", "Node.js/npm not installed. "
                               "Install with a FULL build (BOBO_XCODE_SKIP_HEAVY=0).")
        out, errors = [], []
        try:
            p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
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
