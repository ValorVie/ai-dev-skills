#!/usr/bin/env python3
"""Only write counts, sampled IDs and hashes; never write the bd payload."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def read_bd(binary, *args):
    proc = subprocess.run([binary, "--readonly", *args, "--json"], capture_output=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"bd {args[0]} failed (exit {proc.returncode})")
    result = json.loads(proc.stdout)
    if not isinstance(result, list):
        raise ValueError(f"bd {args[0]} did not return a list")
    return result


def normalize(item):
    if isinstance(item, dict):
        result = {key: normalize(value) for key, value in item.items()}
        for key in ("dependencies", "dependents", "labels"):
            if isinstance(result.get(key), list):
                result[key] = sorted(result[key], key=lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True))
        return result
    if isinstance(item, list):
        return [normalize(value) for value in item]
    return item


def digest(items):
    ordered = sorted(json.dumps(normalize(item), ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in items)
    data = json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def summarize(binary):
    rows = read_bd(binary, "list", "--all", "--limit", "0")
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows) or not by_id or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", key) for key in by_id):
        raise ValueError("issue IDs are missing, duplicated or invalid")
    ids = sorted(by_id)
    selected = set(ids[:3])
    for field in ("comment_count", "dependency_count"):
        match = next((key for key in ids if by_id[key].get(field, 0)), None)
        if match:
            selected.add(match)
    selected = sorted(selected)
    show = read_bd(binary, "show", *selected)
    if {row.get("id") for row in show} != set(selected):
        raise ValueError("sample show returned different IDs")
    comments = {key: digest(read_bd(binary, "comments", key)) for key in selected}
    deps = {key: digest(read_bd(binary, "dep", "list", key)) for key in selected}
    return {"issue_count": len(rows), "list_sha256": digest(rows), "sample_ids": selected,
            "show_sha256": digest(show), "comments_sha256": comments, "deps_sha256": deps}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bd", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("snapshot output already exists")
    expected = json.loads(args.expected.read_text()) if args.expected else None
    result = summarize(args.bd)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")
    if expected is not None and result != expected:
        print("讀回不一致；保留快照並停止", file=sys.stderr)
        return 1
    print(f"讀回一致；任務數={result['issue_count']}" if expected else f"已記錄基準；任務數={result['issue_count']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
        print(f"快照失敗：{type(error).__name__}", file=sys.stderr)
        sys.exit(1)
