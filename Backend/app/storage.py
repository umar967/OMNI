"""Atomic JSON storage for the local presentation app."""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.getenv('OMNI_DATA_DIR', Path(__file__).resolve().parents[1])).resolve()
LOCK = threading.RLock()

def now():
    return datetime.now(timezone.utc).isoformat()

def identifier():
    return uuid.uuid4().hex

def directory(name):
    path = ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path

def safe_file(folder, name, suffix='.json'):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid item identifier.')
    return directory(folder) / (name + suffix)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path, data):
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.' + identifier() + '.tmp')
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        temp.replace(path)

def records(folder):
    with LOCK:
        return [dict(read(p), id=p.stem) for p in sorted(directory(folder).glob('*.json'))]

def personas():
    return [dict(p, technical_skill=p.get('technical_skill', p.get('technical_level', 'moderate'))) for p in records('personas')]

def reports():
    result = []
    for p in directory('results').glob('*.json'):
        report = read(p)
        report.update(id=p.stem, created_at=report.get('created_at') or datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(), imported=not bool(report.get('run_id')))
        result.append(report)
    return sorted(result, key=lambda r:r['created_at'], reverse=True)
