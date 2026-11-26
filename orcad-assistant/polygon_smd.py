"""Dimensioned polygon-SMD profiles; copper, mask and paste remain independent."""
import json,math,re,hashlib,html
from pathlib import Path
BASE=Path(__file__).parent

def area(poly):return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])))/2

def validate(spec):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if spec.get('kind')!='polygon_smd' or spec.get('revision')!=1:raise ValueError('异形封装版本无效')
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,39}',spec['name']):raise ValueError('异形封装名称无效')
    if len(spec['body'])!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in spec['body']):raise ValueError('本体尺寸无效')
    if not isinstance(spec.get('height_max'),(float,int)) or not 0<spec['height_max']<100:raise ValueError('最大高度无效')
    ids=set();coppers=[]
    for p in spec['pads']:
        if not re.fullmatch('[A-Za-z0-9]+',p['id']) or p['id'] in ids:raise ValueError('脚号重复或无效')
        if p.get('role','electrical') not in ('electrical','mounting'):raise ValueError('焊盘角色无效')
        ids.add(p['id'])
        if len(p['xy'])!=2 or any(not math.isfinite(v) for v in p['xy']):raise ValueError('连接点坐标无效')
        shapes={}
        for layer in ('copper','mask','paste'):
            if not p.get(layer):raise ValueError('缺少独立铜/阻焊/锡膏轮廓')
            polys=[]
            for coords in p[layer]:
                if len(coords)<3 or any(len(v)!=2 or any(not isinstance(n,(int,float)) or not math.isfinite(n) or abs(n)>100 for n in v) for v in coords):raise ValueError('多边形坐标无效')
                poly=Polygon(coords)
                if not poly.is_valid or poly.area<=1e-8:raise ValueError('异形轮廓自交或面积无效')
                polys.append(poly)
            shapes[layer]=unary_union(polys)
        if not shapes['copper'].buffer(.0001).covers(Polygon([(p['xy'][0]-.00001,p['xy'][1]-.00001),(p['xy'][0]+.00001,p['xy'][1]-.00001),(p['xy'][0],p['xy'][1]+.00001)])):raise ValueError('焊盘连接点未落在铜内')
        if shapes['paste'].difference(shapes['copper'].buffer(.0001)).area>1e-7:raise ValueError('锡膏超出铜轮廓')
        if p.get('mask_type')=='NSMD' and shapes['copper'].difference(shapes['mask'].buffer(.0001)).area>1e-7:raise ValueError('NSMD 阻焊开口不能小于铜')
        if p.get('mask_type')=='SMD' and shapes['mask'].difference(shapes['copper'].buffer(.0001)).area>1e-7:raise ValueError('SMD 阻焊开口必须位于铜内')
        if shapes['paste'].difference(shapes['mask'].buffer(.0001)).area>1e-7:raise ValueError('锡膏开口超出阻焊开口')
        coppers.append(shapes['copper'])
    if not ids:raise ValueError('焊盘为空')
    for i,a in enumerate(coppers):
        if any(a.intersection(b).area>1e-8 for b in coppers[i+1:]):raise ValueError('不同脚号铜焊盘重叠')
    return [(p['id'],*p['xy']) for p in spec['pads']]

def profile(path):
    import fitz
    with fitz.open(path) as doc:texts=[p.get_text() for p in doc]
    if not all(t in '\n'.join(texts) for t in ('TPS543620','RPY0014A','4225171/D','PIN 1 & 5: 93%')):return None
    page=next((i for i,t in enumerate(texts,1) if 'Table 5-1. Pin Functions' in t),None)
    if not page:return None
    spec=json.loads((BASE/'templates/qfn/tps543620.json').read_text(encoding='utf8'))
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=spec['source_pdf_sha256']:return None
    validate(spec)
    # Fail closed on identity changes; this is an explicit reviewed adapter,
    # not a claim of arbitrary PDF visual extraction.
    if not all(t in texts[page-1] for t in ('SYNC/FSEL','8, 12','9, 11','PGND','BOOT')):return None
    records=[('1','SYNC/FSEL','IN'),('2','MODE','IN'),('3','PGOOD','OUT'),('4','FB','IN'),('5','AGND','GND'),('6','BP5','OUT'),('7','EN','IN'),('8','VIN','PWR'),('9','PGND','GND'),('10','SW','OUT'),('11','PGND','GND'),('12','VIN','PWR'),('13','SW','OUT'),('14','BOOT','PWR')]
    pins=[dict(id=i,name=n,type=t,part='A',side='',group='',page=page,source=str(Path(path).resolve()),raw=f'p{page} Table 5-1 {i} {n}; electrical type normalized from function',confidence=.9,conflicts=[]) for i,n,t in records]
    return dict(pins=pins,pcb=dict(spec=spec,confirmed=False,needs=[],sources=spec['sources'],notes=spec['notes']+['已核对 TPS543620 / RPY0014A / 4225171D 版本适配；不是通用 QFN 自动视觉识别。']))

def native_assets(spec):
    result={}
    for pad in spec['pads']:
        signature=json.dumps({k:pad[k] for k in ('xy','copper','mask','paste')},sort_keys=True)
        key='qp_'+hashlib.sha256(signature.encode()).hexdigest()[:14]
        result[pad['id']]=key
    return result

