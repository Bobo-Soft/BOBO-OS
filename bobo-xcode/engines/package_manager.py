"""
Swift Package Manager helper for BoboXcode.
Reads/edits Package.swift dependencies and drives resolve/update.
"""
import subprocess
import os
import re
import shutil
import json
from typing import Callable, List, Dict, Optional
from engines.swift_engine import BuildResult


class PackageManager:
    def __init__(self):
        self.swift_bin = self._find_swift()

    def _find_swift(self) -> Optional[str]:
        for cand in ["/usr/local/bin/swift", shutil.which("swift")]:
            if cand and os.path.exists(cand):
                return cand
        return None

    def resolve(self, project_path: str, callback: Callable = None) -> BuildResult:
        return self._run(["package", "resolve"], project_path, callback)

    def update(self, project_path: str, callback: Callable = None) -> BuildResult:
        return self._run(["package", "update"], project_path, callback)

    def clean(self, project_path: str, callback: Callable = None) -> BuildResult:
        return self._run(["package", "clean"], project_path, callback)

    def describe(self, project_path: str) -> Dict:
        """Return the package description as a dict (name, products, targets)."""
        if not self.swift_bin:
            return {}
        try:
            r = subprocess.run([self.swift_bin, "package", "describe", "--type", "json"],
                               cwd=project_path, capture_output=True, text=True, timeout=60)
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except Exception:
            return {}

    def list_dependencies(self, project_path: str) -> List[str]:
        """Parse Package.swift for declared `.package(url:...)` dependencies."""
        manifest = os.path.join(project_path, "Package.swift")
        if not os.path.exists(manifest):
            return []
        with open(manifest, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return re.findall(r'\.package\([^)]*url:\s*"([^"]+)"', text)

    def add_dependency(self, project_path: str, url: str, version: str = "1.0.0") -> bool:
        """
        Append a SPM dependency to Package.swift's dependencies array.
        Inserts a `.package(url:..., from:...)` entry idempotently.
        """
        manifest = os.path.join(project_path, "Package.swift")
        if not os.path.exists(manifest):
            return False
        with open(manifest, "r", encoding="utf-8") as fh:
            text = fh.read()
        if url in text:
            return True
        entry = '.package(url: "%s", from: "%s"),' % (url, version)
        # Insert right after `dependencies: [`
        new_text, n = re.subn(r'(dependencies:\s*\[)', r'\1\n        ' + entry, text, count=1)
        if n == 0:
            return False
        with open(manifest, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        return True

    def _run(self, args: list, cwd: str, callback: Callable) -> BuildResult:
        if not self.swift_bin:
            return BuildResult(False, "", "Swift toolchain not installed.")
        out = []
        p = subprocess.Popen([self.swift_bin] + args, cwd=cwd,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
        for line in p.stdout:
            out.append(line)
            if callback:
                callback(line)
        p.wait()
        return BuildResult(p.returncode == 0, "".join(out), "")
