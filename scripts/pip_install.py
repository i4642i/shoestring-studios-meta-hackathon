"""Install requirements.txt one package at a time with visible progress.

start_server.bat calls this instead of bare `pip install -r` so a heavy
first install (~1GB of ML wheels) shows [i/N] + package name instead of
sitting silent. Stdlib only. Usage (from repo root):
  .venv\\Scripts\\python.exe scripts\\pip_install.py [--list]

--list only prints what would be installed (dry run for testing).
"""
import subprocess
import sys


def parse_requirements(path="requirements.txt"):
    options, packages = [], []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-"):
                options.extend(line.split())
                continue
            options_idx = line.find(" #")
            if options_idx >= 0:
                line = line[:options_idx].strip()
            if line:
                packages.append(line)
    return options, packages


def main(argv):
    options, packages = parse_requirements()
    if "--list" in argv:
        print("options: %s" % " ".join(options))
        print("packages: %d" % len(packages))
        for p in packages:
            print("  " + p)
        return 0
    total = len(packages)
    print("Installing %d packages into this interpreter "
          "(first run downloads ~1GB)..." % total, flush=True)
    for i, pkg in enumerate(packages, 1):
        print("[%d/%d] Installing %s" % (i, total, pkg), flush=True)
        cmd = [sys.executable, "-m", "pip", "install",
               "--disable-pip-version-check"] + options + [pkg]
        try:
            subprocess.run(cmd, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print("[ERROR] failed on %s: %s" % (pkg, exc))
            return 1
    print("All %d packages installed." % total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
