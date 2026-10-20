"""Local-only API and frontend host. Start from the repository root with start.ps1."""
import base64
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from Backend.agents.persona_agent import evaluate_ux
from . import storage as db
from .schemas import PersonaInput, ProjectInput, PlanInput, PlanUpdate, RunInput, ScreenshotInput, CaptureInput

EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='omni-evaluation')
Image.MAX_IMAGE_PIXELS = 25_000_000

@asynccontextmanager
async def lifespan(app):
    for run in db.records('runs'):
        if run['status'] in ('queued', 'running'):
            run.update(status='failed', error='The backend restarted during this evaluation. Start a new run.')
            db.write(db.safe_file('runs',run['id']),run)
    yield

app = FastAPI(title='OMNI local API', lifespan=lifespan)

@app.middleware('http')
async def local_access(request: Request, call_next):
    # No remote deployment, authentication substitute, or public listener is intended.
    host = (request.headers.get('host') or '').split(':')[0]
    if host not in ('localhost','127.0.0.1','testserver'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'OMNI is a local-only application.'}, status_code=403)
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin = request.headers.get('origin')
        if request.headers.get('x-omni-client') != 'workspace' or (origin and urlsplit(origin).netloc != request.headers.get('host')):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':'Use the local OMNI workspace to make changes.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response

def get_record(folder, item_id):
    try:
        path = db.safe_file(folder,item_id)
    except ValueError:
        raise HTTPException(400, 'Invalid item identifier.')
    if folder=='personas':
        person=db.persona(item_id)
        if person is None:
            raise HTTPException(404,'Persona not found.')
        return person
    if not path.exists():
        raise HTTPException(404, 'This item was not found.')
    return dict(db.read(path), id=item_id)

def screenshot_path(item_id):
    if '/' in item_id or '\\' in item_id or item_id.startswith('.'):
        raise HTTPException(400, 'Invalid screenshot identifier.')
    path = db.directory('screenshots') / item_id
    if path.suffix.lower() not in ('.png','.jpg','.jpeg') or not path.is_file():
        raise HTTPException(404, 'Screenshot not found.')
    return path

@app.get('/api/health')
def health():
    provider = os.getenv('OMNI_MODEL_PROVIDER', 'gemini').lower()
    return {'status':'ok','workspace':str(Path(__file__).resolve().parents[2]),'gemini_configured':bool(os.getenv('GEMINI_API_KEY')), 'provider':provider, 'model':os.getenv('OLLAMA_MODEL','qwen3:4b') if provider == 'ollama' else os.getenv('GEMINI_MODEL','gemini-3.8-flash'), 'capabilities':{'screenshot_ux':True,'saved_explorations':True,'qa':False,'browser_journeys':True,'pause':False}, 'target_url':'http://127.0.0.1:5173/'}

@app.get('/api/personas')
def list_personas():
    return db.personas()

@app.post('/api/personas', status_code=201)
def create_persona(body:PersonaInput):
    item = dict(body.model_dump(), id=db.identifier())
    db.write(db.safe_file('personas',item['id']),item)
    return item

@app.put('/api/personas/{item_id}')
def update_persona(item_id:str, body:PersonaInput):
    existing = get_record('personas',item_id)
    item = dict(existing, **body.model_dump())
    db.save_persona(item_id,item)
    return item

@app.get('/api/projects')
def list_projects():
    return db.records('projects')

@app.post('/api/projects', status_code=201)
def create_project(body:ProjectInput):
    if not body.name.strip():
        raise HTTPException(400,'Add a project name.')
    item = dict(body.model_dump(), id=db.identifier(), created_at=db.now())
    db.write(db.safe_file('projects',item['id']),item)
    return item

@app.get('/api/screenshots')
def list_screenshots():
    result = []
    for path in sorted(db.directory('screenshots').iterdir()):
        if path.suffix.lower() not in ('.png','.jpg','.jpeg'):
            continue
        try:
            meta = db.safe_file('screenshot_meta',path.stem)
            data = db.read(meta) if meta.exists() else {}
        except ValueError:
            data = {}
        result.append(dict(data,id=path.name,name=data.get('name',path.stem.replace('_',' ')),url=f'/api/screenshots/{path.name}',bytes=path.stat().st_size))
    return result

