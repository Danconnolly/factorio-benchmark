#!/usr/bin/env python3
"""Backward-compatible command-line entry point for the smelting runner."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from factorio_benchmark.smelt_session import main


if __name__ == "__main__":
    main()
