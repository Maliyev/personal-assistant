import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path):
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                name, value = line.split('=', 1)
                os.environ.setdefault(name.strip(), value.strip().strip('\"\''))


def load_config(path=None):
    path = Path(path or ROOT / 'config' / 'config.json')
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    config['runtime'].setdefault('tier1_enabled', True)
    if type(config['runtime']['tier1_enabled']) is not bool:
        raise ValueError('runtime.tier1_enabled must be boolean')
    positive = {
        'runtime': ('max_tool_steps', 'request_timeout_seconds', 'background_workers', 'background_queue_limit'),
        'retry': ('max_attempts', 'max_wait_seconds', 'base_backoff_seconds', 'max_backoff_seconds'),
        'scheduler': ('tick_seconds',),
        'memory': ('periodic_seconds',),
        'workspace': ('max_read_bytes',),
    }
    for section, fields in positive.items():
        for field in fields:
            value = config[section][field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f'{section}.{field} must be positive')
    for field in ('max_tool_steps', 'background_workers', 'background_queue_limit'):
        if type(config['runtime'][field]) is not int:
            raise ValueError(f'runtime.{field} must be an integer')
    if type(config['retry']['max_attempts']) is not int:
        raise ValueError('retry.max_attempts must be an integer')
    if config['runtime']['max_tool_steps'] > 10:
        raise ValueError('V0 permits at most 10 tool steps')
    if type(config['retry']['jitter']) is not bool:
        raise ValueError('retry.jitter must be boolean')
    if type(config['memory']['slow_enabled']) is not bool:
        raise ValueError('memory.slow_enabled must be boolean')
    if config['memory']['slow_enabled']:
        raise ValueError('Slow memory is a V0 stub; keep slow_enabled=false')
    if type(config['workspace']['max_read_bytes']) is not int:
        raise ValueError('workspace.max_read_bytes must be an integer')
    for field in ('database', 'workspace', 'agent_seeds'):
        if not isinstance(config['paths'][field], str) or not config['paths'][field]:
            raise ValueError(f'paths.{field} must be a nonempty string')
    return config
