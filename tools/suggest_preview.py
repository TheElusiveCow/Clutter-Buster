"""Developer check: print what 'Automatically do it' WOULD suggest for the real desktop.

Read-only: it reads layout.json and looks at the desktop, and changes nothing
(no hiding, no saving, no groups made).
Run:  .venv\\Scripts\\python.exe tools\\suggest_preview.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clutterbuster import organize  # noqa: E402
from clutterbuster.icons import display_name  # noqa: E402
from clutterbuster.store import Layout  # noqa: E402

plan = organize.suggest(Layout())
if not plan:
    print("Nothing to suggest: every visible desktop item is already in a group.")
for s in plan:
    where = f"existing group '{s['name']}'" if s["gid"] else f"new group '{s['name']}'"
    print(f"{s['key']:>10} -> {where}{'' if s['enabled'] else ' (off by default)'}: "
          + ", ".join(display_name(i["path"]) for i in s["items"]))
