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
    from connector_profile import profile as connector_profile
    connector=connector_profile(path)
    if connector:return connector['pcb']
    from polygon_smd import profile as polygon_profile
    reviewed=polygon_profile(path)
    if reviewed:return reviewed['pcb']
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
    if re.search(r'\bGC5613\b',text,re.I):
        result=inspect_gc5613_csp(texts,pins)
        if result.get('spec'):
            from model3d_details import gc5613_reference
            appearance=gc5613_reference(path)
            if appearance:
                result['spec']['appearance_profile']=appearance
                result['notes'].append(appearance['notice'])
        return result
    if re.search(r'\bSC8238\b',text) and any(re.fullmatch(r'[A-F][1-7]',p['id']) for p in pins):
        result=inspect_sc8238_csp(texts,pins)
        if result.get('spec'):
            from model3d_details import sc8238_reference
            appearance=sc8238_reference(path)
            if appearance:
                result['spec']['appearance_profile']=appearance
                result['notes'].append(appearance['notice'])
        return result
    if re.search(r'\bOS04A10\b',text,re.I) and 'package dimensions (sheet 1 of 2)' in text.lower():
        dimensions={}
        def dimension(label,symbol):
            pattern=(re.escape(label)+r'\s+'+re.escape(symbol)+r'\s+([\d.]+)(?:\s+([\d.]+)\s+([\d.]+))?\s+(?:µm|μm)')
            hits=[(page,m) for page,t in enumerate(texts,1) for m in re.finditer(pattern,t,re.I)]
            if not hits or len({m.groups() for _,m in hits})!=1:return None
            page,match=hits[0]
            values=[float(v)/1000 for v in match.groups() if v is not None]
            minimum,typical,maximum=(values if len(values)==3 else [None,values[0],None])
            if minimum is not None and not 0<minimum<=typical<=maximum:return None
            dimensions[symbol]=dict(label=label,symbol=symbol,min=minimum,typ=typical,max=maximum,
                                    unit='mm',source_unit='µm',page=page,text=match[0])
            return (minimum,typical,maximum) if len(values)==3 else (typical,typical,typical)
        body_x=dimension('package body dimension x','A')
        body_y=dimension('package body dimension y','B')
        body_z=dimension('package heighta','C')
        ball_height=dimension('ball height','C1')
        body_thickness=dimension('package body thickness','C2')
        ball=dimension('ball diameter','D')
        pitch_x=dimension('ball pitch x axis','J1')
        pitch_y1=dimension('ball pitch y1 axis','J2')
        pitch_y2=dimension('ball pitch y2 axis','J3')
        edge_x=dimension('edge to ball center distance along x','S1')
        edge_y=dimension('edge to ball center distance along y','S2')
        die_x=dimension('die body dimension x','a')
        die_y=dimension('die body dimension y','b')
        glass_hits=[(page,m) for page,t in enumerate(texts,1)
                    for m in re.finditer(r'glass material thickness is\s+([\d.]+)\s*(?:µm|μm)',t,re.I)]
        glass=None
        if glass_hits and len({m[1] for _,m in glass_hits})==1:
            page,match=glass_hits[0];glass=float(match[1])/1000
            dimensions['GLASS']=dict(label='glass material thickness',symbol='GLASS',min=None,typ=glass,max=None,
                                      unit='mm',source_unit='µm',page=page,text=match[0])
        if all((body_x,body_y,body_z,ball_height,body_thickness,ball,pitch_x,pitch_y1,pitch_y2,edge_x,edge_y,die_x,die_y,glass)):
            ids={p['id'] for p in pins}
            rows=''.join(r for r in 'ABCDEFGHJK' if any(pid.startswith(r) for pid in ids))
            columns=15 if all(r+str(c) in ids for r in 'ABJK' for c in range(1,16)) else 0
            intervals=[pitch_y1[1]]+[pitch_y2[1]]*7+[pitch_y1[1]]
            missing=sorted({r+str(c) for r in rows for c in range(1,16)}-ids)
            optical_page=next((i for i,t in enumerate(texts,1) if 'array center and' in t.lower() and 'package center' in t.lower()),None)
            optical_ok=bool(optical_page and re.search(r'array center and\s+package center and\s+chip center\s+\(0\s*µm,\s*0\s*µm\)',texts[optical_page-1],re.I))
            top_view=bool(optical_page and 'top view' in texts[optical_page-1].lower())
            expected_ids={r+str(c) for r in 'ABJK' for c in range(1,16)} | {r+str(c) for r in 'CDEFGH' for c in (1,15)}
            if optical_ok and top_view and columns and len(rows)==10 and ids==expected_ids:
                px=pitch_x[1];total_y=sum(intervals);top=(body_y[1]-total_y)/2
                height_page=next(i for i,t in enumerate(texts,1) if 'package height' in t.lower())
                spec=dict(name='OS04A10',descr='OS04A10 BGA; top view, body center origin, mm',
                    body=[body_x[1],body_y[1]],pitch=[px,pitch_y2[1]],row_pitch_y=intervals,
                    edge=dict(left_to_col1=edge_x[1],right_to_colN=edge_x[1],top_to_rowA=top,bottom_to_rowN=top),
                    rows=rows,cols=15,missing=missing,ball_dia=ball[1],pad_dia=.225,
                    mask_margin=.0508,paste_dia=.2025,courtyard_excess=.25,
                    sensor_array=[7.8416,4.4544],
                    glass_thickness=glass,die_size=[die_x[1],die_y[1]],mechanical_dimensions=dimensions,
                    process_profile=dict(source='OS04A10 datasheet p114: NSMD copper 0.200–0.250 mm, nominal 0.225 mm',status='review_required'),
                    centers=dict(BGA=[0,0],OPT=[0,0]),height_min=body_z[0],height_nominal=body_z[1],height_max=body_z[2],
                    ball_height_min=ball_height[0],ball_height=ball_height[1],ball_height_max=ball_height[2],
                    body_thickness=[body_thickness[0],body_thickness[1],body_thickness[2]],
                    height_source=f'规格书 p{height_page} · Package Height C · max',
                    orientation_source=f'规格书 p{optical_page} 图 10-1：顶视图，阵列/封装/芯片中心均为 (0,0)')
                fp.geometry(spec)
                result.update(spec=spec,confirmed=False,needs=[],
                    sources=[dict(field=label,page=dimensions[symbol]['page'],text=dimensions[symbol]['text'])
                        for label,label_text,symbol,values in [('本体 X','package body dimension x','A',body_x),('本体 Y','package body dimension y','B',body_y),
                        ('本体最大高度','package height','C',body_z),('焊球凸出高度','ball height','C1',ball_height),
                        ('封装本体厚度','package body thickness','C2',body_thickness),('焊球直径','ball diameter','D',ball),('X 球距','ball pitch x axis','J1',pitch_x),
                        ('Y 边缘球距','ball pitch y1 axis','J2',pitch_y1),('Y 中间球距','ball pitch y2 axis','J3',pitch_y2),
                        ('X 边距','edge to ball center distance along x','S1',edge_x),('Y 边距','edge to ball center distance along y','S2',edge_y),
                        ('芯片宽度','die body dimension x','a',die_x),('芯片高度','die body dimension y','b',die_y)]]+
                        [dict(field='玻璃厚度',page=dimensions['GLASS']['page'],text=dimensions['GLASS']['text'])]+
                        [dict(field='PCB 推荐 NSMD 焊盘与锡膏',page=max(i for i,t in enumerate(texts,1) if 'recommended pcb nsmd ball pad size' in t.lower()),
                            text='ball pad opening 250 µm; copper 225 ± 25 µm; stencil opening 90–100% of PCB pad'),
                         dict(field='球径脚注',page=next(i for i,t in enumerate(texts,1) if 'ball placement: solder ball diameter 300' in t.lower()),
                            text='footnote says solder ball diameter 300 µm; table D nominal is 314 µm')]+
                        [dict(field='感光阵列宽度',page=optical_page,text='7841.6 µm'),
                         dict(field='感光阵列高度',page=optical_page,text='4454.4 µm'),
                         dict(field='光学中心与方向',page=optical_page,text='Top view; sensor array center = package center = chip center = (0 µm, 0 µm)')],
                    notes=['从规格书机械尺寸表及图 9-1 提取：A-B 与 J-K 行距为 J2=0.600 mm，其余相邻行距为 J3=0.955 mm。',
                        '图 10-1 明确光学阵列中心、封装中心、芯片中心重合于 (0,0)。',
                        '按 p114 厂家建议设置铜焊盘 0.225 mm（推荐 0.200–0.250 mm），锡膏开口暂用铜径 90%；阻焊扩展 0.0508 mm/侧为工具预设。',
                        '图 10-1 还给出感光阵列 7.8416 × 4.4544 mm，首像素位于封装底视左下方向。',
                        '注意：表格 D 的球径典型值为 0.314 mm，而脚注写“solder ball diameter 300 µm”；两处不同，需人工确认采用值。'])
                return result
            result['needs']=['OS04A10 球阵列、机械尺寸或光学中心数据不完整，未自动生成 PCB 规格']
            result['notes']=['已识别到 OS04A10 尺寸表，但需核对球阵列行列及图示方向。']
            return result
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


