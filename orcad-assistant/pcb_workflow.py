"""Conservative nominal-table extraction and joint schematic/PCB workflow."""
import copy
import json
import re
import uuid
import shutil
from pathlib import Path
import footprint_pipeline as fp


def extract_height(texts):
    hits=[]
    pattern=r'Package\s+Height\s+C\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
    for page,text in enumerate(texts,1):
        for m in re.finditer(pattern,text,re.I):
            nominal,minimum,maximum=map(float,m.groups())
            if 0<minimum<=nominal<=maximum:
                hits.append(dict(height_nominal=nominal,height_min=minimum,height_max=maximum,
                    page=page,text=m[0],field='height_max'))
    if hits and len({(h['height_nominal'],h['height_min'],h['height_max']) for h in hits})==1:
        return hits[0]
    return None


def enrich_height(project):
    """Older saved projects may regain missing height from their original PDF."""
    pcb=project.get('pcb') or {};spec=pcb.get('spec')
    if not spec or spec.get('height_max') is not None:return
    import fitz
    hits=[]
    for source in project.get('sources',[]):
        path=Path(source.get('path',''))
        if path.suffix.lower()!='.pdf' or not path.is_file():continue
        try:
            with fitz.open(path) as doc:
                texts=[page.get_text() for page in doc]
            if not re.search(r'\bMillimeters\b','\n'.join(texts),re.I):continue
            height=extract_height(texts)
            if height:hits.append(height)
        except (OSError,ValueError):continue
    if hits and len({h['height_max'] for h in hits})==1:
        height=hits[0]
        spec.update({k:height[k] for k in ('height_min','height_nominal','height_max')})
        spec['height_source']=f"规格书 p{height['page']} · Package Height C · max"
        pcb.setdefault('sources',[]).append({k:height[k] for k in ('page','field','text')})
        pcb['confirmed']=False


def enrich_project(project):
    enrich_height(project)
    pcb=project.get('pcb') or {};spec=pcb.get('spec')
    if not spec:return
    identity=' '.join(str(v) for v in (project.get('device',''),spec.get('name',''),spec.get('descr','')))
    e=spec.get('edge',{});centers=spec.get('centers',{})
    def same_point(a,b):
        return (isinstance(a,(list,tuple)) and len(a)==2
            and all(isinstance(v,(int,float)) for v in a)
            and all(abs(x-y)<1e-7 for x,y in zip(a,b)))
    known_geometry=(re.search(r'GC4693',identity,re.I) and spec.get('body')==[5.805,3.635]
        and spec.get('pitch')==[.64,.58] and spec.get('rows')=='ABCDE' and spec.get('cols')==7)
    changed=False
    if (re.search(r'GC4693',identity,re.I) and spec.get('body')==[5.805,3.635]
        and spec.get('pitch')==[.64,.58] and spec.get('rows')=='ABCDE' and spec.get('cols')==7
        and abs(e.get('left_to_col1',0)-.92243)<1e-7
        and abs(e.get('right_to_colN',0)-1.04257)<1e-7
        and len(centers.get('BGA',[]))==2 and abs(centers['BGA'][0]+.06007)<1e-7):
        e['left_to_col1'],e['right_to_colN']=e['right_to_colN'],e['left_to_col1']
        old=centers['BGA'][:]
        centers['BGA']=[.06007,old[1]]
        if same_point(centers.get('OPT'),old):centers['OPT']=centers['BGA'][:]
        changed=True
    # Repair projects whose BGA migration succeeded but OPT was left behind by
    # the old exact-float comparison. Limit this to the known legacy geometry.
    if (known_geometry and abs(e.get('left_to_col1',0)-1.04257)<1e-7
        and abs(e.get('right_to_colN',0)-.92243)<1e-7
        and same_point(centers.get('BGA'),[.06007,-.04465])
        and same_point(centers.get('OPT'),[-.06007,-.04465])):
        centers['OPT']=centers['BGA'][:]
        changed=True
    if changed:
        spec['orientation_source']='GC4693 p14 TOP VIEW; S3 left, S1 right; X=+0.06007 mm'
        pcb['confirmed']=False
        pcb['notes']=[n for n in pcb.get('notes',[]) if 'X=-0.06007' not in n]
        pcb['notes'].append('已修正顶视图方向：左=S3、右=S1，阵列中心 X=+0.06007 mm；请重新确认并生成，更新 PCB 旧实例。')
        if same_point(centers.get('OPT'),centers['BGA']):
            pcb['notes'].append('光学中心与 BGA 阵列中心重合，两个标注指向同一个点。')
        project['generated']=None


