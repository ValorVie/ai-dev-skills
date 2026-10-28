#!/usr/bin/env python3
"""Check snapshot comparison and refusal to overwrite evidence."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'scripts' / 'snapshot.py'
spec = importlib.util.spec_from_file_location('snapshot', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data = {'value': 'one'}

def read_bd(_binary, *args):
    if args[0] == 'list':
        return [{'id': 'sample-1', 'comment_count': 1, 'metadata': data.copy()}]
    if args[0] == 'show':
        return [{'id': 'sample-1', 'labels': ['b', 'a']}]
    return []

with tempfile.TemporaryDirectory(prefix='migration-snapshot-') as tmp, patch.object(module, 'read_bd', read_bd):
    root = Path(tmp)
    before = root / 'before.json'
    with patch.object(sys, 'argv', ['snapshot.py', '--bd', '/bin/true', '--out', str(before)]):
        assert module.main() == 0
    expected = json.loads(before.read_text())
    assert expected['issue_count'] == 1
    with patch.object(sys, 'argv', ['snapshot.py', '--bd', '/bin/true', '--out', str(before)]):
        try:
            module.main()
        except FileExistsError:
            pass
        else:
            raise AssertionError('existing evidence was overwritten')
    data['value'] = 'two'
    with patch.object(sys, 'argv', ['snapshot.py', '--bd', '/bin/true', '--out', str(root / 'after.json'), '--expected', str(before)]):
        assert module.main() == 1
    assert json.loads(before.read_text()) == expected
print('snapshot selftest passed')
