#!/usr/bin/env python3
"""Check the configured target, selector guards, previews, and checkpoint binding."""
import grp
import importlib.util
import json
import os
import pwd
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
import switch
import rollback

spec = importlib.util.spec_from_file_location('reswitch', scripts / 'prepare-reswitch.py')
reswitch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reswitch)

with tempfile.TemporaryDirectory(prefix='migration-entry-') as temporary:
    root = Path(temporary).resolve()
    proc_comm = root / 'comm'
    for name, should_block in (('bd', True), ('bd-1.3', True), ('python', False)):
        proc_comm.write_text(name + '\n')
        with patch.object(Path, 'glob', return_value=[proc_comm]):
            try:
                switch.no_bd()
            except RuntimeError:
                assert should_block, name
            else:
                assert not should_block, 'active process was not rejected: ' + name
    repo, state = root / 'repo', root / 'state'
    (repo / '.beads').mkdir(parents=True)
    metadata = repo / '.beads' / 'metadata.json'
    metadata.write_text(json.dumps({'dolt_mode': 'embedded', 'dolt_database': 'sample_db',
                                    'project_id': 'fixture-project'}))
    (repo / '.beads/config.yaml').write_text('# fixture\n')
    for name in ('bd', 'dolt'):
        executable = root / name
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
    config = {'hostname': socket.gethostname().split('.')[0],
              'account': pwd.getpwuid(os.getuid()).pw_name, 'repo': str(repo), 'state': str(state),
              'port': 16021, 'database': 'sample_db', 'prefix': 'sample_db', 'service': 'sample.service',
              'group': grp.getgrgid(os.getgid()).gr_name, 'keep': 5, 'bd': str(root / 'bd'),
              'dolt': str(root / 'dolt'), 'docker_fixture': False}
    config_file = root / 'target.json'
    config_file.write_text(json.dumps(config))
    switch.configure(config_file)
    config_yaml = repo / '.beads/config.yaml'
    for invalid in ('sync.remote: a\nsync.remote: b\n', 'sync:\n  remote: old\n'):
        config_yaml.write_text(invalid)
        for flags in ([], ['--apply', '--reviewed']):
            with patch.dict(os.environ, {}, clear=True), patch.object(switch, 'execution_allowed', return_value=True), \
                    patch.object(switch.state_retention, 'inspectable', return_value=True), \
                    patch.object(sys, 'argv', ['tool', '--config', str(config_file), *flags]):
                try:
                    switch.main()
                except ValueError as error:
                    assert 'config.yaml' in str(error)
                else:
                    raise AssertionError('unsafe config accepted by entrypoint')
            assert config_yaml.read_text() == invalid and not state.exists()
    config_yaml.write_text('# fixture\n')
    digest = switch.config_digest()
    checkpoint = {'config_sha256': digest, 'repo': str(repo), 'port': 16021,
                  'uid': os.getuid(), 'keep': 5}
    switch.check_target_config(checkpoint)
    for field, value in (('port', 16022), ('repo', '/wrong'), ('uid', os.getuid() + 1), ('keep', 6)):
        try:
            switch.check_target_config(dict(checkpoint, **{field: value}))
        except ValueError:
            pass
        else:
            raise AssertionError('changed checkpoint accepted: ' + field)
    for field in ('port', 'uid', 'keep'):
        try:
            switch.check_target_config(dict(checkpoint, **{field: True}))
        except ValueError:
            pass
        else:
            raise AssertionError('boolean checkpoint accepted: ' + field)
    for field, value in (('port', 16022), ('service', 'other.service'),
                         ('state', str(root / 'other')), ('keep', 6)):
        changed = dict(config, **{field: value})
        config_file.write_text(json.dumps(changed))
        switch.configure(config_file)
        try:
            switch.check_target_config(checkpoint)
        except ValueError:
            pass
        else:
            raise AssertionError('changed configuration accepted: ' + field)
    config_file.write_text(json.dumps(dict(config, database='other', prefix='other')))
    switch.configure(config_file)
    try:
        switch.check_target_config(checkpoint)
    except ValueError:
        pass
    else:
        raise AssertionError('changed database configuration accepted')
    config_file.write_text(json.dumps(config))
    switch.configure(config_file)
    for name in switch.BD_SELECTOR_ENV:
        with patch.dict(os.environ, {name: 'untrusted-value'}, clear=True):
            try:
                switch.reject_selector_environment()
            except RuntimeError as error:
                assert name in str(error) and 'untrusted-value' not in str(error)
            else:
                raise AssertionError('selector accepted: ' + name)
            for module, extra in ((switch, []), (rollback, ['--immediate']),
                                  (rollback, ['--after-write']), (reswitch, [])):
                with patch.object(sys, 'argv', ['tool', '--config', str(config_file), *extra,
                                                '--apply', '--reviewed']):
                    try:
                        module.main()
                    except RuntimeError as error:
                        assert name in str(error)
                    else:
                        raise AssertionError('selector accepted by entrypoint')
    with patch.dict(os.environ, {}, clear=True):
        assert switch.child_environment({'BEADS_DIR': '/wrong', 'OTHER': 'yes'}) == {'OTHER': 'yes'}
        assert switch.child_environment({'BEADS_DOLT_SERVER_PORT': '16021'}) == {'BEADS_DOLT_SERVER_PORT': '16021'}
        try:
            switch.child_environment({'BEADS_DOLT_SERVER_PORT': '16022'})
        except ValueError:
            pass
        else:
            raise AssertionError('unexpected port accepted')
        before = metadata.read_bytes()
        with patch.object(sys, 'argv', ['tool', '--config', str(config_file)]):
            assert switch.main() == 0
        assert metadata.read_bytes() == before and not state.exists()
        for module, extra in ((switch, []), (rollback, ['--immediate']), (reswitch, [])):
            with patch.object(sys, 'argv', ['tool', '--config', str(config_file), *extra, '--apply', '--reviewed']), \
                 patch.object(switch, 'execution_allowed', return_value=False):
                try:
                    module.main()
                except RuntimeError as error:
                    assert '套用目標' in str(error)
                else:
                    raise AssertionError('target guard bypassed')
        assert not state.exists() and metadata.read_bytes() == before
print('entrypoints selftest passed')