def inspect_pdf(path, pins):
    import fitz
    result=dict(spec=None, confirmed=False, notes=[], sources=[], needs=[])
    values={}
    labels={'w':('Package Body Dimension X','A'),'h':('Package Body Dimension Y','B'),
      'px':('Pins pitch X axis','J1'),'py':('Pins pitch Y axis','J2'),
      'nx':('Ball Count X axis','N1'),'ny':('Ball Count Y axis','N2'),
      'count':('Total Ball Count','N'),'ball':('Ball Diameter','D'),'left':('Edge to Pin Center Distance along X','S1'),
      'right':('Edge to Pin Center Distance along X','S3'),
      'top':('Edge to Pin Center Distance along Y','S2'),'bottom':('Edge to Pin Center Distance along Y','S4')}
    with fitz.open(path) as doc:
        texts=[p.get_text() for p in doc]
    text='\n'.join(texts)
    height=extract_height(texts)
    model=re.search(r'\bGC4693\b',text,re.I)
    for key,(label,symbol) in labels.items():
        hits=[]
        for page,t in enumerate(texts,1):
            pattern=re.escape(label).replace(r'\ ',r'\s+')+r'\s+'+symbol+r'\s+(-?\d+(?:\.\d+)?)\b'
            for m in re.finditer(pattern,t,re.I):
                hits.append((float(m[1]),page,m[0]))
        if hits and len({h[0] for h in hits})==1:
            values[key]=hits[0][0]
            result['sources'].append(dict(field=key,page=hits[0][1],text=hits[0][2]))
        else: result['needs'].append(label+' / '+symbol+('（多处数值冲突）' if hits else ''))
    result['draft'] = {k: values[k] for k in ('w','h','px','py','ball') if k in values}
    if not re.search(r'\bMillimeters\b',text,re.I):
        result['needs'].append('尺寸表的毫米单位标识')
    if not re.search(r'Top\s+View\s*\(Bumps\s+Down\)',text,re.I):
        result['needs'].append('明确的顶视图方向（Bumps Down）')
    # Edge labels vary by manufacturer; only the reviewed convention is automatic.
    if not model: result['needs'].append('该器件的 S1/S2/S3/S4 方位尚未验证，请在参数中核对顶视方向及边距')
    if len(values)!=len(labels) or any('顶视图方向' in x or '毫米单位' in x for x in result['needs']):
        result['notes']=['暂未取得完整可信的 CSP/BGA 尺寸。可手动补齐 PCB 参数，符号功能仍可单独使用。']
        return result
    nx,ny=int(values['nx']),int(values['ny'])
    rows=sorted({p['id'][0] for p in pins if re.fullmatch('[A-Z][1-9][0-9]*',p['id'])})
    if values['count']!=len(pins):
        result['needs'].append('规格书总球数与提取引脚数不一致');return result
    if not 1<=nx<=100 or not 1<=ny<=26 or values['nx']!=nx or values['ny']!=ny or len(rows)!=ny:
        result['needs'].append('球阵列行列数与引脚表不一致');return result
    ids={p['id'] for p in pins};grid={r+str(c) for r in rows for c in range(1,nx+1)}
    if not ids<=grid:result['needs'].append('引脚编号不符合球阵列');return result
    # The GC4693 S1/S3 dimensions are drawn in BACK VIEW, with columns 7..1.
    # TOP VIEW has columns 1..7, so reflect the horizontal edge assignments.
    if model:values['left'],values['right']=values['right'],values['left']
    cx=(values['left']-values['right'])/2;cy=(values['bottom']-values['top'])/2
    name='GC4693' if model else 'DEVICE'
    spec=dict(name=name,descr='CSP/BGA; top view, body center origin, mm',body=[values['w'],values['h']],
      pitch=[values['px'],values['py']],edge=dict(left_to_col1=values['left'],right_to_colN=values['right'],top_to_rowA=values['top'],bottom_to_rowN=values['bottom']),
      rows=''.join(rows),cols=nx,missing=sorted(grid-ids),ball_dia=values['ball'],
      pad_dia=round(values['ball']*.8,4),mask_margin=.0508,paste_dia=round(values['ball']*.8,4),courtyard_excess=.25,
      centers=dict(BGA=[cx,cy],OPT=[cx,cy]),kicad_version=6,
      process_profile=dict(source='参考工艺：铜径为球径 80%，阻焊每侧 +0.0508 mm；非厂家推荐值',status='review_required'))
    if height:
        spec.update({k:height[k] for k in ('height_min','height_nominal','height_max')})
        spec['height_source']=f"规格书 p{height['page']} · Package Height C · max"
        result['sources'].append({k:height[k] for k in ('page','field','text')})
    else:
        result['needs'].append('器件最大高度（mm），用于 Place Bound 高度检查')
    try:fp.geometry(spec)
    except ValueError as exc:result['needs'].append(str(exc));return result
    result['spec']=spec
    result['notes']=['尺寸来自规格书标称值；顶视图，原点为本体中心，+Y 向上。',spec['process_profile']['source']]
    if model:
        spec['orientation_source']='GC4693 p14 TOP VIEW; S3 left, S1 right; X=+0.06007 mm'
        result['notes'].append('按 p14 顶视图及背视图左右转换：左=S3、右=S1，X=+0.06007 mm；p15 负号备注与顶视图矛盾，请核对。')
    return result


