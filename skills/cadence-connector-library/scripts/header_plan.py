"""Explicit-parameter dual-row header plan. No default drill, copper or height."""
import argparse,json,math
from pathlib import Path

def plan(pins,pitch,row_spacing,drill=None,pad=None,height=None):
    if isinstance(pins,bool) or not isinstance(pins,int) or pins<2 or pins%2 or pins>400:raise ValueError('脚数必须是2–400的偶数')
    for v in (pitch,row_spacing):
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('脚距/排距必须为正毫米数')
    for v in (drill,pad,height):
        if v is not None and (not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<=0):raise ValueError('孔径/焊盘/高度无效')
    if drill is not None and pad is not None and drill>=pad:raise ValueError('铜径须大于成品孔径')
    if pad is not None and pad>=min(pitch,row_spacing):raise ValueError('铜焊盘相互重叠')
    positions=[]
    for i in range(pins//2):
        x=(i-(pins//2-1)/2)*pitch
        positions.extend([dict(id=str(2*i+1),x=round(x,6),y=-row_spacing/2,shape='square' if i==0 else 'circle'),dict(id=str(2*i+2),x=round(x,6),y=row_spacing/2,shape='circle')])
    needs=[label for k,label in [(drill,'成品孔径/电镀要求'),(pad,'铜焊盘尺寸/阻焊工艺'),(height,'本体高度及轮廓')] if k is None]
    return dict(kind='dual_row_pth_plan',status='PREVIEW_ONLY' if needs else 'GEOMETRY_PLAN_ONLY',pins=pins,pitch=pitch,row_spacing=row_spacing,drill=drill,pad=pad,height=height,units='mm',origin='array center; top view; pin1 bottom-left; odd bottom/even top',positions=positions,needs=needs,sources=dict(pitch='explicit argument; caller must retain PDF/user provenance',row_spacing='explicit argument; caller must retain PDF/user provenance'))

def preview(data,path):
    # Pin markers express position only. Their screen size is not a copper diameter.
    rows=data['pins']//2;w=max(540,rows*38+80);h=250;elements=[]
    for pin in data['positions']:
        x=50+((int(pin['id'])-1)//2)*38;y=133 if int(pin['id'])%2 else 95
        marker=f'<rect x="{x-11}" y="{y-11}" width="22" height="22"' if pin['id']=='1' else f'<circle cx="{x}" cy="{y}" r="11"'
        elements.append(marker+' fill="none" stroke="#b9c6df" stroke-width="3"/><text x="'+str(x)+'" y="'+str(y+4)+'" text-anchor="middle" font-size="12" fill="#fff">'+pin['id']+'</text>')
    sw=260;sh=rows*25+90;sym=[]
    for i in range(rows):
        y=50+i*25
        for n,x,tx in [(2*i+1,60,100),(2*i+2,200,160)]:
            sym.append(f'<path d="M {x} {y} H {tx}" stroke="#537ce0"/><circle cx="{x}" cy="{y}" r="2" fill="#537ce0"/><text x="{tx+5 if n%2 else tx-5}" y="{y+4}" text-anchor="{"start" if n%2 else "end"}" font-size="12" fill="#42597c">{n}</text>')
    content='''<!doctype html><meta charset="utf-8"><title>双排排母尺寸计划</title><style>body{background:#f2f5fb;color:#24354d;font:15px Segoe UI,Microsoft YaHei;margin:30px}main{max-width:1420px;margin:auto}.grid{display:grid;grid-template-columns:320px minmax(400px,1fr);gap:20px}.panel{background:white;padding:16px;border-radius:12px;overflow:auto;height:620px}.toolbar button{border:1px solid #dae2ee;background:white;color:#385c98;border-radius:6px;padding:8px;margin:4px;cursor:pointer}.note{background:#fff0d0;padding:16px;border-radius:10px;line-height:1.8}.viewport{overflow:auto;min-height:400px}.viewport svg{transform-origin:0 0}h2{font-size:18px}</style><main>'''
    content+=f'<h1>双排 {data["pins"]} PIN 排母 · 编号与坐标预览</h1><p>脚距 {data["pitch"]} mm · 排距 {data["row_spacing"]} mm · 本次由用户确认；所附12P贴片PDF不用于此40P排母尺寸。</p><p class="note">待补齐：'+ '、'.join(data['needs'])+'。下图圆圈/方框仅标孔位与编号，屏幕大小不是实际孔径或铜径；未生成可生产PCB封装。</p><div class="grid">'
    sym_svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}"><rect x="100" y="30" width="60" height="{rows*25+15}" fill="white" stroke="#d02a32"/><circle cx="110" cy="40" r="4" fill="#bd161e"/>{"".join(sym)}</svg>'
    pcb_svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="background:#101820"><defs><pattern id="g" width="19" height="19" patternUnits="userSpaceOnUse"><path d="M19 0H0V19" stroke="#46515c" stroke-width=".5" fill="none"/></pattern></defs><rect width="100%" height="100%" fill="url(#g)"/>{"".join(elements)}<text x="30" y="220" fill="#dae5f9" font-size="13">PCB 顶视：下奇上偶，左下1脚；仅孔位计划</text></svg>'
    for name,svg in [('原理符号 · 奇左偶右',sym_svg),('PCB 孔位 · 下奇上偶',pcb_svg)]:
        content+=f'<section class="panel"><h2>{name}</h2><div class="toolbar"><button onclick="scale(this,.85)">－</button><button onclick="scale(this,1.18)">＋</button><button onclick="scale(this,0)">复位</button></div><div class="viewport">{svg}</div></section>'
    content+='</div></main><script>function scale(b,k){let s=b.closest("section").querySelector("svg"),z=k?Math.max(.3,Math.min(5,(+s.dataset.zoom||1)*k)):1;s.dataset.zoom=z;s.style.transform=`scale(${z})`;}document.querySelectorAll(".viewport").forEach(v=>v.onwheel=e=>{if(!e.ctrlKey)return;e.preventDefault();scale(v.closest("section").querySelector("button"),e.deltaY<0?1.18:.85)})</script>'
    Path(path).write_text(content,encoding='utf8')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--pins',type=int,required=True);a.add_argument('--pitch',type=float,required=True);a.add_argument('--row-spacing',type=float,required=True);a.add_argument('--drill',type=float);a.add_argument('--pad',type=float);a.add_argument('--height',type=float);a.add_argument('--output',type=Path,required=True);v=a.parse_args()
    d=plan(v.pins,v.pitch,v.row_spacing,v.drill,v.pad,v.height);v.output.mkdir(parents=True,exist_ok=True);(v.output/'plan.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8');preview(d,v.output/'preview.html');print(d['status'])
