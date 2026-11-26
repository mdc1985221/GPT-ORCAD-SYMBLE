"""Reviewed connector drawing adapters, separate electrical pins and hold-downs."""
from pathlib import Path
import hashlib,json,copy
import html,math,re
BASE=Path(__file__).parent

def pth_geometry(spec):
    if spec.get('kind')!='pth_connector':raise ValueError('不是通孔连接器')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',spec['name']):raise ValueError('连接器名称无效')
    if len(spec['body'])!=2 or any(not isinstance(n,(int,float)) or not math.isfinite(n) or n<=0 for n in spec['body']):raise ValueError('连接器本体尺寸无效')
    sizes=[spec[k] for k in ('drill','pad','mask_diameter')]
    if any(not isinstance(n,(int,float)) or not math.isfinite(n) or n<=0 for n in sizes) or not sizes[0]<sizes[1]<=sizes[2]:raise ValueError('通孔/铜/阻焊尺寸无效')
    result=[];seen=set()
    for pin in spec['positions']:
        if not re.fullmatch('[A-Za-z0-9]+',pin['id']) or pin['id'] in seen or any(not isinstance(pin[k],(int,float)) or not math.isfinite(pin[k]) for k in ('x','y')):raise ValueError('通孔脚号或坐标无效')
        seen.add(pin['id']);result.append((pin['id'],pin['x'],pin['y']))
    if not result:raise ValueError('通孔连接器没有引脚')
    return result

def pth_presentation(spec):
    pads=pth_geometry(spec);w,h=spec['body'];r=spec['pad']/2
    pieces=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-w/2-2} {-h/2-2} {w+4} {h+4}"><rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" fill="none" stroke="#798eb6" stroke-width=".10"/>']
    for pid,x,y in pads:
        y=-y
        pieces.append(f'<rect x="{x-r}" y="{y-r}" width="{2*r}" height="{2*r}" fill="#a89961"/>' if pid=='1' else f'<circle cx="{x}" cy="{y}" r="{r}" fill="#a89961"/>')
        pieces.append(f'<circle cx="{x}" cy="{y}" r="{spec["drill"]/2}" fill="#f7f9fc"/><text x="{x}" y="{y+.16}" font-size=".45" text-anchor="middle">{html.escape(pid)}</text>')
    return dict(kind='polygon_smd',svg=''.join(pieces)+'</svg>')

def profile(path):
    if not Path(path).is_file():return None
    template=BASE/'templates/connector/shouhan_12502_12p.json'
    if not template.is_file():return None
    spec=json.loads(template.read_text(encoding='utf8'))
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=spec['source_pdf_sha256']:return None
    pins=[dict(id=str(i),name=str(i),type='PASS',part='A',side='',group='',page=1,source=str(Path(path).resolve()),raw=f'12502 SERIES 1.25mm-12P LT; 12P dimension row; pin {i} numbering is a provisional top-view convention, not marked in drawing',confidence=.9,conflicts=[]) for i in range(1,13)]
    return dict(pins=pins,pcb=dict(spec=spec,confirmed=False,needs=list(spec['unresolved']),sources=spec['sources'],notes=spec['notes']))
