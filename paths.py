"""Where Physiognomy keeps its data, in one place.

By default the data lives in `taste/` beside the code: your references, your marks, and everything made from them.
To keep it somewhere else, make a `mine.py` beside this file (it's never published) that sets DATA,
and, if you like, EXTRA: more files for serve.py to hand out, as {url: (path, content type)}.
"""
from pathlib import Path

TOOL = Path(__file__).resolve().parent
DATA = TOOL / "taste"
EXTRA = {}

try:
    from mine import *  # noqa: F401,F403 — personal paths, kept out of the public copy
except ImportError:
    pass
