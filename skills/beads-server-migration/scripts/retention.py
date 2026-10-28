#!/usr/bin/env python3
"""Retain only marked migration backups; never delete a protected recovery copy."""
import argparse
import os
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_safety

PATTERN = re.compile(r"migration-backup-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\Z")


def owned(path):
    marker = path / ".migration-backup"
    return (bool(PATTERN.fullmatch(path.name)) and not path.is_symlink() and path.is_dir()
            and not marker.is_symlink() and marker.is_file()
            and marker.read_text(encoding="utf-8") == "migration-backup-v1\n")


def select(root, keep, protected):
    if root.is_symlink() or not root.is_dir() or keep < 1:
        raise ValueError("invalid backup directory or count")
    candidates = sorted((p for p in root.iterdir() if owned(p)), key=lambda p: p.name, reverse=True)
    by_name = {p.name: p for p in candidates}
    if not protected <= by_name.keys() or len(protected) > keep:
        raise ValueError("protected backup missing or exceeds retention")
    retained = set(protected)
    for path in candidates:
        if len(retained) >= keep:
            break
        retained.add(path.name)
    return [path for path in candidates if path.name not in retained]


def _walk_error(error):
    raise error


def delete(root, paths):
    for path in paths:
        if path.parent != root or not owned(path):
            raise ValueError("backup changed before deletion")
        if gate_safety.contains_gate(path):
            raise ValueError("gate file in backup; preserve it")
        for directory, dirs, files in os.walk(path, followlinks=False, onerror=_walk_error):
            if '.dolt' in Path(directory).parts and any('lock' in name.lower() for name in dirs + files):
                raise ValueError(f"Dolt lock in backup; preserve it: {path}")
    for path in paths:
        shutil.rmtree(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--keep", type=int, default=5)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed", action="store_true")
    args = parser.parse_args()
    if args.apply != args.reviewed:
        raise ValueError("--apply and --reviewed are required together")
    paths = select(args.directory, args.keep, set(args.protect))
    for path in paths:
        print(f"{'刪除' if args.apply else '預計刪除'} {path}")
    if args.apply:
        delete(args.directory, paths)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"備份保留檢查失敗：{error}", file=sys.stderr)
        sys.exit(1)
