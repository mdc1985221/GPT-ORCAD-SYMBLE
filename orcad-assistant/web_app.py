"""Local HTML workspace; existing Python extraction/build engine is shared."""
import base64
import copy
import json
import secrets
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import assistant_core as core
import build_pipeline
import pcb_workflow
import footprint_pipeline
import library_manager
import model3d_pipeline
from urllib.parse import urlsplit, parse_qs, quote

BASE = Path(__file__).parent
STATE = BASE / 'workspace'


class Workspace:
    def __init__(self):
        self.project = core.new_project()
        self.env = core.DEFAULT_ENV.copy()
        if (STATE / 'environment.json').exists():
            self.env.update(json.loads((STATE / 'environment.json').read_text(encoding='utf-8')))
        self.history = []
        self.job = dict(busy=False, message='准备就绪', error='',progress=0)
        self.reference = None
        self.lock = threading.RLock()
        self.library = library_manager.Library(STATE/'library',STATE/'output')

    def save(self):
        core.atomic_json(STATE / 'last-session.json', self.project)

    def snapshot(self):
        self.history.append(copy.deepcopy(self.project))
        self.history = self.history[-30:]

    def view(self):
        with self.lock:
            core.invalidate_legacy_pcb(self.project)
            q = copy.deepcopy(self.project)
            pending = core.issues(q)
            q['device'] = q['device'] or 'DEVICE'
            q['footprint'] = q['footprint'] or 'PREVIEW'
            q['expected_count'] = None
            for pin in q['pins']:
                if pin['type'] not in core.TYPES:
                    pin['type'] = 'ANA'
            sections, error = [], ''
            if q['pins']:
                try:
                    for part, cfg, pins in core.section_layouts(q, self.env):
                        sections.append(dict(part=part, width=cfg['W'], height=cfg['H'], pins=pins))
                except ValueError as exc:
                    error = str(exc)
            pcb = self.project.get('pcb') or {}
            pcb_preview = []
            if pcb.get('spec'):
                try: pcb_preview = footprint_pipeline.geometry(pcb['spec'])
                except (ValueError, KeyError, TypeError): pass
            style=footprint_pipeline.presentation(pcb['spec']) if pcb_preview else None
            return dict(layout_template=core.layout_rule(self.project),pcb_preview=pcb_preview, pcb_presentation=style, project=self.project, issues=pending, sections=sections,
                        library_categories=library_manager.CATEGORIES, library_suggestion=library_manager.suggest_category(self.project),
                        job=self.job, reference=self.reference, preview_error=error, environment=self.env,
                        model3d_available=self.model3d_available(),model3d_item=getattr(self,'last_model3d_item',None))

    def model3d_available(self):
        try:model3d_pipeline.runtime();return True
        except ValueError:return False

    def start(self, work, kind='import'):
        self.job = dict(busy=True, message='正在生成并验证…' if kind=='build' else '正在读取资料…', error='',progress=None,kind=kind)
        def progress(message):
            with self.lock:
                self.job['message'] = message
        def run():
            try:
                work(progress)
                with self.lock:
                    self.save()
                    self.job.update(busy=False, message='生成并验证完成' if kind=='build' else '资料已就绪，待生成',progress=100 if kind=='build' else 0)
            except Exception as exc:
                with self.lock:
                    self.job.update(busy=False, message='操作未完成，原项目已保留', error=str(exc),progress=0)
                    core.atomic_json(STATE / 'last-web-error.json', self.job)
        threading.Thread(target=run, daemon=True).start()

    def action(self, data):
        with self.lock:
            action = data['action']
            if self.job['busy']:
                raise ValueError('当前任务正在处理，请稍候')
            if action in ('import', 'reference'):
                suffix = Path(data['name']).suffix.lower()
                allowed = ('.png','.jpg','.jpeg','.bmp','.webp') if action=='reference' else ('.pdf','.csv','.json')
                if suffix not in allowed:
                    raise ValueError('不支持的文件类型')
                folder = STATE / 'imports' / uuid.uuid4().hex
                folder.mkdir(parents=True)
                path = folder / Path(data['name'].replace('\\','/')).name
                path.write_bytes(base64.b64decode(data['content'], validate=True))
                if action=='reference':
                    part = data.get('part','A')
                    pins = copy.deepcopy([p for p in self.project['pins'] if p.get('part','A')==part])
                    if not pins:
                        raise ValueError('先导入引脚，再识别截图')
                    def work(progress):
                        from reference_layout import analyze
                        result = analyze(path, pins, progress)
                        with self.lock:
                            self.reference = dict(result=result,part=part)
                    self.start(work)
                else:
                    def work(progress):
                        if suffix=='.json':
                            project = core.load_project(path)
                            pcb_workflow.enrich_project(project)
                        else:
                            pins = core.extract_pdf(path,progress,package=data.get('package')) if suffix=='.pdf' else core.import_csv(path)
                            project = core.new_project()
                            project.update(device=path.stem.split('_')[0],pins=pins,sources=[core.source_record(path)])
                            if data.get('package'):project['selected_package']=data['package']
                            project['parts'] = {p.get('part','A'):'导入单元' for p in pins}
                            core.auto_layout(project)
                            if suffix=='.pdf':
                                progress('正在读取 PCB 尺寸及来源…')
                                project['pcb'] = pcb_workflow.inspect_pdf(path,pins)
                                if project['pcb'].get('spec'):
                                    project['footprint'] = project['pcb']['spec']['name']
                                    if project['footprint']!='DEVICE': project['device'] = project['footprint']
                                    project['expected_count'] = len(pins)
                        with self.lock:
                            self.snapshot()
                            self.project = project
                            self.reference = None
                    self.start(work)
            elif action in ('build','build-all'):
                project = copy.deepcopy(self.project)
                env = self.env.copy()
                if core.issues(project):
                    raise ValueError('请先处理待核对事项')
                if action=='build-all': pcb_workflow.check(project)
                if action=='build-all' and (project.get('model3d') or {}).get('enabled'):
                    model3d_pipeline.plan(project['pcb']['spec'],project['model3d'])
                    model3d_pipeline.runtime()
                def work(progress):
                    builder = pcb_workflow.build if action=='build-all' else build_pipeline.build
                    result = builder(project,env,STATE/'output',progress)
                    try:
                        progress('正在整理设计用库并分类入库…')
                        result['library_item']=self.library.add(project,result)['id']
                        options=project.get('model3d') or {}
                        if action=='build-all' and options.get('enabled'):
                            model=model3d_pipeline.build(project['pcb']['spec'],options,Path(result['directory'])/'model3d',progress)
                            result['model3d']=model
                            result['library_item']=self.library.with_model(result['library_item'],model,options)['id']
                            import shutil
                            shutil.make_archive(result['directory'],'zip',result['directory'])
                    except (ValueError,OSError,KeyError) as exc:
                        result['library_error']='库文件已生成，入库未完成：'+str(exc)
                    with self.lock:
                        self.project['generated'] = result
                        if result.get('model3d'):self.project['model3d_generated']=result['model3d']
                self.start(work,kind='build')
            elif action=='model3d-build':
                item_id=data.get('id')
                project=self.library.project(item_id) if item_id else copy.deepcopy(self.project)
                options=data['options'];spec=(project.get('pcb') or {}).get('spec')
                if not spec:raise ValueError('请先补齐 PCB 机械参数，再生成 3D')
                model3d_pipeline.plan(spec,options)
                def work(progress):
                    model=model3d_pipeline.build(spec,options,STATE/'output'/('model3d-'+uuid.uuid4().hex[:12]),progress)
                    if item_id:
                        item=self.library.with_model(item_id,model,options)
                        with self.lock:self.last_model3d_item=item['id']
                    else:
                        current=project.get('generated') or {}
                        attached=self.library.with_model(current['library_item'],model,options) if current.get('library_item') else None
                        with self.lock:
                            self.snapshot()
                            self.project['model3d']=dict(options,enabled=True)
                            self.project['model3d_generated']=model
                            if attached:self.project['generated']['library_item']=attached['id']
                self.start(work,kind='build')
            elif action=='model3d-config':
                options=data['options']
                if options.get('enabled'):model3d_pipeline.plan(self.project['pcb']['spec'],options)
                self.project['model3d']=options
                self.save()
            elif action=='environment':
                for key in core.DEFAULT_ENV:
                    self.env[key] = str(data['values'].get(key,self.env[key]))
                core.atomic_json(STATE/'environment.json',self.env)
            elif action=='undo':
                if self.history:
                    self.project = self.history.pop()
                    self.save()
            elif action=='library-add':
                item=self.library.add(self.project,self.project.get('generated') or {},data.get('category'))
                self.project['generated']['library_item']=item['id']
                self.save()
            elif action=='library-classify':
                self.library.classify(data['id'],data['category'])
            elif action=='library-category':
                self.project['library_category']=self.library._category(data['category'])
                self.save()
            elif action=='library-scan':
                self.library_scan=self.library.scan_history()
            else:
                candidate = copy.deepcopy(self.project)
                if action=='new':
                    candidate = core.new_project()
                elif action=='resume':
                    candidate = core.load_project(STATE/'last-session.json')
                    pcb_workflow.enrich_project(candidate)
                elif action=='demo':
                    path = BASE/'examples'/'GC4693_ballmap.csv'
                    candidate = core.new_project()
                    candidate.update(device='GC4693',footprint='CSP35',expected_count=35,pins=core.import_csv(path))
                    core.auto_layout(candidate)
                elif action=='pcb':
                    spec = data['spec']
                    footprint_pipeline.geometry(spec)
                    pcb = candidate.setdefault('pcb',{})
                    pcb.update(spec=spec,confirmed=bool(data.get('confirmed')),needs=[])
                    candidate['footprint'] = spec['name']
                    candidate.pop('model3d',None)
                elif action=='metadata':
                    for key in ('device','footprint','profile'):
                        if key in data:
                            candidate[key] = str(data[key])
                    if 'expected_count' in data:
                        value = data['expected_count']
                        candidate['expected_count'] = int(value) if value else None
                    if data.get('relayout'):
                        core.auto_layout(candidate)
                    if 'library_category' in data:
                        candidate['library_category']=self.library._category(data['library_category'])
                elif action=='library-open':
                    candidate=self.library.project(data['id'])
                    candidate['library_category']=self.library.get(data['id'])['category']
                    self.reference=None
                elif action=='relayout':
                    core.auto_layout(candidate)
                elif action=='symbol-geometry':
                    core.edit_symbol_geometry(candidate,self.env,data)
                elif action=='split':
                    core.split_parts(candidate,int(data.get('maximum',64)))
                elif action=='merge':
                    candidate['parts'] = {'A':'主单元'}
                    for pin in candidate['pins']:
                        pin['part'] = 'A'
                    core.auto_layout(candidate)
                elif action=='edit':
                    pin = next(p for p in candidate['pins'] if p['id']==data['id'])
                    values = data['values']
                    if any(k in values and str(values[k]).strip()!=pin[k] for k in ('side','part')):
                        candidate.pop('symbol_layout',None)
                    for key in ('name','type','side','group','part'):
                        if key in values:
                            pin[key] = str(values[key]).strip()
                    if pin['type'] not in core.TYPES or pin['side'] not in core.SIDES or pin['part'] not in candidate['parts']:
                        raise ValueError('请选择有效的类型、位置和 PART')
                elif action=='move':
                    candidate.pop('symbol_layout',None)
                    pin = next(p for p in candidate['pins'] if p['id']==data['id'])
                    if data['side'] not in core.SIDES:
                        raise ValueError('位置无效')
                    candidate['pins'].remove(pin)
                    pin['side'] = data['side']
                    target = next((i for i,p in enumerate(candidate['pins']) if p['id']==data.get('before')),len(candidate['pins']))
                    candidate['pins'].insert(target,pin)
                elif action=='confirm':
                    issue = next(i for i in core.issues(candidate) if i['key']==data['key'])
                    if issue['blocking']:
                        raise ValueError('此项需要修正，不能直接确认')
                    candidate['reviewed'].append(issue['key'])
                elif action=='apply-reference':
                    from reference_layout import apply
                    if not self.reference:
                        raise ValueError('没有待应用的截图结果')
                    candidate.pop('symbol_layout',None)
                    apply(candidate,self.reference['result'],self.reference['part'])
                    self.reference = None
                else:
                    raise ValueError('未知操作')
                self.snapshot()
                candidate['generated'] = None
                candidate.pop('model3d_generated',None)
                self.project = candidate
                self.save()
            if action not in ('import','reference','build','build-all','model3d-build'):
                self.job = dict(busy=False,message='资料已就绪，待生成' if self.project['pins'] else '准备就绪',error='',progress=0)
            return self.view()


