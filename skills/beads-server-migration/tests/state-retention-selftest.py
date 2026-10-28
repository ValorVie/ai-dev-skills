#!/usr/bin/env python3
"""Exercise completed-state retention with disposable directories only."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('state_retention', Path(__file__).resolve().parents[1] / "scripts" / 'state_retention.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory(prefix='migration-state-retention-') as tmp:
    root = Path(tmp)
    root.chmod(0o775)
    def archive(n, *, complete=True, marked=True):
        path = root / ('completed-' + f'{n:032x}')
        path.mkdir()
        if marked:
            (path / '.migration-state').write_text('migration-state-v1\n')
        (path / 'target.json').write_text(json.dumps({'repo': '/fixture/repo', 'uid': os.getuid()}))
        if complete:
            (path / 'rollback-complete').write_text('immediate\n')
            (path / 'switch-complete').write_text('ok\n')
            (path / 'operations.log').write_text('退回開始：immediate\n')
            (path / ('rollback-attempt-' + 'a' * 32 + '.started')).write_text('started\n')
            (path / ('rollback-attempt-' + 'a' * 32 + '.completed')).write_text('ok\n')
            os.utime(path / 'switch-complete', ns=(n * 1000000000, n * 1000000000))
        os.utime(path, ns=(n * 1000000000, n * 1000000000))
        return path
    paths = [archive(n) for n in range(1, 8)]
    failed = archive(8, complete=False)
    unmarked = archive(9, marked=False)
    broken = archive(10)
    (broken / 'rollback-attempt-1234567890abcdef1234567890abcdef.started').touch()
    os.utime(broken, ns=(10 * 1000000000, 10 * 1000000000))
    latest = archive(11)
    (paths[0] / '.dolt').mkdir()
    (paths[0] / '.dolt/LOCK').touch()
    os.utime(paths[0], ns=(1000000000, 1000000000))
    current = root / 'current'
    current.mkdir()
    events = []
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'in_use', return_value=False):
        module.cleanup(root, 5, '/fixture/repo', os.getuid(), events.append)
    assert not paths[0].exists() and not paths[1].exists() and not paths[2].exists()
    assert len(events) == 6 and all(x.startswith('預計刪除') for x in events[:3])
    assert all(x.startswith('已刪除') for x in events[3:])
    assert all(p.exists() for p in paths[3:] + [failed, unmarked, broken, latest, current])
    # Newest five are never replaced by older protected failures.
    assert sum(p.exists() for p in paths + [latest]) == 5
    (current / '.migration-state').write_text('migration-state-v1\n')
    (current / 'switch-complete').write_text('ok\n')
    (current / 'target.json').write_text(json.dumps({'repo': '/fixture/repo', 'uid': os.getuid()}))
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'in_use', return_value=False):
        module.cleanup(root, 5, '/fixture/repo', os.getuid())
    assert not paths[3].exists() and all(p.exists() for p in paths[4:] + [latest, current, failed, unmarked, broken])
    assert sum(p.exists() for p in paths + [latest, current]) == 5
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'in_use', return_value=False):
        module.cleanup(root, 1, '/fixture/repo', os.getuid())
    assert current.exists() and all(not p.exists() for p in paths + [latest])
    assert all(p.exists() for p in (failed, unmarked, broken))
    preparing = archive(12)
    before = preparing / 'reswitch-before.json'
    before.write_bytes(b'{}\n')
    assert not module.marked(preparing, '/fixture/repo', os.getuid())
    tree = preparing / 'reswitch-saved-tree'
    tree.mkdir()
    intent = preparing / 'reswitch-intent.json'
    intent.write_text(json.dumps({'tree': [tree.stat().st_dev, tree.stat().st_ino],
                                  'baseline_sha': module.hashlib.sha256(before.read_bytes()).hexdigest()}))
    assert not module.marked(preparing, '/fixture/repo', os.getuid())
    (preparing / 'reswitch-complete').write_text('wrong\n')
    assert not module.marked(preparing, '/fixture/repo', os.getuid())
    (preparing / 'reswitch-complete').write_text(module.hashlib.sha256(intent.read_bytes()).hexdigest() + '\n')
    assert module.marked(preparing, '/fixture/repo', os.getuid())

with tempfile.TemporaryDirectory(prefix='migration-state-busy-') as tmp:
    root = Path(tmp)
    root.chmod(0o775)
    paths = []
    for n in range(1, 4):
        path = root / ('completed-' + f'{n:032x}')
        path.mkdir()
        for name, value in (('.migration-state', 'migration-state-v1\n'), ('rollback-complete', 'immediate\n'), ('switch-complete', 'ok\n')):
            (path / name).write_text(value)
        (path / 'operations.log').write_text('退回開始：immediate\n')
        (path / ('rollback-attempt-' + 'a' * 32 + '.started')).write_text('started\n')
        (path / ('rollback-attempt-' + 'a' * 32 + '.completed')).write_text('ok\n')
        os.utime(path / 'switch-complete', ns=(n * 1000000000, n * 1000000000))
        (path / 'target.json').write_text(json.dumps({'repo': '/fixture/repo', 'uid': os.getuid()}))
        nested = path / 'data'
        nested.mkdir()
        (nested / 'open').write_text('fixture')
        os.utime(path, ns=(n * 1000000000, n * 1000000000))
        paths.append(path)
    with patch.object(module.shutil, 'which', return_value=None):
        module.cleanup(root, 1, '/fixture/repo', os.getuid())
    assert all(p.exists() for p in paths)
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'in_use', return_value=False), \
            patch.object(module.gate_safety, 'contains_gate', side_effect=lambda p: p == paths[0]), \
            patch.object(module.shutil, 'rmtree') as remove:
        remove.avoids_symlink_attacks = True
        module.cleanup(root, 1, '/fixture/repo', os.getuid())
        assert [call.args[0] for call in remove.call_args_list] == [paths[1]]
    assert all(p.exists() for p in paths)
    def failed_log(_):
        raise OSError('fixture log failure')
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'in_use', return_value=False):
        module.cleanup_safe(root, 1, '/fixture/repo', os.getuid(), failed_log)
    assert all(p.exists() for p in paths)
    if module.shutil.which('fuser'):
        proc = subprocess.Popen([sys.executable, '-I', '-c', 'import sys,time; f=open(sys.argv[1]); print("ready",flush=True); time.sleep(30)', str(paths[0] / 'data/open')], stdout=subprocess.PIPE, text=True)
        try:
            assert proc.stdout.readline().strip() == 'ready'
            with patch.object(module, 'inspectable', return_value=True):
                module.cleanup(root, 1, '/fixture/repo', os.getuid())
            assert paths[0].exists() and not paths[1].exists() and paths[2].exists()
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            proc.stdout.close()
    with patch.object(module, 'inspectable', return_value=False):
        module.cleanup(root, 1, '/fixture/repo', os.getuid())
    assert paths[0].exists()
    with patch.object(module, 'inspectable', return_value=True), \
            patch.object(module, 'in_use', side_effect=RuntimeError('fixture cannot inspect')):
        module.cleanup(root, 1, '/fixture/repo', os.getuid())
    assert paths[0].exists() and paths[2].exists()
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'no_mounts', return_value=False):
        module.cleanup(root, 1, '/fixture/repo', os.getuid())
    assert paths[0].exists() and paths[2].exists()
    with patch.object(module.subprocess, 'run') as run:
        run.return_value.returncode = 0
        assert module.in_use('/usr/bin/lsof', paths[0])
        run.return_value.returncode = 1
        run.return_value.stderr = ''
        assert not module.in_use('/usr/bin/lsof', paths[0])

with patch.object(module.gate_safety.os, 'walk', return_value=[('/fixture', [], ['foo.gate.lock'])]):
    assert module.gate_safety.contains_gate(Path('/fixture'))
with tempfile.TemporaryDirectory(prefix='migration-proc-stat-') as tmp:
    process = Path(tmp)
    (process / 'stat').write_text('42 (name with spaces) Z 1 2\n')
    assert module.is_zombie(process)
    (process / 'stat').write_text('42 (name with spaces) S 1 2\n')
    assert not module.is_zombie(process)
    (process / 'stat').write_text('unparseable')
    assert not module.is_zombie(process)

with tempfile.TemporaryDirectory(prefix='migration-state-repeat-') as tmp:
    root = Path(tmp)
    root.chmod(0o775)
    with patch.object(module, 'inspectable', return_value=True), patch.object(module, 'in_use', return_value=False), \
            patch.object(module.shutil, 'which', return_value='/fixture/fuser'):
        for n in range(1, 9):
            path = root / ('completed-' + f'{n:032x}')
            path.mkdir()
            (path / '.migration-state').write_text('migration-state-v1\n')
            (path / 'target.json').write_text(json.dumps({'repo': '/fixture/repo', 'uid': os.getuid()}))
            (path / 'switch-complete').write_text('ok\n')
            os.utime(path / 'switch-complete', ns=(n * 1000000000, n * 1000000000))
            (path / 'rollback-complete').write_text('immediate\n')
            (path / 'operations.log').write_text('退回開始：immediate\n')
            (path / ('rollback-attempt-' + 'a' * 32 + '.started')).write_text('started\n')
            (path / ('rollback-attempt-' + 'a' * 32 + '.completed')).write_text('ok\n')
            module.cleanup(root, 5, '/fixture/repo', os.getuid())
            assert {p.name for p in root.iterdir()} == {
                'completed-' + f'{i:032x}' for i in range(max(1, n - 4), n + 1)}
print('state retention selftest passed')
