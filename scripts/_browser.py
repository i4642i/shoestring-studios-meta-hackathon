"""Shared headless-Edge launcher for the live checks (J28).

Mode from SHOE_CHECK_GL: "gpu" (default, hardware ANGLE/D3D11)
or "software" (SwiftShader on the CPU, for PCs without a usable
GPU). Stdlib only.
"""
import os
import shutil
import subprocess

EDGE = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

SOFTWARE_FLAGS = ["--disable-gpu", "--use-angle=swiftshader"]

RENDERER_JS = ("(() => { const c = document.createElement('canvas');"
               " const gl = c.getContext('webgl2') ||"
               " c.getContext('webgl');"
               " if (!gl) return 'NO-WEBGL';"
               " const ext = gl.getExtension("
               "'WEBGL_debug_renderer_info');"
               " const r = ext ? gl.getParameter("
               "ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter("
               "gl.RENDERER);"
               " return String(r); })()")


def mode():
    """'gpu' unless SHOE_CHECK_GL=software."""
    m = os.environ.get("SHOE_CHECK_GL", "gpu").strip().lower()
    return "software" if m == "software" else "gpu"


def launch_args(cdp_port, profile, width=None, height=None,
                extra=(), binary=None):
    """Full Edge command line for one check run."""
    args = [binary or EDGE, "--headless", "--no-sandbox",
            "--no-first-run", "--disable-extensions"]
    if mode() == "software":
        args = args + SOFTWARE_FLAGS
    args = args + list(extra)
    args = args + ["--remote-debugging-port=%d" % cdp_port,
                   "--user-data-dir=" + profile]
    if width and height:
        args = args + ["--window-size=%d,%d" % (width, height)]
    return args + ["about:blank"]


def dump_dom_args(url, profile, width, height, budget_s=15,
                  binary=None):
    """One-shot Edge command line for --dump-dom harness pages.

    Same GL-mode rule as launch_args: hardware by default, SwiftShader
    only with SHOE_CHECK_GL=software. Returns the argv list."""
    args = [binary or EDGE, "--headless", "--no-sandbox",
            "--no-first-run", "--disable-extensions"]
    if mode() == "software":
        args = args + SOFTWARE_FLAGS
    return args + ["--user-data-dir=" + profile,
                   "--virtual-time-budget=%d" % (budget_s * 1000),
                   "--window-size=%d,%d" % (width, height),
                   "--dump-dom", url]


def stop_tree(proc, name):
    """Kill a process and its whole tree (taskkill /T). Plain
    terminate() leaves Edge helper processes behind holding the
    CPU and the debug port."""
    if proc is None or proc.poll() is not None:
        return proc.poll() if proc is not None else None
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID",
                        str(proc.pid)], capture_output=True,
                       timeout=15)
        proc.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except (OSError, subprocess.SubprocessError):
            pass
    print("stopped %s (exit %s)" % (name, proc.poll()), flush=True)
    return proc.poll()


def cleanup_edge(proc, profile):
    """Stop the check browser tree and delete its temp profile."""
    stop_tree(proc, "edge")
    shutil.rmtree(profile or "", ignore_errors=True)


def renderer_verdict(renderer):
    """(ok, line) for the one renderer print per check. Gpu mode
    fails loudly on software WebGL instead of silently using it."""
    r = renderer or "?"
    if mode() == "software":
        return True, "software WebGL (CPU) (%s)" % r
    if "nvidia" in r.lower():
        return True, "GPU WebGL: %s" % r
    return False, "GPU not available in headless browser: %s" % r
