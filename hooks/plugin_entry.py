"""Plugin adapter for the same branch-pinned startup contract as installed hooks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import launch

if __name__ == "__main__":
    launch(sys.argv[1], event=sys.argv[2], plugin=Path(__file__).resolve().parents[1])
