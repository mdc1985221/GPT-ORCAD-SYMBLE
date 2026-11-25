"""Read-only discovery of previous builds, separate from the verified library."""
import hashlib,html,io,json
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import assistant_core as core
import footprint_pipeline as fp
import library_manager as library

def read(path):
    try:return json.loads(Path(path).read_text(encoding='utf8'))
    except (OSError,ValueError):return {}

class HistoryCatalog:
    def __init__(self,roots):
        self.roots=[(label,Path(path).resolve()) for label,path in roots]
        self.records=None

    def _safe(self,file,root):
        p=Path(file).resolve()
        return p if p.is_relative_to(root) and p.is_file() else None

    def scan(self):
        self.records={};seen=set();warnings=0
        for label,parent in self.roots:
            if not parent.is_dir():continue
            candidates=[p for p in parent.iterdir() if p.is_dir() and not p.name.startswith('.')]
            # Company examples are one level below their review collection.
            if (parent/'company-library').is_dir():candidates+=list((parent/'company-library').iterdir())
            for folder in candidates:
                if not folder.is_dir() or not folder.resolve().is_relative_to(parent) or folder.resolve() in seen:continue
                seen.add(folder.resolve())
                try:
                    item=self._index(folder.resolve(),label)
                    if item:self.records[item['id']]=item
                except (OSError,ValueError,KeyError,TypeError):warnings+=1
        return dict(items=sorted(self.records.values(),key=lambda x:x['created'],reverse=True),categories=library.CATEGORIES,warnings=warnings)

    def _index(self,root,label):
        project=read(root/'project.json') or read(root/'updated-project.json')
        symbol_result=read(root/'symbol-result.json')
        olbs=[p for pattern in ('*.OLB','symbol/*/*.OLB','symbol/*.OLB','symbol-correct-order/*/*.OLB') for p in root.glob(pattern)]
        explicit=self._safe(symbol_result.get('olb',''),root)
        olb=explicit or (max(olbs,key=lambda p:p.stat().st_mtime) if olbs else None)
        if not project and olb:project=read(olb.parent/'project.json')
        symbol_project=(read(olb.parent/'project.json') if olb else {}) or project
        spec=read(root/'spec.json') or (project.get('pcb') or {}).get('spec') or read(root/'pcb-extraction.json').get('spec')
        dirs=[p for pattern in ('pcb','pcb-v*','native-v*') for p in root.glob(pattern) if p.is_dir()]
        dirs=[p for p in dirs if (p/'allegro').is_dir()]
        # Prefer an output with a completed verification record over failed attempts.
        native=max(dirs,key=lambda p:(read(p/'verification.json').get('status')=='PASS',p.stat().st_mtime),default=None)
        if native:spec=read(native/'spec.json') or spec
        files=[]
        legacy=read(root/'verification.json')
        for relative in legacy.get('files',{}):
            if not isinstance(relative,str):continue
            normalized=relative.replace('\\','/');f=self._safe(root/normalized,root)
            if f and f.suffix.lower() in ('.olb','.psm','.pad','.ssm','.dra','.step'):files.append((normalized,f))
        if olb:files.append(('symbol/'+olb.name,olb))
        if native:
            adir=native/'allegro';psms=list(adir.glob('*.psm'));pads=list(adir.glob('*.pad'));ssms=list(adir.glob('*.ssm'))
            for f in psms+ssms:files.append(('pcb/psm/'+f.name,f))
            for f in pads:files.append(('pcb/pad/'+f.name,f))
            for psm in psms:
                for dra in adir.glob('*.dra'):
                    if dra.stem.lower()==psm.stem.lower():files.append(('pcb/source/'+dra.name,dra))
        mesh_dirs=[p.parent for pattern in ('mesh.json','3d/mesh.json','model3d/mesh.json') for p in root.glob(pattern)]
        model=max(mesh_dirs,key=lambda p:(p/'mesh.json').stat().st_mtime,default=None)
        steps=list(model.glob('*.step')) if model else list(root.glob('*.step'))
        if steps:
            record=read(model/'model3d.json') or read(model/'verification.json') if model else {}
            named=self._safe(model/record['step'],root) if model and record.get('step') else None
            step=named or max(steps,key=lambda p:p.stat().st_mtime)
            files.append(('3d/'+step.name,step))
        files=[(relative,p) for relative,p in files if self._safe(p,root)]
        if not files:return None
        name=project.get('device') or (spec or {}).get('name') or legacy.get('name') or (steps[0].stem if steps else root.name)
        inferred='connector-dip' if (spec or {}).get('kind')=='pth_connector' else 'connector' if (spec or {}).get('family')=='connector' else 'resistor' if name.startswith('R0402') else library.suggest_category(dict(project,device=name))
        category=project.get('library_category') or inferred
        if category not in {c['id'] for c in library.CATEGORIES}:category='other'
        ident=hashlib.sha256(str(root).encode()).hexdigest()[:24]
        paths={key:next((str(p.parent) for _,p in files if p.suffix.lower() in suffixes),None) for key,suffixes in [('capture',('.olb',)),('psmpath',('.psm',)),('padpath',('.pad',)),('model3d',('.step',))]}
        if not spec and legacy.get('centers') and legacy.get('pad_size'):
            spec=dict(kind='legacy_rectangles',body=legacy['body_nominal'],centers_xy=legacy['centers'],pad_size=legacy['pad_size'])
        return dict(id=ident,history=True,device=name,footprint=project.get('footprint') or (spec or {}).get('name',name),pins=len(symbol_project.get('pins',[])) or len((spec or {}).get('positions',[])),parts=len(project.get('parts',{})) or 1,category=category,category_label=next(c['label'] for c in library.CATEGORIES if c['id']==category),pcb=any(p.suffix.lower()=='.psm' for _,p in files),symbol=bool(olb),model3d_status='generated' if steps and model else 'file_only' if steps else 'pending',status='HISTORY_REVIEW_REQUIRED',source=label,source_path=str(root),created=datetime.fromtimestamp(max(p.stat().st_mtime for _,p in files),timezone.utc).isoformat(),paths=paths,files=[dict(path=rel,bytes=p.stat().st_size) for rel,p in files],_files={rel:str(p) for rel,p in files},_project=symbol_project,_spec=spec,_mesh=str(model/'mesh.json') if model else None)

    def list(self,refresh=False):
        if self.records is None or refresh:self.scan()
        return dict(items=[{k:v for k,v in i.items() if not k.startswith('_')} for i in sorted(self.records.values(),key=lambda x:x['created'],reverse=True)],categories=library.CATEGORIES)

    def get(self,ident):
        if self.records is None:self.scan()
        if ident not in self.records:raise ValueError('历史记录不存在，请刷新索引')
        return self.records[ident]

    def detail(self,ident):
        record=self.get(ident);item={k:v for k,v in record.items() if not k.startswith('_')}
        item.update(sections=[],pcb_spec=record['_spec'],pads=[],presentation=None,preview_notice='历史参数预览；保留原文件，尚未重新验收。')
        try:
            if record['_project'].get('pins'):
                p=core.new_project();p.update(record['_project'])
                item['sections']=[dict(part=part,width=cfg['W'],height=cfg['H'],pins=pins) for part,cfg,pins in core.section_layouts(p,core.DEFAULT_ENV)]
        except (ValueError,KeyError,TypeError):pass
        spec=record['_spec']
        if spec:
            try:
                if spec.get('kind')=='legacy_rectangles':
                    w,h=spec['body'];pw,ph=spec['pad_size'];coords=spec['centers_xy']
                    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1.5 -1 3 2">']
                    svg.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" fill="none" stroke="#8798b5" stroke-width=".015"/>')
                    for i,(x,y) in enumerate(coords,1):svg.append(f'<rect x="{x-pw/2}" y="{-y-ph/2}" width="{pw}" height="{ph}" fill="#8099c8"/><text x="{x}" y="{-y+.04}" font-size=".12" text-anchor="middle" fill="white">{i}</text>')
                    item['presentation']=dict(kind='polygon_smd',svg=''.join(svg)+'</svg>')
                elif spec.get('kind')=='pth_connector':
                    w,h=spec['body'];svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-w/2-2} {-h/2-2} {w+4} {h+4}"><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" fill="none" stroke="#798eb6" stroke-width=".1"/>']
                    for p in spec['positions']:
                        x,y=p['x'],-p['y'];r=spec['pad']/2;pid=html.escape(p['id'])
                        svg.append(f'<rect x="{x-r}" y="{y-r}" width="{r*2}" height="{r*2}" fill="#a89961"/>' if p['id']=='1' else f'<circle cx="{x}" cy="{y}" r="{r}" fill="#a89961"/>')
                        svg.append(f'<circle cx="{x}" cy="{y}" r="{spec["drill"]/2}" fill="#f7f9fc"/><text x="{x}" y="{y+.16}" font-size=".45" text-anchor="middle">{pid}</text>')
                    item['presentation']=dict(kind='polygon_smd',svg=''.join(svg)+'</svg>')
                else:item['pads']=fp.geometry(spec);item['presentation']=fp.presentation(spec)
            except (ValueError,KeyError,TypeError):item['presentation']=None
        return item

    def mesh(self,ident):
        r=self.get(ident);p=r['_mesh']
        if not p or not self._safe(p,Path(r['source_path'])):raise ValueError('此历史记录没有可用的3D预览网格')
        return read(p)

    def download(self,ident,include_source=False):
        r=self.get(ident);buf=io.BytesIO()
        with ZipFile(buf,'w',ZIP_DEFLATED) as archive:
            for relative,path in r['_files'].items():
                p=self._safe(path,Path(r['source_path']))
                if not p or p.suffix.lower() not in ('.olb','.psm','.ssm','.pad','.dra','.step'):raise ValueError('历史文件路径无效或已丢失')
                if p.suffix.lower()=='.dra' and not include_source:continue
                archive.writestr(relative,p.read_bytes())
            archive.writestr('历史记录说明.txt','这是历史文件副本，未重新进行目标设计验收。参数预览不替代原生核验。来源：'+r['source_path'])
        return buf.getvalue()