def inspect_gc5613_csp(texts,pins):
    """GC5613 C43YA V1.1: reviewed top/bottom orientation and page-13 table."""
    result=dict(spec=None,confirmed=False,notes=[],sources=[],needs=[])
    page=next((i for i,t in enumerate(texts,1) if 'Glass Thickness' in t and 'Millimeters' in t),None)
    if not page:result['needs']=['未找到 GC5613 毫米机械表'];return result
    t=texts[page-1];dims={}
    labels={'A':'Package Body Dimension X','B':'Package Body Dimension Y','C':'Package Height',
        'C1':'Ball Height','C2':'Package Body Thickness','C3':'Thickness from top glass surface to wafer',
        'C4':'Glass Thickness','D':'Ball Diameter','J1':'Pins pitch X axis','J2':'Pins pitch Y axis',
        'S1':'Edge to Pin Center Distance along X1','S2':'Edge to Pin Center Distance along Y1',
        'S3':'Edge to Pin Center Distance along X2','S4':'Edge to Pin Center Distance along Y2',
        'X':'BGA ball center to package center offset in X-direction',
        'Y':'BGA ball center to package center offset in Y-direction',
        'X1':'BGA ball center to chip center offset in X-direction',
        'Y1':'BGA ball center to chip center offset in Y-direction'}
    for symbol,label in labels.items():
        pattern=re.escape(label).replace(r'\ ',r'\s+')+r'\s+'+symbol+r'\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'
        m=re.search(pattern,t,re.I)
        if not m:result['needs'].append(label);continue
        nom,lo,hi=map(float,m.groups())
        if not lo<=nom<=hi:result['needs'].append(label+' 公差无效');continue
        dims[symbol]=dict(label=label,symbol=symbol,typ=nom,min=lo,max=hi,unit='mm',source_unit='mm',page=page,text=m[0])
        result['sources'].append(dict(field=symbol,page=page,text=m[0]))
    ids={p['id'] for p in pins};grid={r+str(c) for r in 'ABCDE' for c in range(1,10)}
    if ids!=grid-{'B6','B7'} or len(pins)!=43:result['needs'].append('GC5613 必须有 43 个实体球位，仅 B6/B7 缺球，NC A5/B8 必须保留')
    counts=[('Total Ball Count','N','43'),('Ball Count X axis','N1','9'),('Ball Count Y axis','N2','5')]
    if not all(re.search(re.escape(label).replace(r'\ ',r'\s+')+r'\s+'+sym+r'\s+'+val+r'\b',t) for label,sym,val in counts):
        result['needs'].append('GC5613 尺寸表球数/行列数不匹配')
    drawing=next((i for i,t in enumerate(texts,1) if 'Top View Image Size' in t and 'Bottom View BGA Size' in t),None)
    bga=re.search(r'BGA center\s+coordinate is\s*\(([^,]+),([^\)]+)\)',t)
    opt=re.search(r'optical center coordinate is\s*\(([^,]+),([^\)]+)\)',t)
    if not drawing or not bga or not opt or not re.search(r'with\s+[μµ]m unit',t):result['needs'].append('GC5613 顶视方向或中心微米单位不完整')
    featurepage=next((i for i,t in enumerate(texts,1) if 'Pixel size:' in t and 'Active image size:' in t),None)
    ft=texts[featurepage-1] if featurepage else ''
    pixel=re.search(r'Pixel size:\s*([\d.]+)[μµ]m\s*x\s*([\d.]+)[μµ]m',ft)
    active=re.search(r'Active image size:\s*(\d+)\s*x\s*(\d+)',ft)
    if not pixel or not active:result['needs'].append('缺少活动阵列及像素尺寸')
    if result['needs']:return result
    n=lambda k:dims[k]['typ']
    center=[float(v)/1000 for v in bga.groups()];optical=[float(v)/1000 for v in opt.groups()]
    derived=[(n('S3')-n('S1'))/2,(n('S4')-n('S2'))/2]
    if any(abs(a-b)>1e-7 for a,b in zip(center,derived)):
        result['needs']=['中心脚注与顶视边距尺寸链不一致'];return result
    sensor=[int(active[i])*float(pixel[i])/1000 for i in (1,2)]
    spec=dict(name='GC5613_C43YA',descr='GC5613-C43YA CSP43; top view, body-center origin, mm',kicad_version=6,
        body=[n('A'),n('B')],pitch=[n('J1'),n('J2')],rows='ABCDE',cols=9,missing=['B6','B7'],
        edge=dict(left_to_col1=n('S3'),right_to_colN=n('S1'),top_to_rowA=n('S2'),bottom_to_rowN=n('S4')),
        centers=dict(BGA=center,OPT=optical),ball_dia=n('D'),pad_dia=.24,paste_dia=.24,mask_margin=.0508,courtyard_excess=.25,
        height_min=dims['C']['min'],height_nominal=n('C'),height_max=dims['C']['max'],ball_height=n('C1'),
        glass_thickness=n('C4'),top_to_wafer=n('C3'),body_thickness=[dims['C2']['min'],n('C2'),dims['C2']['max']],
        sensor_array=sensor,mechanical_dimensions=dims,height_source=f'p{page} C max',
        orientation_source=f'p{drawing} top view A1 upper-left; S3 left / S1 right; p{page} signed center footnote',
        process_profile=dict(source='工具工艺预设：铜径/锡膏 0.240 mm（球径 80%），阻焊每侧 +0.0508 mm；非厂家推荐值',status='review_required'))
    fp.geometry(spec)
    result['spec']=spec
    result['sources'] += [dict(field='顶视有符号中心',page=page,text=bga[0]+'; '+opt[0]+'; μm → mm'),
        dict(field='活动感光尺寸（推导）',page=featurepage,text=pixel[0]+'; '+active[0]+f'; derived {sensor} mm')]
    result['notes']=[
        '顶视 A1 左上；仅 B6/B7 无球，A5/B8 为 NC 实体球；符号采用 p10–11 引脚表。',
        'p10 球位图 IN_CLK / PLVSS 与 p11 表 INCLK / PLLVSS 拼写不同，按引脚表名称保留，脚号相同。',
        'p13 X/X1 标称 +0.0035 mm 对应底视方向；顶视按 p12 和 p13 有符号脚注取 -0.0035 mm，并已用 S3/S1 闭合校验。',
        '活动感光区由 2960×1666、2 μm 推导为 5.920×3.332 mm；p14 默认首像素左下，A1 左上。',
        'p15 另有每侧 4 dummy 像素及上方 20 light-shielded 行；其与机械光学中心的精确对应未标注，不把未确认边界当作精密尺寸。',
        spec['process_profile']['source']]
    return result


