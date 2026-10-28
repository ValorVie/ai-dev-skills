#!/usr/bin/env python3
"""Keep common-path ACLs on a disposable staging tree outside Beads."""
import importlib.util
import tempfile
from pathlib import Path

directory = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('staged_acl', directory / 'staged_acl.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='migration-staged-acl-') as tmp:
    root = Path(tmp)
    root.chmod(0o775)
    source = root / 'source'
    stage = root / 'stage'
    source.mkdir()
    stage.mkdir()
    (source / 'file').write_text('source')
    (stage / 'file').write_text('restored')
    (source / 'file').chmod(0o640)
    (stage / 'file').chmod(0o777)
    baseline = module.permissions.capture(source)
    original = (source / 'file').read_bytes()
    module.reconcile(stage, baseline, root / 'protected')
    after = module.permissions.capture(stage)
    assert after['file']['mode'] == baseline['file']['mode']
    assert after['file']['acl'] == baseline['file']['acl']
    assert (stage / 'file').read_text() == 'restored'
    assert (source / 'file').read_bytes() == original
    try:
        module.reconcile(stage, baseline, root)
    except ValueError:
        pass
    else:
        raise AssertionError('staging inside protected tree accepted')
print('staged ACL selftest passed')
