"""Root conftest for identity-service — sets up sys.path for src-based imports."""

import sys
from pathlib import Path

# Add src/ to sys.path so that top-level imports like "from core.settings" work.
# This is needed because pyproject.toml lists packages as ["src/application", ...],
# which makes hatchling create a namespace where these are top-level modules.
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
