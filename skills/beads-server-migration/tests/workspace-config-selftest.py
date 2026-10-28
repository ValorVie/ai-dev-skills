#!/usr/bin/env python3
"""Reject ambiguous workspace selectors before any bd process runs."""
import os
import sys
import tempfile
import json
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import switch

with tempfile.TemporaryDirectory(prefix='migration-config-') as temporary:
    root = Path(temporary)
    home, xdg, beads = root / 'home', root / 'xdg', root / 'repo/.beads'
    home.mkdir()
    xdg.mkdir()
    beads.mkdir(parents=True)
    project = beads / 'config.yaml'
    project.write_text('sync.remote: local\n')
    candidates = (home / '.beads/config.yaml', xdg / 'bd/config.yaml', home / '.config/bd/config.yaml')
    with patch.dict(os.environ, {'HOME': str(home), 'XDG_CONFIG_HOME': str(xdg)}, clear=True):
        switch.reject_workspace_overrides(beads)
        for path in (beads / 'config.local.yaml', project, *candidates):
            path.parent.mkdir(parents=True, exist_ok=True)
            previous = path.read_bytes() if path.exists() else None
            path.write_text('db: /wrong/workspace\n')
            try:
                switch.reject_workspace_overrides(beads)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('unsafe selector accepted: ' + str(path))
            if previous is None:
                path.unlink()
            else:
                path.write_bytes(previous)
        unreadable = candidates[-1]
        unreadable.write_text('other: value\n')
        original_read = Path.read_bytes
        def denied(path):
            if path == unreadable:
                raise PermissionError('fixture denied')
            return original_read(path)
        with patch.object(Path, 'read_bytes', denied):
            try:
                switch.reject_workspace_overrides(beads)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('unreadable user config accepted')
        unreadable.unlink()
        (beads / 'metadata.json').write_text(json.dumps({'dolt_mode': 'embedded', 'dolt_database': 'sample'}))
        switch.CONFIG = {'bd': '/fixture/bd', 'dolt': '/fixture/dolt', 'database': 'sample'}
        seen = []
        def fake_run(args, **kwargs):
            seen.append((args, kwargs['env']))
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(switch.subprocess, 'run', fake_run):
            switch.run(['bd', 'list'], beads.parent, dict(os.environ))
            switch.helper('snapshot.py', ['--bd', 'bd', '--out', root / 'out'], beads.parent, dict(os.environ))
        assert len(seen) == 2 and all(env['BEADS_DIR'] == str(beads.resolve()) for _, env in seen)
        assert seen[0][0][0] == '/fixture/bd' and 'snapshot.py' in seen[1][0][1]
        location = {'path': str(beads), 'database_path': str(beads / 'embeddeddolt')}
        with patch.object(switch, 'run', return_value=json.dumps(location)):
            switch.verify_scratch_location(beads.parent, dict(os.environ))
        for key in location:
            wrong = dict(location, **{key: str(root / 'other')})
            with patch.object(switch, 'run', return_value=json.dumps(wrong)):
                try:
                    switch.verify_scratch_location(beads.parent, dict(os.environ))
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('wrong readback accepted: ' + key)
print('workspace config selftest passed')
