#!/usr/bin/env python3
"""Exercise proc fallback and fail-closed process visibility for both accounts."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import state_retention

with tempfile.TemporaryDirectory(prefix='migration-proc-') as temporary:
    root = Path(temporary)
    (root / 'self').mkdir()
    (root / 'self/mountinfo').write_text('1 1 0:1 / /proc rw - proc proc rw\n')
    def process(pid, uid, name, command):
        entry = root / str(pid)
        (entry / 'fd').mkdir(parents=True)
        (entry / 'status').write_text(f'Name:\t{name}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n')
        (entry / 'stat').write_text(f'{pid} ({name}) S 1 0 0\n')
        (entry / 'comm').write_text(name + '\n')
        (entry / 'cmdline').write_bytes(command)
        (entry / 'maps').write_text('map\n')
        for part in ('cwd', 'root', 'exe'):
            (entry / part).symlink_to('/dev/null')
        return entry
    own = process(100, 12001, 'worker', b'/usr/bin/worker\0')
    other = process(101, 2001, 'sleep', b'/usr/bin/sleep\0')
    real_scandir = os.scandir
    def deny_foreign(path):
        if Path(path) == other / 'fd':
            raise PermissionError('foreign fixture')
        return real_scandir(path)
    with patch.object(state_retention.os, 'getuid', return_value=12001), \
            patch.object(state_retention.os, 'scandir', side_effect=deny_foreign):
        assert state_retention.inspectable(root)
        (other / 'comm').write_text('bd\n')
        assert not state_retention.inspectable(root)
        (other / 'comm').write_text('sleep\n')
        (other / 'cmdline').write_bytes(b'/usr/bin/dolt\0')
        assert not state_retention.inspectable(root)
        (other / 'cmdline').write_bytes(b'/usr/bin/sleep\0')
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if path == other / 'comm':
                raise PermissionError('foreign fixture')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read_text):
            assert not state_retention.inspectable(root)
    def deny_own(path):
        if Path(path) == own / 'fd':
            raise PermissionError('own fixture')
        return real_scandir(path)
    with patch.object(state_retention.os, 'getuid', return_value=12001), \
            patch.object(state_retention.os, 'scandir', side_effect=deny_own):
        assert state_retention.inspectable(root)
        for name in ('bd', 'bd-worker', 'dolt', 'dolt-server'):
            (own / 'comm').write_text(name + '\n')
            assert not state_retention.inspectable(root), name
        (own / 'comm').write_text('worker\n')
        (own / 'cmdline').write_bytes(b'/usr/bin/bd\0')
        assert not state_retention.inspectable(root)
        (own / 'cmdline').write_bytes(b'/usr/bin/worker\0')
        original = Path.read_text
        def read_own_comm(path, *args, **kwargs):
            if path == own / 'comm':
                raise PermissionError('own fixture')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read_own_comm):
            assert not state_retention.inspectable(root)
        original_bytes = Path.read_bytes
        def read_own_cmdline(path, *args, **kwargs):
            if path == own / 'cmdline':
                raise PermissionError('own fixture')
            return original_bytes(path, *args, **kwargs)
        with patch.object(Path, 'read_bytes', read_own_cmdline):
            assert not state_retention.inspectable(root)
        (own / 'comm').write_text('dolt\n')
        (own / 'stat').write_text('100 (dolt) Z 1 0 0\n')
        assert state_retention.inspectable(root), 'a dead process cannot hold a data tree open'
        (own / 'comm').write_text('worker\n')
        (own / 'stat').write_text('100 (worker) S 1 0 0\n')
    (own / 'fd/3').symlink_to('/dev/null')
    real_readlink = os.readlink
    def deny_own_fd(path, *args, **kwargs):
        if Path(path) == own / 'fd/3':
            raise PermissionError('own fd fixture')
        return real_readlink(path, *args, **kwargs)
    with patch.object(state_retention.os, 'getuid', return_value=12001), \
            patch.object(state_retention.os, 'readlink', side_effect=deny_own_fd):
        assert state_retention.inspectable(root)
        (own / 'comm').write_text('dolt\n')
        assert not state_retention.inspectable(root)
        (own / 'comm').write_text('worker\n')
    data = root / 'data'
    data.mkdir()
    def result(pids, error):
        return SimpleNamespace(returncode=0, stdout=pids, stderr=error)
    with patch.object(state_retention.subprocess, 'run', return_value=result('123', f'{data}:c\n')):
        assert not state_retention.in_use('/usr/bin/fuser', data, {123})
    with patch.object(state_retention.subprocess, 'run', return_value=result('123 456', f'{data}:c\n')):
        assert state_retention.in_use('/usr/bin/fuser', data, {123})
    with patch.object(state_retention.subprocess, 'run', return_value=result('123', 'Permission denied\n')):
        try:
            state_retention.in_use('/usr/bin/fuser', data, {123})
        except RuntimeError:
            pass
        else:
            raise AssertionError('unrecognized fuser error accepted')
print('process visibility selftest passed')
