from __future__ import annotations

import sys
from pathlib import Path

from .ui import run


def main() -> int:
    return run(Path.cwd())


if __name__ == "__main__":
    sys.exit(main())
