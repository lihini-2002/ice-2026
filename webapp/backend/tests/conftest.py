import sys
from pathlib import Path

# app.py lives one directory up from tests/; it's a script-style module (no
# package __init__.py), same convention as scripts/*.py importing common.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
