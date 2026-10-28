#!/usr/bin/env python3
"""Verify ignored-table changes are retained in the server fingerprint."""
import importlib.util
import copy
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("fingerprint", Path(__file__).resolve().parents[1] / "scripts" / "db-fingerprint.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
state = {"events": "a" * 32}

def query(_base, sql):
    if sql == "SHOW FULL TABLES":
        return [{"Tables_in_test": "events", "Table_type": "BASE TABLE"},
                {"Tables_in_test": "issues", "Table_type": "BASE TABLE"}]
    if sql.startswith("SELECT name, hash"):
        return [{"name": "main", "hash": "b" * 32}]
    if sql.startswith("SHOW CREATE TABLE"):
        return [{"Table": "test", "Create Table": "CREATE TABLE test (id INT)"}]
    assert "DOLT_HASHOF_TABLE('events')" in sql
    return [{"head": "b" * 32, "working": "c" * 32, "staged": "d" * 32,
             "t0": state["events"], "t1": "e" * 32}]

module.query = query
before = module.fingerprint([], "test")
state["events"] = "f" * 32
after = module.fingerprint([], "test")
assert before["working"] == after["working"] and before != after
assert before["tables"]["events"] != after["tables"]["events"]
assert "events" in before["schemas"]
with tempfile.TemporaryDirectory(prefix='migration-full-fingerprint-') as directory:
    root = Path(directory)
    expected = root / 'expected.json'
    expected.write_text(json.dumps(before))
    for index, (key, value) in enumerate((('head', 'f' * 32), ('staged', 'g' * 32),
                                           ('branches', [{'name': 'main', 'hash': 'h' * 32}]))):
        changed = copy.deepcopy(before)
        changed[key] = value
        args = ['db-fingerprint.py', '--dolt', '/usr/bin/dolt', '--database', 'test', '--local', str(root), '--expected', str(expected),
                '--out', str(root / f'actual-{index}.json')]
        with patch.object(sys, 'argv', args), patch.object(module, 'fingerprint', return_value=changed):
            assert module.main() == 1, key
print("database fingerprint selftest passed")