@app.get('/api/screenshots/{item_id}')
def screenshot(item_id:str):
    return FileResponse(screenshot_path(item_id))

def save_image(image_bytes, name='Screenshot', source_url=None):
    if len(image_bytes)>10*1024*1024:
        raise HTTPException(413,'Use an image smaller than 10 MB.')
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in ('PNG','JPEG'):
                raise ValueError('Unsupported format')
            image.load()
            clean = io.BytesIO()
            image.convert('RGB').save(clean,format='PNG')
    except Exception:
        raise HTTPException(400,'Upload a valid PNG or JPEG, up to 25 million pixels.')
    item_id = db.identifier()+'.png'
    (db.directory('screenshots')/item_id).write_bytes(clean.getvalue())
    meta = {'name':name,'source_url':source_url,'created_at':db.now()}
    db.write(db.safe_file('screenshot_meta',Path(item_id).stem),meta)
    return dict(meta,id=item_id,url=f'/api/screenshots/{item_id}')

@app.post('/api/screenshots',status_code=201)
def upload_screenshot(body:ScreenshotInput):
    try:
        image = base64.b64decode(body.data.split(',')[-1], validate=True)
    except Exception:
        raise HTTPException(400,'Invalid image data.')
    return save_image(image,name=body.name)

@app.post('/api/capture',status_code=201)
def capture(body:CaptureInput):
    # A screenshot capture only: no interactions or QA assertions are fabricated.
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            with p.chromium.launch(channel='chrome',headless=False) as browser:
                page = browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
                # Restrict every browser request, including redirects and subresources.
                def guard(route):
                    u = urlsplit(route.request.url)
                    if u.scheme in ('data','blob') or (u.hostname in ('127.0.0.1','localhost') and u.port==5173):
                        route.continue_()
                    else:
                        route.abort()
                page.route('**/*',guard)
                page.goto(body.url,wait_until='networkidle',timeout=30000)
                image = page.screenshot(full_page=True,animations='disabled')
        return save_image(image,name=body.name,source_url=body.url)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502,'Chrome capture failed. Start TestLab on 127.0.0.1:5173 and install Google Chrome, or upload a screenshot instead.')

@app.post('/api/plans',status_code=201)
def create_plan(body:PlanInput):
    person = get_record('personas',body.persona_id)
    if body.method == 'screenshot':
        if not body.screenshot_id:
            raise HTTPException(400, 'Choose a screenshot.')
        screenshot_path(body.screenshot_id)
    elif urlsplit(body.url).hostname in ('localhost', '127.0.0.1') and urlsplit(body.url).port == 8000:
        raise HTTPException(400, 'Choose the website to test, rather than the OMNI workspace.')
    if body.project_id:
        get_record('projects',body.project_id)
    criteria = person.get('criteria',[])
    item = dict(body.model_dump(),id=db.identifier(),persona=person,created_at=db.now(),planner='persona_criteria', cases=[{'id':db.identifier(),'title':f'Review {criterion}','expected':f'Inspect recorded evidence relevant to {criterion.lower()} for {person["name"]}.','selected':True} for criterion in criteria])
    if not item['cases']:
        raise HTTPException(400,'The selected persona has no evaluation criteria.')
    db.write(db.safe_file('plans',item['id']),item)
    return item

@app.get('/api/plans/{item_id}')
def get_plan(item_id:str):
    return get_record('plans',item_id)

@app.put('/api/plans/{item_id}')
def update_plan(item_id:str,body:PlanUpdate):
    item = get_record('plans',item_id)
    item['cases'] = [c.model_dump() for c in body.cases]
    db.write(db.safe_file('plans',item_id),item)
    return item

@app.get('/api/runs/{item_id}')
def get_run(item_id:str):
    return get_record('runs',item_id)

def progress(item_id,message,**changes):
    with db.LOCK:
        run = get_record('runs',item_id)
        run.update(**changes)
        run['logs'].append({'at':db.now(),'message':message})
        db.write(db.safe_file('runs',item_id),run)

