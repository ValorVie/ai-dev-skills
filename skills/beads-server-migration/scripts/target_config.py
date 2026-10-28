"""Load the explicit target for a migration; loading never changes the target."""
import grp
import json
import os
import pwd
import re
import subprocess
from pathlib import Path


def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('設定檔必須是一般檔案')
    data = json.loads(path.read_text(encoding='utf-8'))
    keys = {'hostname', 'account', 'repo', 'state', 'port', 'database', 'prefix',
            'service', 'group', 'keep', 'bd', 'dolt', 'docker_fixture'}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError('設定欄位缺漏或多出欄位')
    for key in keys - {'port', 'keep', 'docker_fixture'}:
        if not isinstance(data[key], str) or not data[key] or '\x00' in data[key]:
            raise ValueError('設定欄位格式不符：' + key)
    if type(data['port']) is not int or not 1 <= data['port'] <= 65535:
        raise ValueError('通訊埠不符')
    if type(data['keep']) is not int or data['keep'] < 1 or type(data['docker_fixture']) is not bool:
        raise ValueError('保留數或容器設定不符')
    for key in ('repo', 'state', 'bd', 'dolt'):
        value = Path(data[key])
        if not value.is_absolute() or value != value.resolve(strict=False):
            raise ValueError('路徑必須為解析後的絕對路徑：' + key)
    if not re.fullmatch(r'[A-Za-z0-9_]+', data['database']):
        raise ValueError('資料庫名稱不符')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', data['prefix']):
        raise ValueError('前綴不符')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]*\.service', data['service']):
        raise ValueError('服務名稱不符')
    return data


def execution_allowed(config, repo):
    """Require an exact target; the isolated Docker fixture is a separate case."""
    try:
        repo = Path(repo).resolve(strict=True)
        if repo != Path(config['repo']) or os.getuid() != os.geteuid():
            return False
        if pwd.getpwuid(os.getuid()).pw_name != config['account']:
            return False
        if grp.getgrnam(config['group']).gr_gid not in {os.getgid(), *os.getgroups()}:
            return False
        hostname = subprocess.run(['/usr/bin/hostname', '-s'], capture_output=True, text=True, timeout=10)
        if hostname.returncode != 0 or hostname.stdout.strip() != config['hostname']:
            return False
        if config['docker_fixture']:
            return (Path('/.dockerenv').is_file() and repo == Path('/experiment/repo')
                    and {p.name for p in Path('/sys/class/net').iterdir()} == {'lo'})
        if Path('/.dockerenv').exists() or Path('/run/.containerenv').exists():
            return False
        container = subprocess.run(['/usr/bin/systemd-detect-virt', '--container'],
                                   capture_output=True, text=True, timeout=10)
        return container.returncode == 1 and container.stdout.strip() == 'none'
    except (OSError, KeyError, ValueError, subprocess.SubprocessError):
        return False
