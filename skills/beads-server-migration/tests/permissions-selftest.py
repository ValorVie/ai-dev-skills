#!/usr/bin/env python3
"""Check permission comparisons without touching a real Beads directory."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("permissions", Path(__file__).resolve().parents[1] / "scripts" / "permissions.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def item(mode=0o660, uid=12001, gid=12002, acl="acl", kind="file"):
    return {"mode": mode, "uid": uid, "gid": gid, "acl": acl, "kind": kind}

old_acl = 'user::rwx\ngroup::rwx\nother::---\ndefault:user::rwx\ndefault:group::rwx\ndefault:other::---\n'
before = {".": item(0o2770, acl=old_acl, kind="dir"), "embeddeddolt": item(0o2770, acl=old_acl, kind="dir"),
          "embeddeddolt/data": item()}
after = {".": before["."], "embeddeddolt.migration-saved": before["embeddeddolt"],
         "embeddeddolt.migration-saved/data": before["embeddeddolt/data"],
         "dolt": item(0o2770, acl=old_acl, kind="dir"), "dolt/config.yaml": item(0o777),
         "dolt.gate.lock": item(0o600)}
def check(a, b, expected):
    errors, added = module.compare(a, b, 12001, "embeddeddolt.migration-saved", 12002)
    assert bool(errors) is expected, (errors, added)

check(before, after, False)
check(before, {**after, "dolt/config.yaml": item(0o777, uid=42)}, True)
check(before, {**after, "dolt/config.yaml": item(0o777, gid=42)}, True)
check(before, {**after, "dolt": item(0o2777, acl=old_acl, kind="dir")}, True)
check(before, {**after, "dolt": item(0o2770, acl="wrong", kind="dir")}, True)
check(before, {**after, "other": item()}, True)
check(before, {**after, "wrong.gate.lock": item(0o660)}, True)
check(before, {**after, "embeddeddolt.migration-saved/data": item(0o600)}, True)
check(before, {k: v for k, v in after.items() if k != "embeddeddolt.migration-saved/data"}, True)
check(before, {**after, "embeddeddolt.migration-saved/data": item(acl="changed")}, True)
assert module.compare_immediate(before, before) == []
assert module.compare_immediate(before, {**before, "new.gate.lock": item(0o600)})
assert module.compare_immediate(before, {**before, "new.gate.lock": item(0o600)}, 12001) == []
assert module.compare_immediate(before, {**before, "new.gate.lock": item(0o660)}, 12001)
assert module.compare_immediate(before, {**before, "new.gate.lock": item(0o600, uid=42)}, 12001)
assert module.compare_immediate(before, {**before, "new.gate.lock": item(0o600, kind='symlink')}, 12001)
assert module.compare_immediate(before, {**before, "embeddeddolt/new.gate.lock": item(0o600)}, 12001)
assert module.compare_immediate(before, {**before, "other": item(0o600)}, 12001)
assert module.compare_immediate(before, {**before, "embeddeddolt/data": item(0o600)})
old = {".": item(0o2770, acl=old_acl, kind="dir"), "metadata.json": item(),
       "embeddeddolt": item(0o2770, acl=old_acl, kind="dir"),
       "embeddeddolt/old": item()}
rebuilt = {".": old["."], "metadata.json": old["metadata.json"],
           "embeddeddolt.saved": old["embeddeddolt"], "embeddeddolt.saved/old": old["embeddeddolt/old"],
           "embeddeddolt": old["embeddeddolt"], "embeddeddolt/new": item(0o600),
           "dolt": item(0o2770, acl=old_acl, kind="dir"), "dolt.gate.lock": item(0o600)}
def later(b, a, bad):
    errors, _ = module.compare_later(b, a, 12001, 12002, "embeddeddolt.saved")
    assert bool(errors) is bad, errors
later(old, rebuilt, False)
later(old, {**rebuilt, "metadata.json": item(0o600)}, True)
later(old, {**rebuilt, "embeddeddolt.saved/old": item(0o600)}, True)
later(old, {**rebuilt, "embeddeddolt/new": item(0o777)}, False)
later(old, {**rebuilt, "embeddeddolt/new": item(0o600, gid=2)}, True)
later(old, {**rebuilt, "embeddeddolt": item(0o2770, acl="other", kind="dir")}, True)
later(old, {**rebuilt, "embeddeddolt": item(0o2777, acl=old_acl, kind="dir")}, True)
later(old, {**rebuilt, "embeddeddolt/old": item(0o600)}, True)
with tempfile.TemporaryDirectory(prefix="migration-permissions-") as directory:
    root = Path(directory)
    root.chmod(0o775)
    (root / "file").write_text("data", encoding="utf-8")
    baseline = module.capture(root)
    assert not module.compare_immediate(baseline, module.capture(root))
    (root / "file").chmod(0o600)
    assert module.compare_immediate(baseline, module.capture(root))
    expected = root.parent / (root.name + '-baseline.json')
    output = root.parent / (root.name + '-actual.json')
    try:
        expected.write_text(json.dumps(baseline))
        result = subprocess.run([sys.executable, str(spec.origin), '--root', str(root),
                                 '--out', str(output), '--expected', str(expected),
                                 '--owner', str(os.getuid()), '--group', str(os.getgid()), '--phase', 'immediate'],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 1 and 'permission changed: file' in result.stderr
    finally:
        expected.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
print("permissions selftest passed")
