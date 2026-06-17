"""
Prepares a local project for transfer to the Mac cloud.
Detects the project type and Xcode scheme, and can produce a clean tarball
(excluding build artifacts) for fast, reproducible uploads.
"""
import os
import tarfile
import fnmatch

EXCLUDE = [".build", "DerivedData", ".git", "node_modules", "*.xcuserstate",
           "Pods", ".dart_tool", "build"]


class ProjectPackager:
    def detect_type(self, path: str) -> str:
        try:
            entries = os.listdir(path)
        except Exception:
            return "swift"
        if any(e.endswith(".xcodeproj") or e.endswith(".xcworkspace") or e == "Package.swift"
               for e in entries):
            return "swift"
        if "pubspec.yaml" in entries:
            return "flutter"
        if "package.json" in entries:
            return "react_native"
        return "swift"

    def detect_scheme(self, path: str) -> str:
        """Find an Xcode scheme name, falling back to the project/app name."""
        for root, dirs, files in os.walk(path):
            for f in files:
                if f.endswith(".xcscheme"):
                    return f[:-len(".xcscheme")]
            # don't descend into build dirs
            dirs[:] = [d for d in dirs if d not in EXCLUDE]
        # fallback: *.xcodeproj basename
        for e in os.listdir(path):
            if e.endswith(".xcodeproj"):
                return e[:-len(".xcodeproj")]
        return os.path.basename(os.path.normpath(path)) or "App"

    def _excluded(self, name: str) -> bool:
        return any(fnmatch.fnmatch(name, pat) or name == pat for pat in EXCLUDE)

    def make_tarball(self, path: str, out_path: str) -> str:
        """Create a clean .tar.gz of the project (excludes build artifacts)."""
        def filt(tarinfo):
            base = os.path.basename(tarinfo.name)
            parts = tarinfo.name.split("/")
            if any(self._excluded(p) for p in parts) or self._excluded(base):
                return None
            return tarinfo
        with tarfile.open(out_path, "w:gz") as tar:
            tar.add(path, arcname=os.path.basename(os.path.normpath(path)), filter=filt)
        return out_path

    def summary(self, path: str) -> dict:
        """Return a quick project summary for the UI."""
        return {
            "type": self.detect_type(path),
            "scheme": self.detect_scheme(path),
            "name": os.path.basename(os.path.normpath(path)),
        }
