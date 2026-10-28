#!/usr/bin/env python3.14
"""Suspend immediately after the real saved-tree rename in the test container."""
import importlib.util
import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch

if not Path('/.dockerenv').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise SystemExit('offline Docker fixture required')
spec = importlib.util.spec_from_file_location('reswitch', '/skill/scripts/prepare-reswitch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
real_rename = Path.rename

def rename(path, target):
    result = real_rename(path, target)
    if path == Path('/experiment/repo/.beads/embeddeddolt.migration-saved'):
        with Path('/experiment/reswitch-fault').open('xb') as stream:
            stream.write(b'reached\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.kill(os.getpid(), signal.SIGSTOP)
    return result

sys.argv = ['/skill/scripts/prepare-reswitch.py', *sys.argv[1:]]
with patch.object(Path, 'rename', rename):
    sys.exit(module.main())
