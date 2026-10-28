#!/usr/bin/env python3
"""Check inode-preserving rewrite and stale-input refusal on a disposable file."""
import importlib.util
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("metadata_io", Path(__file__).resolve().parents[1] / "scripts" / "metadata_io.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix="migration-metadata-") as tmp:
    root = Path(tmp)
    root.chmod(0o775)
    path = root / "metadata.json"
    path.write_bytes(b'original metadata')
    before = path.stat()
    module.write_in_place(path, b'new', module.sha(b'original metadata'))
    assert path.read_bytes() == b'new' and path.stat().st_ino == before.st_ino
    try:
        module.write_in_place(path, b'unsafe', module.sha(b'original metadata'))
    except ValueError:
        pass
    else:
        raise AssertionError("stale metadata accepted")
    assert path.read_bytes() == b'new'
    try:
        module.write_in_place(path, b'unsafe', module.sha(b'new'), [before.st_dev, before.st_ino + 1])
    except ValueError:
        pass
    else:
        raise AssertionError('different metadata inode accepted')
    assert path.read_bytes() == b'new'
    module.write_in_place(path, b'original metadata')
    assert path.read_bytes() == b'original metadata' and path.stat().st_ino == before.st_ino
print("metadata selftest passed")
