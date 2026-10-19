#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from fais.backup import create_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and verify an online FAIS SQLite backup")
    parser.add_argument("database", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()
    print(create_backup(args.database, args.destination, keep=args.keep))


if __name__ == "__main__":
    main()
