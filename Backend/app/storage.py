"""Atomic JSON storage for the local presentation app."""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.getenv('OMNI_DATA_DIR', DEFAULT_ROOT)).resolve()
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

def persona(item_id):
    safe_file('personas',item_id)
    return next((p for p in personas() if p['id']==item_id),None)

def save_persona(item_id, item):
    write(safe_file('personas',item_id),item)

def report_sources():
    root = directory('results')
    sources = {p.stem:p for p in root.glob('*.json')}
    for report in root.glob('exploration_*/report.json'):
        sources[report.parent.name] = report
    return sources

def reports():
    result = []
    for item_id, p in report_sources().items():
        report = read(p)
        is_exploration = p.name=='report.json' and p.parent.name.startswith('exploration_')
        report.setdefault('findings',[])
        report.update(id=item_id, kind='exploration' if is_exploration else 'screenshot',created_at=report.get('created_at') or datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(), imported=not bool(report.get('run_id')))
        if is_exploration:
            report['method']='Recorded browser exploration'
            report.setdefault('task','Explore the website')
            history_path=p.parent/'history.json'
            report['has_history']=history_path.is_file()
            if history_path.is_file():
                history=read(history_path)
                report['actions_executed'] = sum(row.get('result') == 'executed' for row in history)
                if history:
                    report.setdefault('url',history[0].get('before',{}).get('url'))
            snapshot=p.parent/'persona.json'
            if snapshot.is_file():
                report['persona_snapshot']=read(snapshot)
        result.append(report)
    return sorted(result, key=lambda r:r['created_at'], reverse=True)

def report_evidence(item_id):
    path=report_sources().get(item_id)
    if not path or path.name!='report.json':
        return []
    history_path=path.parent/'history.json'
    if not history_path.is_file():
        return []
    # Never expose browser_state.json, cookies, localStorage or entered values.
    rows=[]
    for row in read(history_path):
        decision=row.get('decision',{})
        states={}
        for key in ('before','after'):
            source=row.get(key,{})
            states[key]={'url':source.get('url'), 'visible_text':source.get('visible_text',''), 'controls':[{'id':c.get('id'),'name':c.get('name','')} for c in source.get('controls',[])]}
        images = {}
        for phase in ('before', 'after'):
            filename = f'step-{row.get("step")}-{phase}.png'
            if row.get('screenshots', {}).get(phase) == filename and (path.parent/'evidence'/filename).is_file():
                images[phase] = f'/api/reports/{item_id}/evidence/{filename}'
        rows.append(dict(states,step=row.get('step'),action=decision.get('action'),reason=decision.get('reason'),result=row.get('result'),observed_change=row.get('observed_change',{}),screenshots=images,target_label=row.get('target_label','')))
    return rows