def inspect_sc8238_csp(texts,pins):
    """Reviewed CSP convention: S3 is left after reflecting the bumps-up view."""
    result=dict(spec=None,confirmed=False,notes=[],sources=[],needs=[])
    page=next((i for i,t in enumerate(texts,1) if 'Glass Thickness' in t and 'Millimeters' in t),None)
    if not page:result['needs']=['未找到 CSP 毫米尺寸表'];return result
    t=texts[page-1];dims={}
    labels={'A':'Package Body Dimension X','B':'Package Body Dimension Y','C':'Package Height',
        'C1':'Ball Height','C2':'Package Body Thickness','C3':'Thickness from top glass surface to wafer',
        'C4':'Glass Thickness','D':'Ball Diameter','J1':'Pins Pitch X axis','J2':'Pins Pitch Y axis',
        'S1':'Edge to Pin Center Distance along X1','S2':'Edge to Pin Center Distance along Y1',
        'S3':'Edge to Pin Center Distance along X1','S4':'Edge to Pin Center Distance along Y1'}
    for symbol,label in labels.items():
        pattern=re.escape(label).replace(r'\ ',r'\s+')+r'\s+'+symbol+r'\s+([\d.]+)\s+([\d.]+|-)\s+([\d.]+|-)'
        m=re.search(pattern,t,re.I)
        if not m:result['needs'].append(label);continue
        nominal=float(m[1]);minimum=None if m[2]=='-' else float(m[2]);maximum=None if m[3]=='-' else float(m[3])
        if minimum is not None and not minimum<=nominal<=maximum:result['needs'].append(label+' 公差无效');continue
        dims[symbol]=dict(label=label,symbol=symbol,min=minimum,typ=nominal,max=maximum,unit='mm',page=page,text=m[0])
        result['sources'].append(dict(field=symbol,page=page,text=m[0]))
    if result['needs']:return result
    ids={p['id'] for p in pins};grid={r+str(c) for r in 'ABCDEF' for c in range(1,8)}
    if ids!=grid-{'B4'} or len(pins)!=41:result['needs']=['CSP 引脚必须为 A1–F7，只有 B4 缺球，共 41 脚'];return result
    drawing=next((i for i,t in enumerate(texts,1) if 'Pixel center' in t and 'BGA center' in t),None)
    if not drawing:result['needs']=['缺少顶视方向和光学中心依据'];return result
    dt=texts[drawing-1]
    pixel=re.search(r'Pixel center\s*\(\s*([\d.-]+),\s*([\d.-]+)\)',dt)
    top_bga=re.search(r'BGA center\s*\(\s*([\d.-]+),\s*([\d.-]+)\)',dt)
    if not pixel or not top_bga:result['needs']=['光学/BGA 中心读取失败'];return result
    n=lambda s:dims[s]['typ']
    center=[float(top_bga[1])/1000,float(top_bga[2])/1000];opt=[float(pixel[1])/1000,float(pixel[2])/1000]
    # Array dimensions and pixel pitch are explicitly listed on p2. Use full array,
    # not the cropped 3840x2160 output; preserve derivation as a source.
    overview='\n'.join(texts[:3])
    arr=re.search(r'像素阵列[：:]\s*(\d+)H\s*x\s*(\d+)V',overview)
    pitch=re.search(r'像素尺寸[：:]\s*([\d.]+)\s*μm\s*x\s*([\d. ]+)\s*μm',overview)
    sensor=None
    if arr and pitch:sensor=[int(arr[1])*float(pitch[1])/1000,int(arr[2])*float(pitch[2].replace(' ',''))/1000]
    spec=dict(name='SC8238_CS3NN00',descr='41-pin CSP, top view, mm',kicad_version=6,body=[n('A'),n('B')],pitch=[n('J1'),n('J2')],
        rows='ABCDEF',cols=7,missing=['B4'],edge=dict(left_to_col1=n('S3'),right_to_colN=n('S1'),top_to_rowA=n('S2'),bottom_to_rowN=n('S4')),
        centers=dict(BGA=center,OPT=opt),ball_dia=n('D'),pad_dia=.24,paste_dia=.24,mask_margin=.0508,courtyard_excess=.25,
        height_min=dims['C']['min'],height_nominal=n('C'),height_max=dims['C']['max'],ball_height=n('C1'),
        glass_thickness=n('C4'),top_to_wafer=n('C3'),body_thickness=[dims['C2']['min'],n('C2'),dims['C2']['max']],
        mechanical_dimensions=dims,height_source=f'p{page} C',orientation_source=f'p{drawing} top view: S3 left / S1 right',
        process_profile=dict(source='工具参考预设：铜径为球径 80%；本规格书未提供 PCB 推荐焊盘',status='review_required'))
    if sensor:
        spec['sensor_array']=sensor
        result['sources'].append(dict(field='感光区域尺寸（推导）',page=2,text=f'像素阵列 {arr[1]} × {arr[2]}；像素尺寸 {pitch[1]} × {pitch[2]} µm；推导 {sensor} mm'))
    fp.geometry(spec)
    result['spec']=spec
    result['sources'].append(dict(field='顶视 BGA / 光学中心',page=drawing,text=f'{top_bga[0]}; {pixel[0]}; µm → mm'))
    result['notes']=[f'CSP 41 个实体球位，B4 缺球；RESERVED B2 依引脚表 NC 保留焊球。',
        '顶视原点为本体中心；BGA=(+0.043416,-0.027626) mm；光学=(+0.043416,-0.238626) mm。',
        '感光尺寸由完整像素阵列及像素间距推导，不使用裁切输出尺寸；内部芯片轮廓未标尺寸，不额外虚构。',
        spec['process_profile']['source'],
        '规格书“41(4NC)”统计不含额外标为 RESERVED/NC 的 B2；按 41 个球位保留所有引脚。']
    return result


def check(project):
    pcb=project.get('pcb') or {};spec=pcb.get('spec')
    if not spec:raise ValueError('PCB 尺寸尚不完整，请在 PCB 封装页补齐参数')
    pads=fp.geometry(spec)
    fp.require_height(spec)
    ids=[p['id'] for p in project['pins']]
    if len(set(ids))!=len(ids) or set(ids)!=fp.electrical_ids(spec):raise ValueError('符号脚号与 PCB 焊盘编号不完全一致')
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
    import assistant_core as core
    names=fp.native_asset_names(spec,report)
    native=[p for p in (root/'pcb/allegro').iterdir() if p.name.lower() in names]
    if len(native)!=len(names):raise ValueError('生成结果中的 Cadence 库文件不完整')
    manifest['file_hashes']=core.artifact_hashes(root,[Path(symbol['olb']),Path(symbol['olb']).parent/'project.json',root/'pcb/spec.json',*native])
    (root/'verification.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=shutil.make_archive(str(root),'zip',root)
    return dict(directory=str(root),olb=symbol['olb'],report=manifest,archive=archive,pcb_directory=str(root/'pcb'))
