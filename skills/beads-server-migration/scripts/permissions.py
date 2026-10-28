#!/usr/bin/env python3
"""Record and compare a Beads tree's numeric ownership, mode and ACLs."""
import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


def capture(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Beads root must be a real directory")
    result = {}

    def visit(path, relative):
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            kind, acl = "symlink", os.readlink(path)
        elif stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
            kind = "dir" if stat.S_ISDIR(info.st_mode) else "file"
            proc = subprocess.run(["getfacl", "-c", "-n", "-P", "--", str(path)],
                                  capture_output=True, text=True, check=True)
            acl = proc.stdout
        else:
            raise ValueError(f"unsupported file type: {relative}")
        result[relative] = {"mode": mode, "uid": info.st_uid, "gid": info.st_gid,
                            "kind": kind, "acl": acl}
        if kind == "dir":
            with os.scandir(path) as entries:
                for entry in sorted(entries, key=lambda e: e.name):
                    child = entry.name if relative == "." else relative + "/" + entry.name
                    visit(path / entry.name, child)

    visit(root, ".")
    return result


def default_acl(value):
    return tuple(line for line in value["acl"].splitlines() if line.startswith("default:"))


def root_errors(before, after, owner, group, paths):
    baseline = before.get(".")
    if baseline is None or not default_acl(baseline):
        return ["baseline root has no default ACL"]
    errors = []
    for path in paths:
        if path not in after:
            continue
        value = after[path]
        reference = before.get(path, baseline)
        if (value["kind"] != "dir" or value["mode"] != 0o2770 or value["uid"] != owner
                or value["gid"] != group or default_acl(value) != default_acl(reference)):
            errors.append(f"invalid protected directory: {path}")
    return errors


def compare(before, after, owner, saved, group):
    mapped = {}
    for path, value in after.items():
        if saved and (path == saved or path.startswith(saved + "/")):
            path = "embeddeddolt" + path[len(saved):]
        if path in mapped:
            return [f"duplicate mapped path: {path}"], []
        mapped[path] = value
    errors, added = root_errors(before, mapped, owner, group, (".", "embeddeddolt", "dolt")), []
    for path, value in before.items():
        if path not in mapped:
            errors.append(f"missing: {path}")
        elif value != mapped[path]:
            errors.append(f"permission changed: {path}")
    for path in sorted(mapped.keys() - before.keys()):
        value = mapped[path]
        is_dolt = path == "dolt" or path.startswith("dolt/")
        is_gate = path.rsplit("/", 1)[-1].endswith(".gate.lock")
        if value["uid"] == owner and value["gid"] == group and value["kind"] != "symlink" and (
            is_dolt or (is_gate and value["kind"] == "file" and value["mode"] == 0o600)
        ):
            added.append({"path": path, **value})
        else:
            errors.append(f"unexpected addition: {path}")
    return errors, added


def compare_immediate(before, after, owner=None):
    errors = [f"missing: {p}" for p in before.keys() - after.keys()]
    for p in after.keys() - before.keys():
        value = after[p]
        if not (owner is not None and '/' not in p and p.endswith('.gate.lock')
                and value['kind'] == 'file' and value['uid'] == owner and value['mode'] == 0o600):
            errors.append(f"unexpected addition: {p}")
    errors += [f"permission changed: {p}" for p in before.keys() & after.keys() if before[p] != after[p]]
    return sorted(errors)


def compare_later(before, after, owner, group, saved):
    if not saved:
        return ["saved embedded tree is required"], []
    original = {p: v for p, v in before.items() if p == "embeddeddolt" or p.startswith("embeddeddolt/")}
    retained = {"embeddeddolt" + p[len(saved):]: v for p, v in after.items()
                if p == saved or p.startswith(saved + "/")}
    errors = ["retained " + e for e in compare_immediate(original, retained)]
    top_before = {p: v for p, v in before.items() if p not in original}
    top_after = {p: v for p, v in after.items() if not (
        p == saved or p.startswith(saved + "/") or p == "embeddeddolt" or p.startswith("embeddeddolt/")
    )}
    top_errors, added = compare(top_before, top_after, owner, "", group)
    errors.extend(top_errors)
    if "embeddeddolt" not in original or "embeddeddolt" not in after:
        return errors + ["embedded root missing"], added
    default = default_acl(original["embeddeddolt"])
    if not default:
        errors.append("baseline embedded root has no default ACL")
    errors.extend(root_errors(before, after, owner, group, ("embeddeddolt",)))
    for path, value in after.items():
        if path != "embeddeddolt" and not path.startswith("embeddeddolt/"):
            continue
        if path in original:
            if any(value[key] != original[path][key] for key in ("mode", "acl", "kind")):
                errors.append(f"rebuilt permission changed: {path}")
        else:
            if value["uid"] != owner or value["gid"] != group or value["kind"] not in ("file", "dir"):
                errors.append(f"invalid rebuilt addition: {path}")
            added.append({"path": path, **value})
    return sorted(errors), added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--owner", type=int, required=True)
    parser.add_argument("--saved", default="")
    parser.add_argument("--phase", choices=("switch", "immediate", "later"), default="switch")
    parser.add_argument("--group", type=int, required=True)
    args = parser.parse_args()
    if args.saved and ("/" in args.saved or not args.saved.startswith("embeddeddolt.")):
        raise ValueError("invalid saved embedded directory")
    current = capture(args.root)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(current, output, ensure_ascii=True, sort_keys=True, indent=2)
        output.write("\n")
    if args.expected:
        before = json.loads(args.expected.read_text(encoding="utf-8"))
        if args.phase == "immediate":
            errors, added = compare_immediate(before, current, args.owner), []
        elif args.phase == "later":
            errors, added = compare_later(before, current, args.owner, args.group, args.saved)
        else:
            errors, added = compare(before, current, args.owner, args.saved, args.group)
        for entry in added:
            print(f"允許新增 {entry['path']} mode={entry['mode']:04o} uid={entry['uid']} gid={entry['gid']}")
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            return 1
        print(f"權限一致；允許新增 {len(added)} 項")
    else:
        print(f"已保存權限基線：{len(current)} 項")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"權限檢查失敗：{error}", file=sys.stderr)
        sys.exit(1)
