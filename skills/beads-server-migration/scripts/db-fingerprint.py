#!/usr/bin/env python3
"""Fingerprint server working data, including Dolt-ignored user tables."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def query(base, sql):
    proc = subprocess.run([*base, "sql", "-r", "json", "-q", sql],
                          capture_output=True, text=True, timeout=180, check=True)
    result = json.loads(proc.stdout)
    if not isinstance(result.get("rows"), list):
        raise ValueError("unexpected Dolt result")
    return result["rows"]


def fingerprint(base, database):
    tables = query(base, "SHOW FULL TABLES")
    key = "Tables_in_" + database
    names = sorted(row[key] for row in tables if row.get("Table_type") == "BASE TABLE")
    if not names or len(names) != len(set(names)) or any(not re.fullmatch(r"[A-Za-z0-9_]+", n) for n in names):
        raise ValueError("unexpected database table names")
    columns = ["DOLT_HASHOF('HEAD') AS head", "DOLT_HASHOF_DB('WORKING') AS working",
               "DOLT_HASHOF_DB('STAGED') AS staged"]
    columns.extend(f"DOLT_HASHOF_TABLE('{name}') AS t{index}" for index, name in enumerate(names))
    rows = query(base, "SELECT " + ", ".join(columns))
    if len(rows) != 1:
        raise ValueError("unexpected hash row count")
    row = rows[0]
    hashes = {name: row[f"t{index}"] for index, name in enumerate(names)}
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-v]{32}", value)
           for value in [row["head"], row["working"], row["staged"], *hashes.values()]):
        raise ValueError("invalid database hash")
    branches = query(base, "SELECT name, hash FROM dolt_branches ORDER BY name")
    if len(branches) != 1 or branches[0].get("name") != "main":
        raise ValueError("immediate rollback requires exactly one main branch")
    schemas = {}
    for name in names:
        rows = query(base, f"SHOW CREATE TABLE `{name}`")
        if len(rows) != 1 or not isinstance(rows[0].get("Create Table"), str):
            raise ValueError("unexpected table schema")
        schemas[name] = hashlib.sha256(rows[0]["Create Table"].encode()).hexdigest()
    return {"head": row["head"], "working": row["working"], "staged": row["staged"],
            "tables": hashes, "schemas": schemas, "branches": branches}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dolt", required=True)
    parser.add_argument("--database", required=True)
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument("--port", type=int)
    location.add_argument("--local", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.database) or (args.port is not None and not 1 <= args.port <= 65535):
        raise ValueError("invalid database or port")
    if args.local is not None:
        if args.local.is_symlink() or not args.local.is_dir():
            raise ValueError("invalid local database")
        base = [args.dolt, "-C", str(args.local)]
    else:
        base = [args.dolt, "--host", "127.0.0.1", "--port", str(args.port), "--no-tls", "--use-db", args.database]
    result = fingerprint(base, args.database)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(result, output, sort_keys=True, indent=2)
        output.write("\n")
    if args.expected and result != json.loads(args.expected.read_text(encoding="utf-8")):
        print("伺服器資料或分支已變，不能立即退回", file=sys.stderr)
        return 1
    print(f"已核對 {len(result['tables'])} 個資料表")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"伺服器資料檢查失敗：{type(error).__name__}", file=sys.stderr)
        sys.exit(1)
