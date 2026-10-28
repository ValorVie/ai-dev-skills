#!/usr/bin/env python3
"""Exercise target identity checks without touching a Beads workspace."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import target_config


class TargetConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.config = {'hostname': 'test-host', 'account': 'operator', 'repo': str(root),
                       'state': str(root / 'state'), 'port': 16021, 'database': 'sample_db',
                       'prefix': 'sample', 'service': 'sample.service', 'group': 'team',
                       'keep': 5, 'bd': '/usr/bin/bd', 'dolt': '/usr/bin/dolt',
                       'docker_fixture': False}
        self.path = root / 'target.json'

    def write(self):
        self.path.write_text(json.dumps(self.config))
        return target_config.load(self.path)

    def test_valid_and_invalid_config(self):
        self.assertEqual(self.write(), self.config)
        for key, value in [('port', True), ('keep', 0), ('repo', '/tmp/../tmp'),
                           ('database', '../bad'), ('database', 'bad-name'), ('service', 'bad/path.service')]:
            old = self.config[key]
            self.config[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.write()
            self.config[key] = old
        self.config['unexpected'] = 'x'
        with self.assertRaises(ValueError):
            self.write()

    def test_identity_and_non_container_gate(self):
        config = self.write()
        results = [SimpleNamespace(returncode=0, stdout='test-host\n'),
                   SimpleNamespace(returncode=1, stdout='none\n')]
        real_exists = Path.exists
        def exists(path):
            return False if str(path) in ('/.dockerenv', '/run/.containerenv') else real_exists(path)
        with patch.object(target_config.os, 'getuid', return_value=1234), \
             patch.object(target_config.os, 'geteuid', return_value=1234), \
             patch.object(target_config.os, 'getgid', return_value=2468), \
             patch.object(target_config.os, 'getgroups', return_value=[]), \
             patch.object(target_config.pwd, 'getpwuid', return_value=SimpleNamespace(pw_name='operator')), \
             patch.object(target_config.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=2468)), \
             patch.object(Path, 'exists', exists), \
             patch.object(target_config.subprocess, 'run', side_effect=results):
            self.assertTrue(target_config.execution_allowed(config, config['repo']))
        self.assertFalse(target_config.execution_allowed(config, '/'))
        with patch.object(target_config.os, 'getuid', return_value=1), \
             patch.object(target_config.os, 'geteuid', return_value=2):
            self.assertFalse(target_config.execution_allowed(config, config['repo']))


if __name__ == '__main__':
    unittest.main()