def evaluate_run(item_id,plan):
    try:
        if plan.get('method') == 'live':
            from .live import run_live
            from Backend.agents.gemini_requests import status_callback
            progress(item_id,'Opening Chrome for the selected persona.',status='running',stage='preparing')
            token = status_callback.set(lambda message: progress(item_id, message))
            try:
                run_live(item_id, plan, progress)
            finally:
                status_callback.reset(token)
            return
        progress(item_id,'Preparing the selected screenshot and persona.',status='running',stage='preparing')
        path = screenshot_path(plan['screenshot_id'])
        selected = [c for c in plan['cases'] if c['selected']]
        task = plan['instructions']+'\n\nSelected screenshot review criteria:\n'+'\n'.join(c['title']+': '+c['expected'] for c in selected)
        progress(item_id,'Sent screenshot to Gemini. Waiting for evidence-based findings.',stage='analyzing')
        result = evaluate_ux(plan['persona'],task,path)
        result.update(id=item_id,run_id=item_id,created_at=db.now(),persona_id=plan['persona_id'],persona_snapshot=plan['persona'],task=plan['instructions'],url=plan['url'],mode='UX',project_id=plan['project_id'],screenshot_id=plan['screenshot_id'],cases=selected,model=os.getenv('GEMINI_MODEL','gemini-3.8-flash'),method='Gemini screenshot UX evaluation')
        db.write(db.safe_file('results',item_id),result)
        progress(item_id,'Findings saved. Report is ready.',status='completed',stage='completed',report_id=item_id)
    except Exception as error:
        # SDK errors may contain sensitive request context: never return their raw text.
        message = str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Evaluation failed. Check your Gemini API key, configured model, network and quota, then start a new run.'
        if os.getenv('GEMINI_API_KEY'):
            message = message.replace(os.environ['GEMINI_API_KEY'],'[redacted]')
        progress(item_id,message,status='failed',stage='failed',error=message)

@app.post('/api/runs',status_code=202)
def create_run(body:RunInput):
    plan = get_record('plans',body.plan_id)
    if not any(c['selected'] for c in plan['cases']):
        raise HTTPException(400,'Select at least one review case.')
    needs_gemini = plan.get('method') != 'live' or os.getenv('OMNI_MODEL_PROVIDER', 'gemini').lower() != 'ollama'
    if needs_gemini and not os.getenv('GEMINI_API_KEY'):
        raise HTTPException(503,'Add GEMINI_API_KEY to Backend/.env and restart the backend. Your saved reports remain available.')
    with db.LOCK:
        if any(r['status'] in ('queued','running') for r in db.records('runs')):
            raise HTTPException(409,'An evaluation is already running. Wait for it to finish.')
        item = {'id':db.identifier(),'status':'queued','stage':'queued','plan':plan,'created_at':db.now(),'logs':[{'at':db.now(),'message':'Evaluation queued.'}],'report_id':None,'error':None}
        db.write(db.safe_file('runs',item['id']),item)
        EXECUTOR.submit(evaluate_run,item['id'],plan)
    return item

@app.get('/api/reports')
def list_reports():
    return db.reports()

@app.get('/api/reports/{item_id}')
def get_report(item_id:str):
    report=next((r for r in db.reports() if r['id']==item_id),None)
    if report is None:
        raise HTTPException(404,'Report not found.')
    return report

@app.get('/api/reports/{item_id}/evidence')
def get_report_evidence(item_id:str):
    get_report(item_id)
    return db.report_evidence(item_id)

@app.get('/api/reports/{item_id}/evidence/{filename}')
def get_evidence_image(item_id:str, filename:str):
    source = db.report_sources().get(item_id)
    if not source or source.name != 'report.json' or not re.fullmatch(r'step-[1-9][0-9]*-(before|after)\.png', filename):
        raise HTTPException(404, 'Screenshot not found.')
    path = source.parent / 'evidence' / filename
    if not path.is_file() or path.resolve().parent != (source.parent / 'evidence').resolve():
        raise HTTPException(404, 'Screenshot not found.')
    return FileResponse(path, media_type='image/png')

FRONTEND = Path(__file__).resolve().parents[2] / 'Frontend'
app.mount('/',StaticFiles(directory=FRONTEND,html=True),name='frontend')
