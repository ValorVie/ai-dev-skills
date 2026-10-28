#!/usr/bin/env python3
"""Reject ambiguous workspace selectors before any bd process runs."""
import os
import sys
import tempfile
import json
import grp
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
    project.write_text('# fixture\n')
    candidates = (home / '.beads/config.yaml', xdg / 'bd/config.yaml', home / '.config/bd/config.yaml')
    with patch.dict(os.environ, {'HOME': str(home), 'XDG_CONFIG_HOME': str(xdg)}, clear=True):
        switch.reject_workspace_overrides(beads)
        for path in (project, *candidates):
            path.parent.mkdir(parents=True, exist_ok=True)
            original = path.read_bytes() if path.exists() else None
            for unsafe in ('dolt.shared-server: true\n', 'dolt:\n  shared-server: true\n',
                           'dolt.future-option: value\n', 'dolt:\n  max-conns: 4\n  shared-server: true\n',
                           'dolt: 1\n', 'dolt:\n', 'dolt:\n  max-conns: 4\ndolt.max-conns: 5\n',
                           'routing.mode: auto\n',
                           'contributor:\n  planning_repo: /other\n',
                           'routing:\n  default: /other\n', 'backup.git-repo: /other\n',
                           'backup:\n  git-push: true\n', 'federation.remote: remote\n',
                           'repos.primary: /other\n', 'external_projects:\n  other: /other\n',
                           'sync.git-remote: remote\n', 'sync.remote: remote\n',
                           'sync:\n  remote: remote\n', 'no-push: true\n'):
                path.write_text(unsafe)
                try:
                    switch.reject_workspace_overrides(beads)
                except (ValueError, RuntimeError):
                    pass
                else:
                    raise AssertionError('unsafe setting accepted: ' + unsafe)
            for safe in ('dolt.max-conns: 4\n', 'dolt:\n  max-conns: 4\n'):
                path.write_text(safe)
                switch.reject_workspace_overrides(beads)
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)
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
        state = root / 'state'
        state.mkdir(mode=0o2770)
        state.chmod(0o2770)
        work = state / 'current'
        work.mkdir()
        scratch_name = 'migration-scratch-' + 'a' * 32
        scratch = state / scratch_name
        scratch.mkdir(mode=0o2770)
        scratch.chmod(0o2770)
        (work / 'scratch-id').write_text(scratch_name)
        (work / 'target.json').write_text('fixture')
        (scratch / 'target.json').write_text('fixture')
        (scratch / '.migration-scratch').write_text('migration-scratch-v1\n')
        scratch_beads = scratch / 'backup-repo/.beads'
        scratch_beads.mkdir(parents=True)
        scratch_config = scratch_beads / 'config.yaml'
        switch.CONFIG = {'state': str(state), 'group': grp.getgrgid(os.getgid()).gr_name}
        scratch_config.write_text('sync.remote: ' + json.dumps((work / 'remote.git').as_uri()) + '\n')
        switch.reject_workspace_overrides(scratch_beads)
        scratch_config.write_text('sync.remote: "file:///other.git"\n')
        try:
            switch.reject_workspace_overrides(scratch_beads)
        except ValueError:
            pass
        else:
            raise AssertionError('unexpected scratch remote accepted')
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
        assert all(env['BD_ROUTING_MODE'] == 'explicit' and env['BD_ROUTING_DEFAULT'] == '.' for _, env in seen)
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
    for variable in ('BD_DOLT_AUTO_PUSH', 'BD_ROUTING_DEFAULT', 'BEADS_ROUTING_MODE',
                     'BD_BACKUP_GIT_REPO', 'BD_EXTERNAL_PROJECTS'):
        with patch.dict(os.environ, {variable: ''}, clear=True):
            try:
                switch.reject_selector_environment()
            except RuntimeError:
                pass
            else:
                raise AssertionError('unsafe environment accepted: ' + variable)
print('workspace config selftest passed')
