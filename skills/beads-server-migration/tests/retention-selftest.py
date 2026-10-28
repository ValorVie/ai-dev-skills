#!/usr/bin/env python3
"""Test backup retention on disposable directories."""
import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("retention", Path(__file__).resolve().parents[1] / "scripts" / "retention.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix="migration-retention-") as tmp:
    root = Path(tmp)
    root.chmod(0o775)
    names = [f"migration-backup-20261027T1200{n:02d}Z-{n:08x}" for n in range(7)]
    for name in names:
        path = root / name
        path.mkdir()
        (path / ".migration-backup").write_text("migration-backup-v1\n")
    (root / "unrelated").mkdir()
    (root / "migration-backup-20261027T120099Z-deadbeef").mkdir()
    planned = module.select(root, 5, {names[0]})
    assert len(planned) == 2 and all((root / n).exists() for n in names)
    assert names[0] not in {p.name for p in planned}
    with patch.object(module.gate_safety, 'contains_gate', side_effect=[False, True]):
        try:
            module.delete(root, planned)
        except ValueError:
            pass
        else:
            raise AssertionError('backup containing a gate file was deleted')
    assert all(path.exists() for path in planned)
    with patch.object(module.os, 'walk', side_effect=[[], [('fixture/.dolt/noms', [], ['LOCK'])]]):
        try:
            module.delete(root, planned)
        except ValueError:
            pass
        else:
            raise AssertionError('backup containing a Dolt lock was deleted')
    assert all(path.exists() for path in planned)
    with patch.object(module.os, 'walk', side_effect=PermissionError('fixture unreadable')):
        try:
            module.delete(root, planned)
        except PermissionError:
            pass
        else:
            raise AssertionError('unreadable backup was deleted')
    assert all(path.exists() for path in planned)
    module.delete(root, planned)
    assert sum((root / n).exists() for n in names) == 5
    assert (root / "unrelated").is_dir() and (root / "migration-backup-20261027T120099Z-deadbeef").is_dir()
    assert module.select(root, 5, {names[0]}) == []
    try:
        module.select(root, 0, set())
    except ValueError:
        pass
    else:
        raise AssertionError("invalid retention count accepted")
print("retention selftest passed")
