#!/usr/bin/env python3
"""Check conservative remote isolation and fail-closed configuration handling."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import switch

remote = 'file:///tmp/local%20remote.git'
for source in ('sync.remote: old\nexport:\n  auto: true\n', '# empty\n', 'other: value'):
    result = switch.isolate_sync_remote(source, remote)
    assert result.count('sync.remote:') == 1 and remote in result
    assert switch.isolate_sync_remote(result, remote) == result

for source in ('sync.remote: a\nsync.remote: b\n', 'sync:\n  remote: old\n',
               'sync: {remote: old}\n', '"sync.remote": old\n',
               'sync.remote: |\n  old\n', 'other: [unterminated\n',
               '---\nsync.remote: old\n', 'other: &alias value\n'):
    try:
        switch.isolate_sync_remote(source, remote)
    except ValueError as error:
        assert 'config.yaml' in str(error)
    else:
        raise AssertionError('unsafe config accepted: ' + source)

print('sync config isolation passed')
