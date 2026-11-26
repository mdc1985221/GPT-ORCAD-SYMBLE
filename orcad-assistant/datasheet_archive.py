"""Content-addressed local PDFs with explicit per-device source associations."""
import hashlib,json,re,threading
from pathlib import Path
import assistant_core as core

class Archive:
    def __init__(self,root):
        self.root=Path(root).resolve();self.lock=threading.RLock()
    def _load(self):
        p=self.root/'index.json'
        return json.loads(p.read_text(encoding='utf8')) if p.is_file() else {'revision':1,'devices':{}}
    def key(self,project):
        # Exact normalized identity only; do not match a different part by a substring.
        device=str(project.get('device','')).strip().upper()
        embedded=project.get('_project') or {}
        spec=project.get('_spec') or {}
        manufacturer=str(project.get('manufacturer') or embedded.get('manufacturer') or spec.get('manufacturer') or '').strip().upper()
        return (manufacturer+'::'+device if manufacturer else device) if device else ''
    def attach(self,project,raw,name,origin='user_import',role='datasheet'):
        if not self.key(project):raise ValueError('请先填写器件型号，再关联规格书')
        if not raw.startswith(b'%PDF-') or len(raw)>60*1024*1024:raise ValueError('请提供不超过60MB的PDF规格书')
        import fitz
        with fitz.open(stream=raw,filetype='pdf') as d:
            if d.is_encrypted:raise ValueError('规格书PDF已加密，无法归档')
            pages=len(d)
        digest=hashlib.sha256(raw).hexdigest();folder=self.root/'pdf';folder.mkdir(parents=True,exist_ok=True)
        p=folder/(digest+'.pdf')
        with self.lock:
            if not p.exists():p.write_bytes(raw)
            if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('规格书存档校验失败')
            index=self._load();items=index['devices'].setdefault(self.key(project),[])
            if not any(i['sha256']==digest for i in items):
                items.append(dict(sha256=digest,name=Path(name).name,pages=pages,origin=origin,role=role))
                core.atomic_json(self.root/'index.json',index)
        return digest
    def capture(self,project,extra=()):
        errors=[]
        paths=[s.get('path','') for s in project.get('sources',[]) if isinstance(s,dict)]+list(extra)
        for raw_path in paths:
            if not raw_path:continue
            p=Path(raw_path)
            if p.suffix.lower()!='.pdf' or not p.is_file():continue
            try:self.attach(project,p.read_bytes(),p.name,'saved_project_source')
            except (OSError,ValueError) as e:errors.append(str(e))
        return errors
    def list(self,project):
        with self.lock:records=self._load()['devices'].get(self.key(project),[])
        return [dict(r,available=(self.root/'pdf'/(r['sha256']+'.pdf')).is_file()) for r in records]
    def pdf(self,digest):
        if not re.fullmatch('[a-f0-9]{64}',str(digest)):raise ValueError('规格书编号无效')
        p=self.root/'pdf'/(digest+'.pdf');raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('规格书已被修改或损坏')
        return raw
    def backfill(self,library,history):
        done=0;missing=[]
        for item in library.list():
            p=library.project(item['id']);self.capture(p)
            if self.list(p):done+=1
            else:missing.append(p.get('device',''))
        history.list(refresh=True)
        for r in history.records.values():
            p=dict(r['_project']);p['device']=r['device'];root=Path(r['source_path']);extra=[]
            source_path=root/'source-path.txt'
            # A recorded project source takes precedence over an older source-path
            # file. The AON sample deliberately changed manufacturer versions.
            if not p.get('sources') and source_path.is_file():extra.append(source_path.read_text(encoding='utf8').strip())
            spec=r.get('_spec') or {}
            if spec.get('source_pdf'):extra.append(spec['source_pdf'])
            self.capture(p,extra)
            if self.list(p):done+=1
            else:missing.append(p.get('device',''))
        return dict(linked_records=done,missing_devices=sorted(set(missing)))
