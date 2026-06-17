"""
Swift compilation engine for BoboXcode.
Uses the official Apple Swift toolchain for Linux (open-source, legal).
All operations are local on BOBO OS — no external account, no cost.
"""
import subprocess
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Optional, List


@dataclass
class BuildResult:
    success: bool
    output: str
    errors: str
    binary_path: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class SwiftEngine:
    """Wraps `swift build/test/package` for local compilation."""

    def __init__(self):
        self.swift_bin = self._find_swift()

    # ------------------------------------------------------------------ detect
    def _find_swift(self) -> Optional[str]:
        """Locate the installed swift toolchain (None if not installed yet)."""
        candidates = [
            "/usr/local/bin/swift",
            "/opt/swift/usr/bin/swift",
            shutil.which("swift"),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        # Lean ISO may ship without Swift; the UI surfaces an install hint.
        return None

    def is_available(self) -> bool:
        return self.swift_bin is not None

    def version(self) -> str:
        if not self.swift_bin:
            return "Swift toolchain not installed"
        try:
            return subprocess.run([self.swift_bin, "--version"],
                                  capture_output=True, text=True, timeout=20).stdout.splitlines()[0]
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------ build
    def build(self, project_path: str, configuration: str = "debug",
              callback: Callable = None) -> BuildResult:
        """Compile a Swift package (Package.swift) with Swift Package Manager."""
        if not self.swift_bin:
            return BuildResult(False, "", "Swift toolchain not installed. "
                               "Run a FULL build or: bobo-xcode --install-swift")
        cmd = [self.swift_bin, "build", "--configuration", configuration,
               "--build-path", os.path.join(project_path, ".build")]
        return self._run_command(cmd, project_path, callback, configuration)

    def run_tests(self, project_path: str, callback: Callable = None) -> BuildResult:
        if not self.swift_bin:
            return BuildResult(False, "", "Swift toolchain not installed.")
        return self._run_command([self.swift_bin, "test"], project_path, callback)

    def resolve_dependencies(self, project_path: str, callback: Callable = None) -> BuildResult:
        if not self.swift_bin:
            return BuildResult(False, "", "Swift toolchain not installed.")
        return self._run_command([self.swift_bin, "package", "resolve"], project_path, callback)

    def run_binary(self, project_path: str, callback: Callable = None) -> BuildResult:
        """Build then execute the package's product, streaming stdout."""
        if not self.swift_bin:
            return BuildResult(False, "", "Swift toolchain not installed.")
        return self._run_command([self.swift_bin, "run"], project_path, callback)

    def create_project(self, path: str, name: str, template: str = "executable") -> str:
        """Create a new Swift package from an SPM template."""
        os.makedirs(path, exist_ok=True)
        if self.swift_bin:
            subprocess.run([self.swift_bin, "package", "init", "--name", name,
                            "--type", template], cwd=path, check=True)
        return path

    def get_lsp_command(self) -> Optional[list]:
        """Return the sourcekit-lsp command (for autocomplete/go-to-def)."""
        for cand in ["/usr/local/bin/sourcekit-lsp", shutil.which("sourcekit-lsp")]:
            if cand and os.path.exists(cand):
                return [cand]
        if self.swift_bin:
            guess = os.path.join(os.path.dirname(self.swift_bin), "sourcekit-lsp")
            if os.path.exists(guess):
                return [guess]
        return None

    # ------------------------------------------------------------------ helpers
    def _find_built_binary(self, project_path: str, configuration: str) -> Optional[str]:
        build_dir = os.path.join(project_path, ".build", configuration)
        if not os.path.isdir(build_dir):
            return None
        for f in os.listdir(build_dir):
            full = os.path.join(build_dir, f)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
        return None

    def _run_command(self, cmd: list, cwd: str, callback: Callable,
                     configuration: str = "debug") -> BuildResult:
        output_lines, errors, warnings = [], [], []
        try:
            process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1)
        except FileNotFoundError as e:
            return BuildResult(False, "", str(e))
        for line in process.stdout:
            output_lines.append(line)
            low = line.lower()
            if "error:" in low:
                errors.append(line)
            elif "warning:" in low:
                warnings.append(line)
            if callback:
                callback(line)
        process.wait()
        success = process.returncode == 0
        binary = self._find_built_binary(cwd, configuration) if success else None
        return BuildResult(success=success, output="".join(output_lines),
                           errors="".join(errors), binary_path=binary, warnings=warnings)