def svg(spec,layers=('copper','mask','paste'),numbers=True):
    colors=dict(copper='#4f7bb0',mask='#439c71',paste='#e17b50');w,h=spec['body']
    ext=[v for pad in spec['pads'] for layer in ('copper','mask','paste') for contour in pad[layer] for v in contour]
    x0=min(v[0] for v in ext)-.8;x1=max(v[0] for v in ext)+.8;y0=-max(v[1] for v in ext)-.8;y1=-min(v[1] for v in ext)+.8
    viewbox=f'{x0} {y0} {x1-x0} {y1-y0}'
    chunks=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" style="width:100%;height:100%;background:#fafcff">']
    if spec.get('draw_body',True):chunks.append(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" fill="#eef1f8" stroke="#99a5b8" stroke-width=".015"/>')
    for layer in layers:
        for pad in spec['pads']:
            for contour in pad[layer]:
                pts=' '.join(f'{x},{-y}' for x,y in contour)
                chunks.append(f'<polygon data-pad="{pad["id"]}" data-layer="{layer}" points="{pts}" fill="{colors[layer] if layer=="copper" else "none"}" stroke="{colors[layer]}" stroke-width=".012"/>')
    if numbers:
        for p in spec['pads']:
            x,y=p['xy'];chunks.append(f'<text x="{x}" y="{-y}" font-size=".105" text-anchor="middle" dominant-baseline="central" fill="#fff">{p["id"]}</text>')
    if spec.get('family')!='connector':chunks.append('<circle cx="-1.9" cy="-1.5" r=".045" fill="#db893f"/>')
    chunks.append('</svg>')
    return ''.join(chunks)

def preview(spec,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    title=html.escape(spec['name']);blocks=''.join(f'<section><h2>{label}</h2><div style="height:470px">{svg(spec,layers)}</div></section>' for label,layers in [('铜 / 阻焊 / 锡膏叠加',('copper','mask','paste')),('铜焊盘',('copper',)),('阻焊开口',('mask',)),('锡膏开口',('paste',))])
    if spec.get('family')=='mosfet':
        notes=''.join(f'<li>{html.escape(str(n))}</li>' for n in spec.get('notes',[])+spec.get('needs',[]))
        path=output/(spec['name']+'_preview.html')
        path.write_text(f'<!doctype html><meta charset="utf-8"><title>{title}</title><style>body{{font:15px Segoe UI,Microsoft YaHei,sans-serif;background:#f2f5fa;color:#24344c;margin:32px}}main{{max-width:1150px;margin:auto}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}section{{background:white;padding:18px;border-radius:14px}}li,p{{line-height:1.8}}</style><main><h1>{title} · MOSFET</h1><p>PCB 顶视 · mm · 蓝=铜，绿=阻焊开口，橙=锡膏。{len(spec["pads"])} 个电气焊盘；端子与 PCB 铜焊盘分别建模。目标设计及工艺尚待验收。</p><div class="grid">{blocks}</div><ul>{notes}</ul></main>',encoding='utf8')
        return str(path)
    if spec.get('family')=='connector':
        electrical=sum(p.get('role','electrical')=='electrical' for p in spec['pads'])
        mounting=len(spec['pads'])-electrical
        notes=''.join(f'<li>{html.escape(str(n))}</li>' for n in spec.get('unresolved',[])+spec.get('notes',[]))
        path=output/(spec['name']+'_preview.html')
        path.write_text(f'<!doctype html><meta charset="utf-8"><title>{title}</title><style>body{{font:15px Segoe UI,Microsoft YaHei,sans-serif;background:#f2f5fa;color:#24344c;margin:32px}}main{{max-width:1150px;margin:auto}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}section{{background:white;padding:18px;border-radius:14px}}h2{{font-size:17px}}li,p{{line-height:1.8}}</style><main><h1>{title} · 连接器</h1><p>PCB 顶视 · mm · 蓝=铜，绿=阻焊开口，橙=锡膏。{electrical} 个电气接点、{mounting} 个机械固定焊盘。MP 标签仅供预览识别，原生固定焊盘不编号。预览不等于目标设计验收。</p><div class="grid">{blocks}</div><ul>{notes}</ul></main>',encoding='utf8')
        return str(path)
    (output/(spec['name']+'_preview.html')).write_text(f'<!doctype html><meta charset="utf-8"><title>{title}</title><style>body{{font:15px Segoe UI,Microsoft YaHei,sans-serif;background:#f2f5fa;color:#24344c;margin:32px}}main{{max-width:1150px;margin:auto}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}section{{background:white;padding:18px;border-radius:14px}}h2{{font-size:17px}}p{{line-height:1.8}}</style><main><h1>{title} · 异形 QFN</h1><p>官方图 p47 顶视方向 · mm · 蓝=铜，绿=阻焊开口，橙=锡膏。14 个实体引脚；10 号 SMD，其他 NSMD。预览不等于目标工程制造验收。</p><div class="grid">{blocks}</div><p>PCB 焊盘与器件端子不同；3D 端子需另按 p46。工艺预设、参考尺寸及验证范围见报告。</p></main>',encoding='utf8')
    return str(output/(spec['name']+'_preview.html'))