def check(project):
    pcb=project.get('pcb') or {};spec=pcb.get('spec')
    if not spec:raise ValueError('PCB 尺寸尚不完整，请在 PCB 封装页补齐参数')
    pads=fp.geometry(spec)
    fp.require_height(spec)
    ids=[p['id'] for p in project['pins']]
    if len(set(ids))!=len(ids) or set(ids)!={p[0] for p in pads}:raise ValueError('符号脚号与 PCB 焊盘编号不完全一致')
    if pcb.get('needs'):raise ValueError('请先处理 PCB 缺项：'+'；'.join(pcb['needs']))
    if not pcb.get('confirmed'):raise ValueError('请在 PCB 页核对尺寸、方向和工艺预设后确认')
    if project['footprint']!=spec['name']:raise ValueError('PCB 封装名称不一致，请保存 PCB 参数以同步名称')
    return spec


def build(project,env,output_root,progress):
    import build_pipeline
    spec=check(project)
    root=Path(output_root).resolve()/('device-'+uuid.uuid4().hex[:12]);root.mkdir(parents=True)
    progress('正在原生生成 PCB 封装…')
    report=fp.build(spec,root/'pcb',progress,env.get('allegro','D:/tools/pcb/bin/allegro.exe'))
    symbol=build_pipeline.build(project,env,root/'symbol',progress)
    manifest=dict(status='PASS',pins=len(project['pins']),pcb=report,symbol=symbol['report'],
                  checks=['所有 PART 的脚号与 PCB 焊盘完全一致','OLB 独立回读','DRA 独立回读和 PSM 编译'])
    (root/'verification.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=shutil.make_archive(str(root),'zip',root)
    return dict(directory=str(root),olb=symbol['olb'],report=manifest,archive=archive,pcb_directory=str(root/'pcb'))
