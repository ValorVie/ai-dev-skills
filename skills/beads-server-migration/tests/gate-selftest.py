#!/usr/bin/env python3
"""Detect gate locks before considering any state-directory cleanup."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gate_safety

with tempfile.TemporaryDirectory(prefix='migration-gate-') as tmp:
    root = Path(tmp)
    nested = root / 'nested'
    nested.mkdir()
    assert not gate_safety.contains_gate(root)
    (nested / 'database.gate.lock').touch()
    assert gate_safety.contains_gate(root)
print('gate selftest passed')
