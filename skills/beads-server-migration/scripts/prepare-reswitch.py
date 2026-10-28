#!/usr/bin/env python3
"""Preserve the old tree before a subsequent switch; preview by default."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_safety
import permissions
import rollback
import state_retention
import switch
import target_config
from metadata_io import sha


def check_remaining(before, after):
    prefix = switch.SAVED + '/'
    if switch.SAVED not in before:
        raise RuntimeError('缺少原樹權限基線')
    expected = {key: value for key, value in before.items() if key != switch.SAVED and not key.startswith(prefix)}
    if expected != after:
        raise RuntimeError('封存後 .beads 權限或路徑漂移')


def locate_saved(source, destination, identity):
    return rollback.locate_tree(source, destination, identity)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def latest_archive(state):
    archives = sorted((p for p in state.iterdir() if state_retention.ARCHIVE.fullmatch(p.name)
                       and not p.is_symlink() and p.is_dir()
                       and (p / 'rollback-complete').is_file() and (p / 'switch-complete').is_file()),
                      key=lambda p: (p / 'switch-complete').stat().st_mtime_ns, reverse=True)
    if not archives:
        raise RuntimeError('缺少完成的事後退回紀錄')
    return archives[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reviewed', action='store_true')
    args = parser.parse_args()
    switch.configure(args.config)
    rollback.SERVICE = switch.SERVICE
    args.repo, args.state = Path(switch.CONFIG['repo']), Path(switch.CONFIG['state'])
    if args.apply != args.reviewed:
        raise ValueError('需要同時指定 --apply --reviewed')
    switch.reject_selector_environment()
    repo = args.repo.resolve(strict=True)
    if args.apply and not switch.execution_allowed(repo):
        raise RuntimeError('套用目標不是指定離線容器或設定宣告的主機與帳號')
    beads, state = repo / '.beads', args.state.absolute()
    switch.reject_workspace_overrides(beads)
    if (beads.is_symlink() or not beads.is_dir() or state != state.resolve(strict=False)
            or '.cache' in state.parts or state == beads or beads in state.parents):
        raise ValueError('無效目標或狀態目錄')
    print(f'目標={repo} 狀態={state}；封存事後退回保留的原樹，不刪除')
    switch.validate_state(state, beads)
    if beads.stat().st_uid != os.getuid():
        raise ValueError('執行帳號不符')
    if not args.apply:
        archive = latest_archive(state)
        print(f'預覽來源={beads / switch.SAVED} 目的地={archive / "reswitch-saved-tree"}')
        print('套用前核對服務 inactive／disabled、程序、資料樹身分、gate 與權限；失敗保留現狀')
        return 0
    if not state_retention.inspectable():
        raise RuntimeError('無法確認封存所需程序可見性')
    preliminary = latest_archive(state)
    with switch.workspace_gate(repo):
        for path in (beads / switch.SAVED, preliminary / 'reswitch-saved-tree'):
            if path.is_symlink():
                raise RuntimeError('資料樹不可為符號連結')
            if path.exists():
                if not path.is_dir():
                    raise RuntimeError('資料樹不可用')
                rollback.ensure_tree_idle(path)
    lock_path = state / '.operation.lock'
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ValueError('操作鎖不可用')
    with lock_path.open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (state / 'current').exists() or (state / 'current').is_symlink():
            raise RuntimeError('已有進行中的切換')
        archive = latest_archive(state)
        target_file = archive / 'target.json'
        markers = [target_file, archive / '.migration-state', archive / 'switch-complete',
                   archive / 'rollback-complete', archive / 'permissions.json']
        info = archive.stat()
        if (any(p.is_symlink() or not p.is_file() for p in markers)
                or info.st_uid != os.getuid() or info.st_gid != target_config.group_id(switch.CONFIG) or info.st_dev != state.stat().st_dev
                or (archive / '.migration-state').read_bytes() != b'migration-state-v1\n'
                or (archive / 'switch-complete').read_bytes() != b'ok\n'
                or (archive / 'rollback-complete').read_bytes() != b'after-write\n'):
            raise RuntimeError('最新紀錄不是完成的事後退回')
        target_bytes = target_file.read_bytes()
        target = json.loads(target_bytes)
        switch.check_target_config(target)
        if target.get('repo') != str(repo) or target.get('uid') != os.getuid():
            raise RuntimeError('紀錄目標或執行帳號不符')
        active = subprocess.run(['systemctl', '--user', 'is-active', switch.SERVICE], capture_output=True, text=True)
        if active.returncode != 3 or active.stdout.strip() != 'inactive':
            raise RuntimeError('服務不是 inactive')
        rollback.verify_disabled()
        source, destination = beads / switch.SAVED, archive / 'reswitch-saved-tree'
        intent, baseline_file = archive / 'reswitch-intent.json', archive / 'reswitch-before.json'
        completion = archive / 'reswitch-complete'
        if any(p.is_symlink() for p in (source, destination, intent, baseline_file, completion)):
            raise RuntimeError('封存路徑不可為符號連結')
        with switch.workspace_gate(repo):
            if not intent.exists():
                if not source.is_dir() or destination.exists() or completion.exists():
                    raise RuntimeError('缺少可驗證的原樹')
                rollback.verify_completed(beads, archive, target, 'after-write')
                before = permissions.capture(beads)
                baseline = json.loads((archive / 'permissions.json').read_text())
                errors, _ = permissions.compare_later(baseline, before, os.getuid(), target_config.group_id(switch.CONFIG), switch.SAVED)
                if errors:
                    raise RuntimeError('事後退回權限已漂移')
                baseline_bytes = (json.dumps(before, sort_keys=True, indent=2) + '\n').encode()
                rollback.ensure_durable(baseline_file, baseline_bytes)
                plan = {'tree': rollback.tree_identity(source), 'archive': rollback.tree_identity(archive),
                        'source': str(source), 'destination': str(destination),
                        'baseline_sha': sha(baseline_bytes), 'target_sha': sha(target_bytes)}
                rollback.ensure_durable(intent, (json.dumps(plan, sort_keys=True) + '\n').encode())
            if not intent.is_file() or not baseline_file.is_file():
                raise RuntimeError('封存檢查點不完整')
            data = intent.read_bytes()
            plan = json.loads(data)
            if (not isinstance(plan, dict) or set(plan) != {'tree', 'archive', 'source', 'destination', 'baseline_sha', 'target_sha'}
                    or plan['archive'] != rollback.tree_identity(archive) or plan['target_sha'] != sha(target_bytes)
                    or plan['source'] != str(source) or plan['destination'] != str(destination)
                    or plan['baseline_sha'] != sha(baseline_file.read_bytes())):
                raise RuntimeError('封存檢查點不符')
            saved = locate_saved(source, destination, plan['tree'])
            rollback.verify_completed(beads, archive, target, 'after-write', saved_override=saved)
            before = json.loads(baseline_file.read_text())
            saved_expected = {('.' if key == switch.SAVED else key[len(switch.SAVED) + 1:]): value
                              for key, value in before.items()
                              if key == switch.SAVED or key.startswith(switch.SAVED + '/')}
            if permissions.capture(saved) != saved_expected:
                raise RuntimeError('原樹權限與檢查點不符')
            current = permissions.capture(beads)
            if saved == source:
                if current != before or completion.exists():
                    raise RuntimeError('封存前 .beads 狀態不符')
            else:
                check_remaining(before, current)
            rollback.ensure_tree_idle(saved)
            if gate_safety.contains_gate(saved):
                raise RuntimeError('原樹含 gate 檔，不能搬移')
            if rollback.tree_identity(saved) != plan['tree']:
                raise RuntimeError('原樹身分在檢查期間改變')
            if saved == source:
                source.rename(destination)
            sync_dir(beads)
            sync_dir(archive)
            if rollback.tree_identity(destination) != plan['tree'] or permissions.capture(destination) != saved_expected:
                raise RuntimeError('封存後原樹身分或權限不符')
            check_remaining(before, permissions.capture(beads))
            rollback.ensure_durable(completion, (sha(data) + '\n').encode())
        print(f'原樹封存於 {destination}；inode={plan["tree"][1]}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'封存停止：{error}', file=sys.stderr)
        sys.exit(1)
