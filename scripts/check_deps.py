"""Exit 0 when every requirements.txt package is installed in THIS interpreter.

Used by start_server.bat: if pip install fails (e.g. offline), the server
still starts when the packages are already there. Stdlib only.
Usage (from repo root): .venv\\Scripts\\python.exe scripts\\check_deps.py
"""
import importlib.metadata
import re
import sys


def main():
    missing = []
    with open("requirements.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            name = re.split(r"[<>=!;\s\[]", line, 1)[0].strip()
            if not name:
                continue
            try:
                importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                missing.append(name)
    if missing:
        print("missing packages: " + ", ".join(missing))
        return 1
    print("all required packages already installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
