"""Start Clutter Buster.

    .venv\\Scripts\\pythonw.exe main.py            start it (pythonw = no black console window)
    .venv\\Scripts\\python.exe  main.py --quit     ask the running copy to quit nicely
                                                 (it shows everything on the desktop again)
    .venv\\Scripts\\python.exe  main.py --rehide   ask the running copy to try hiding failed items again
    .venv\\Scripts\\pythonw.exe main.py --uninstall  remove Clutter Buster (same as Settings > Apps > Uninstall)
    .venv\\Scripts\\python.exe  main.py --showcase shot.png
                                                 safe demo screenshot with pretend groups
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    os.chdir(HERE)   # Windows starts Run-key programs in another folder; work from our own
except OSError:
    pass

SHOWCASE = "--showcase" in sys.argv
if SHOWCASE:
    # demo mode: throw-away settings, and never look at the real desktop
    os.environ["CLUTTERBUSTER_SHOWCASE"] = "1"
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="clutterbuster-showcase-")

from clutterbuster import paths  # noqa: E402

paths.ensure_dirs()
paths.setup_logging()
paths.install_excepthook()
if "--quit" not in sys.argv:
    paths.install_faulthandler()

if __name__ == "__main__":
    if SHOWCASE:
        from clutterbuster.showcase import run_showcase
        i = sys.argv.index("--showcase")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.path.join(tempfile.gettempdir(), "clutterbuster-showcase.png")
        sys.exit(run_showcase(out))
    from clutterbuster.app import run
    sys.exit(run(sys.argv))
