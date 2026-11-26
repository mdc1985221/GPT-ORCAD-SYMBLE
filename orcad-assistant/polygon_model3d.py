"""QFN package body/terminal STEP, separate from the larger PCB land pattern."""
import json,math,hashlib
from pathlib import Path

def plan(spec,options):
    import polygon_smd
    polygon_smd.validate(spec)
    if options.get('confirmed') is not True:raise ValueError('请确认 QFN 机械高度与端子外观近似')
    ref=spec.get('terminal_profile')
    if not ref:raise ValueError('缺少独立的器件端子机械数据；PCB 焊盘不能冒充 3D 引脚')
    total=options.get('total_height',ref['total_height'])
    if not isinstance(total,(int,float)) or not math.isfinite(total) or not spec['height_min']<=total<=spec['height_max']:raise ValueError('QFN 总高超出规格书范围')
    if {p['id'] for p in ref['contours']}!={p['id'] for p in spec['pads']}:raise ValueError('3D 端子编号与 PCB 不一致')
    from shapely.geometry import Polygon,box
    mosfet=spec.get('family')=='mosfet'
    body=box(-spec['body'][0]/2,-spec['body'][1]/2,spec['body'][0]/2,spec['body'][1]/2)
    envelope=body.buffer(.25) if mosfet else body.buffer(.00001)
    polys=[]
    for t in ref['contours']:
        p=Polygon(t['outline'])
        if not p.is_valid or p.area<=0 or not envelope.covers(p):raise ValueError('3D 端子轮廓无效或超出允许机械包络')
        if any(p.intersection(q).area>1e-8 for q in polys):raise ValueError('3D 端子重叠')
        polys.append(p)
    return dict(revision=1,kind='polygon_smd',name=spec['name'],units='mm',body=spec['body'],total_height=total,
        terminal_profile=ref,pads=[(p['id'],*p['xy']) for p in spec['pads']],optical=None,
        family=spec.get('family','qfn'),approximation=ref['notice'],dimension_source=options.get('dimension_source','TI p46 package terminal dimensions'))

def generate(folder):
    import cadquery as cq
    folder=Path(folder);p=json.loads((folder/'input.json').read_text(encoding='utf8'));w,h=p['body'];z=p['total_height'];ref=p['terminal_profile'];stand=ref['standoff'];thick=ref['terminal_thickness']
    body=cq.Solid.makeBox(w,h,z-stand,cq.Vector(-w/2,-h/2,stand));shapes=[]
    for t in ref['contours']:
        shape=cq.Workplane('XY').polyline(t['outline']).close().extrude(thick).val()
        body=body.cut(shape).clean();shapes.append(('TERMINAL_'+t['id'],shape,[.75,.78,.82]))
    # Pin-1 top dimple is a display approximation; p46 identifies the corner,
    # but does not dimension its size/depth. Keep full nominal body envelope.
    mark_y=-h/2+.2 if p.get('family')=='mosfet' else h/2-.2
    mark=cq.Solid.makeCylinder(.065,.002,cq.Vector(-w/2+.2,mark_y,z-.002))
    body=body.cut(mark).clean();shapes=[('BODY',body,[.14,.15,.18]),('PIN1_MARK_APPROX',mark,[.62,.63,.66])]+shapes
    for name,shape,_ in shapes:
        if not shape.isValid() or len(shape.Solids())!=1:raise ValueError('Invalid QFN solid '+name)
    assembly=cq.Assembly(name=p['name'])
    for name,shape,color in shapes:assembly.add(shape,name=name,color=cq.Color(*color))
    target=folder/(p['name']+'.step');assembly.export(str(target),exportType='STEP')
    loaded=cq.importers.importStep(str(target)).val();solids=loaded.Solids()
    if not loaded.isValid() or len(solids)!=len(shapes):raise ValueError('QFN STEP topology/count mismatch')
    def bounds(s):
        b=s.BoundingBox();return [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]
    actual=bounds(loaded);wanted=[-w/2,-h/2,0,w/2,h/2,z]
    if p.get('family')=='mosfet':
        vertices=[v for t in ref['contours'] for v in t['outline']]
        wanted=[min(-w/2,min(v[0] for v in vertices)),min(-h/2,min(v[1] for v in vertices)),0,
                max(w/2,max(v[0] for v in vertices)),max(h/2,max(v[1] for v in vertices)),z]
    if max(abs(a-b) for a,b in zip(actual,wanted))>1e-5:raise ValueError('QFN STEP envelope mismatch')
    rest=list(solids)
    for name,shape,_ in shapes:
        found=[s for s in rest if max(abs(a-b) for a,b in zip(bounds(s),bounds(shape)))<1e-5 and abs(s.Volume()-shape.Volume())<1e-6]
        if len(found)!=1:raise ValueError('QFN terminal/body mismatch '+name)
        rest.remove(found[0])
    meshes=[]
    # Tessellate matched STEP-reimported solids, so previews show the saved file.
    remaining=list(solids)
    for name,shape,color in shapes:
        matched=next(s for s in remaining if max(abs(a-b) for a,b in zip(bounds(s),bounds(shape)))<1e-5 and abs(s.Volume()-shape.Volume())<1e-6)
        remaining.remove(matched)
        v,t=matched.tessellate(.01,.2);meshes.append(dict(name=name,color=color,opacity=1,vertices=[[q.x,q.y,q.z] for q in v],triangles=t))
    (folder/'mesh.json').write_text(json.dumps(dict(kind='polygon_smd',bounds=actual,meshes=meshes,optical=None,appearance_notice=ref['notice'])),encoding='utf8')
    report=dict(status='PASS',revision=1,kind='polygon_smd',step=target.name,plan=p,units='mm',solids=len(solids),balls=0,terminals=len(ref['contours']),bounds=actual,
        checks=['STEP reimport topology/count','body envelope and Z=0','per-terminal bounding box and volume','separate package-terminal / PCB-land definitions'],
        file_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (target,folder/'mesh.json')})
    (folder/'model3d.json').write_text(json.dumps(report,indent=2),encoding='utf8')
