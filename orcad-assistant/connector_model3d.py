"""PTH socket reference model; explicit mechanical and appearance parameters only.

Run with the optional CadQuery runtime: connector_model3d.py SPEC OUTPUT.
"""
import json,sys,hashlib
from pathlib import Path

def generate(spec,folder):
    import cadquery as cq
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    w,d=spec['body'];h=spec['height_nominal'];tail=spec['tail_length']
    tw,td=spec['terminal_section'];a=spec['appearance']
    positions=spec['positions']
    if spec['gender']!='female':raise ValueError('当前模型只支持排母')
    if not all(v>0 for v in (w,d,h,tail,tw,td)):raise ValueError('机械尺寸无效')
    mouth=a['mouth_size'];throat=a['throat_size'];depth=a['socket_depth'];lead=a['lead_in_depth']
    if not 0<throat<mouth<min(spec['pitch'],spec['row_spacing']) or not 0<lead<depth<h:raise ValueError('插孔外观参数超出本体')
    body=cq.Solid.makeBox(w,d,h,cq.Vector(-w/2,-d/2,0));cuts=[]
    for pin in positions:
        x,y=pin['x'],pin['y']
        if abs(x)+mouth/2>=w/2 or abs(y)+mouth/2>=d/2:raise ValueError('插孔超出本体')
        bore=cq.Solid.makeBox(throat,throat,depth+.01,cq.Vector(x-throat/2,y-throat/2,h-depth))
        entry=cq.Workplane('XY',origin=(x,y,h-lead)).rect(throat,throat).workplane(offset=lead+.01).rect(mouth,mouth).loft(combine=True).val()
        cuts.append(bore.fuse(entry).clean())
    body=body.cut(cq.Compound.makeCompound(cuts))
    shapes=[('BODY',body,[.10,.11,.13])]
    for p in positions:
        # The external tail is dimensioned. Hidden internal spring contacts are not inferred.
        shape=cq.Solid.makeBox(tw,td,tail,cq.Vector(p['x']-tw/2,p['y']-td/2,-tail))
        shapes.append(('TERMINAL_'+p['id'],shape,[.74,.65,.35]))
    assembly=cq.Assembly(name=spec['name'])
    for label,shape,color in shapes:
        if not shape.isValid() or len(shape.Solids())!=1:raise ValueError('模型实体无效: '+label)
        assembly.add(shape,name=label,color=cq.Color(*color))
    target=folder/(spec['name']+'.step');assembly.export(str(target),exportType='STEP')
    loaded=cq.importers.importStep(str(target)).val();solids=list(loaded.Solids())
    def box(s):
        b=s.BoundingBox();return [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]
    expected=[-w/2,-d/2,-tail,w/2,d/2,h]
    if not loaded.isValid() or len(solids)!=len(shapes) or max(abs(a-b) for a,b in zip(box(loaded),expected))>1e-5:raise ValueError('STEP回读实体或包络不符')
    remaining=solids[:];meshes=[]
    for name,shape,color in shapes:
        matches=[s for s in remaining if max(abs(a-b) for a,b in zip(box(shape),box(s)))<1e-5 and abs(shape.Volume()-s.Volume())<1e-5]
        if len(matches)!=1:raise ValueError('STEP逐端子回读不符: '+name)
        actual=matches[0];remaining.remove(actual)
        # Mesh the saved STEP readback, not a separately drawn approximation.
        vertices,triangles=actual.tessellate(.025,.25)
        meshes.append(dict(name=name,color=color,vertices=[[v.x,v.y,v.z] for v in vertices],triangles=triangles,opacity=1))
    (folder/'mesh.json').write_text(json.dumps(dict(bounds=expected,meshes=meshes,optical=None,initial_pitch=-.72)),encoding='utf8')
    report=dict(status='PASS',step=target.name,solids=len(shapes),bounds=expected,terminal_count=len(positions),origin='PCB mounting plane Z=0; tails below board',checks=['STEP topology','envelope','each terminal XY/section/length and volume','mesh from STEP readback'],approximation=spec['appearance']['notice'],limitation='Socket interior is an explicitly approximate cavity; internal contact springs and exact mouth dimensions are not specified. Target-board assembly acceptance pending.',file_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [target,folder/'mesh.json']})
    (folder/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS',target,len(shapes),'solids')

if __name__=='__main__':generate(json.loads(Path(sys.argv[1]).read_text(encoding='utf8')),sys.argv[2])