def serve(port=8765, open_browser=True):
    workspace = Workspace()
    token = secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200):
            raw = json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            url=urlsplit(self.path);query=parse_qs(url.query)
            if self.path=='/health':
                self.reply({'application':'symbol-studio','pcb_unit_validation':3,'pcb_drawing_validation':2,'pcb_orientation_validation':1})
            elif self.path=='/':
                raw = (BASE/'web'/'index.html').read_text(encoding='utf-8').replace('__TOKEN__',token).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                self.wfile.write(raw)
            elif self.path=='/pcb-preview.js':
                raw=(BASE/'web'/'pcb-preview.js').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/javascript; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                self.wfile.write(raw)
            elif url.path in ('/library.js','/library.css','/model3d.js'):
                raw=(BASE/'web'/url.path[1:]).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/javascript; charset=utf-8' if url.path.endswith('.js') else 'text/css; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
            elif url.path.startswith('/api/library') and self.headers.get('X-Workspace-Token')==token:
                try:
                    with workspace.lock:
                        if url.path=='/api/library':
                            self.reply(dict(items=workspace.library.list(),categories=library_manager.CATEGORIES,
                                scan=getattr(workspace,'library_scan',None)));return
                        item_id=query.get('id',[''])[0]
                        if url.path=='/api/library/item':self.reply(workspace.library.detail(item_id));return
                        if url.path=='/api/library/mesh':self.reply(workspace.library.model_mesh(item_id));return
                        if url.path!='/api/library/download':raise ValueError('器件库操作无效')
                        raw=workspace.library.design_bytes(item_id,query.get('source',['0'])[0]=='1')
                    self.send_response(200);self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except (ValueError,OSError,KeyError) as exc:self.reply({'error':str(exc)},400)
            elif url.path in ('/api/model3d/download','/api/model3d/mesh') and self.headers.get('X-Workspace-Token')==token:
                try:
                    with workspace.lock:
                        g=workspace.project.get('model3d_generated') or {}
                        folder=workspace.library._source(Path(g.get('directory',''))/'model3d.json').parent
                        spec=workspace.project['pcb']['spec'];options=workspace.project['model3d']
                        report=model3d_pipeline.verify(folder,model3d_pipeline.plan(spec,options))
                        if url.path.endswith('/mesh'):
                            self.reply(json.loads((folder/'mesh.json').read_text(encoding='utf8')));return
                        variant=query.get('variant',['complete'])[0]
                        filename=(report.get('inspection') or {}).get('step') if variant=='inspection' else report['step']
                        if not filename:raise ValueError('该旧模型没有隐藏玻璃检查版，请重新生成 STEP')
                        raw=(folder/filename).read_bytes()
                    self.send_response(200);self.send_header('Content-Type','application/step')
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except (ValueError,OSError,KeyError) as exc:self.reply({'error':str(exc)},400)
            elif url.path=='/api/download' and self.headers.get('X-Workspace-Token')==token:
                with workspace.lock:
                    generated = workspace.project.get('generated') or {}
                    core.invalidate_legacy_pcb(workspace.project)
                    if query.get('full',['0'])[0]!='1':
                        try:
                            item=workspace.library.get(generated['library_item']) if generated.get('library_item') else workspace.library.add(workspace.project,generated)
                            raw=workspace.library.design_bytes(item['id'],query.get('source',['0'])[0]=='1')
                        except (ValueError,OSError,KeyError) as exc:
                            self.reply({'error':str(exc)},400);return
                        self.send_response(200);self.send_header('Content-Type','application/zip')
                        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                    file = Path(generated.get('archive','')).resolve()
                    allowed = (STATE/'output').resolve()
                    if not file.is_relative_to(allowed) or file.suffix!='.zip' or not file.is_file():
                        self.reply({'error':'尚无可下载的联合生成结果'},404)
                        return
                    raw = file.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','application/zip')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif self.path=='/api/state' and self.headers.get('X-Workspace-Token')==token:
                self.reply(workspace.view())
            else:
                self.reply({'error':'Not found'},404)

        def do_POST(self):
            if self.path!='/api/action' or self.headers.get('X-Workspace-Token')!=token:
                self.reply({'error':'Unauthorized'},403)
                return
            try:
                length = int(self.headers.get('Content-Length',0))
                if length>90*1024*1024:
                    raise ValueError('文件过大，请使用小于 60 MB 的资料')
                data = json.loads(self.rfile.read(length))
                self.reply(workspace.action(data))
            except Exception as exc:
                self.reply({'error':str(exc)},400)
    try:
        server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    except OSError:
        from urllib.request import urlopen
        try:
            with urlopen(f'http://127.0.0.1:{port}/health',timeout=2) as response:
                existing = json.load(response)
            if existing.get('application') != 'symbol-studio':
                raise ValueError('端口被其他程序使用')
        except Exception:
            raise RuntimeError(f'端口 {port} 不可用，请使用 --port 指定其他端口')
        if open_browser:
            webbrowser.open(f'http://127.0.0.1:{port}/')
        return
    url = f'http://127.0.0.1:{server.server_port}/'
    print('Symbol Studio: '+url,flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    serve(args.port,not args.no_browser)
