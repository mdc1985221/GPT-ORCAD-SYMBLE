"""Reviewed two-terminal SMD recipes; manufacturer dimensions and process presets stay separate."""
import copy,hashlib,json,math
from pathlib import Path
BASE=Path(__file__).parent

def catalog():
    return json.loads((BASE/'templates/standard_smd/catalog.json').read_text(encoding='utf8'))['parts']

def download_sources(folder,progress=print):
    """Only a previously reviewed PDF revision can drive these recipes."""
    import urllib.request
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    sources={r['source']['file']:r['source'] for r in catalog()}
    for filename,source in sources.items():
        path=folder/filename
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']:continue
        progress('下载原厂资料：'+filename)
        with urllib.request.urlopen(source['url'],timeout=40) as response:raw=response.read(60*1024*1024+1)
        if not raw.startswith(b'%PDF-') or len(raw)>60*1024*1024 or hashlib.sha256(raw).hexdigest()!=source['sha256']:
            raise ValueError('原厂资料版本发生变化或下载异常，须重新核对尺寸后更新规则：'+filename)
        tmp=path.with_suffix('.pdf.downloading');tmp.write_bytes(raw);tmp.replace(path)
    return folder

def rect(x,y,w,h):
    return [[round(x-w/2,6),round(y-h/2,6)],[round(x+w/2,6),round(y-h/2,6)],
            [round(x+w/2,6),round(y+h/2,6)],[round(x-w/2,6),round(y+h/2,6)]]

def specification(recipe,source):
    from footprint_naming import validate
    source=Path(source).resolve()
    if hashlib.sha256(source.read_bytes()).hexdigest()!=recipe['source']['sha256']:raise ValueError('规格书版本与核对过的贴片规则不一致')
    name=recipe['device']+'_RF';validate(name)
    pw,ph=recipe['pad'];gap=recipe['gap'];offset=(gap+pw)/2
    if min(pw,ph,gap,recipe['model_height'])<=0:raise ValueError('贴片尺寸无效')
    pads=[]
    for pid,x in [('1',-offset),('2',offset)]:
        pads.append(dict(id=pid,xy=[x,0],copper=[rect(x,0,pw,ph)],mask=[rect(x,0,pw+.10,ph+.10)],paste=[rect(x,0,pw-.06,ph-.06)],mask_type='NSMD'))
    lines=[]
    if gap>.4:
        y=max(recipe['body'][1],ph+.1)/2+.2
        lines=[[[(-gap/2+.15),y],[(gap/2-.15),y]],[[(-gap/2+.15),-y],[(gap/2-.15),-y]]]
    if recipe['category']=='diode':
        x=-(gap+2*pw)/2-.25;lines.append([[x,-ph/2-.15],[x,ph/2+.15]])
    notes=['铜焊盘尺寸来自对应原厂推荐图；矩形铜角、阻焊每侧+0.05mm、锡膏每边内缩0.03mm、丝印及Courtyard为工具工艺预设，尚待板厂与装配验收。',recipe['notes']]
    return dict(kind='polygon_smd',family='standard_smd',revision=1,name=name,label=recipe['device'],
        manufacturer=recipe['manufacturer'],body=recipe['body'],body_max=recipe['body_max'],
        height_min=recipe['height_min'],height_nominal=recipe['model_height'],height_max=recipe['height_max'],
        height_selection='nominal' if recipe['category']=='resistor' else 'maximum_envelope' if recipe['category'] in ('capacitor','inductor') else 'documented_typ_or_range_midpoint',
        courtyard_excess=.25,pads=pads,silkscreen_segments=lines,
        sources=[dict(page=recipe['source']['mechanical_page'],field='mechanical',text=recipe['notes']),dict(page=recipe['source']['land_page'],field='recommended copper',text=f'pad {pw}x{ph}mm; inner gap {gap}mm; {recipe["source"]["url"]}')],
        notes=notes,needs=['板厂焊接工艺与目标工程验收；同尺寸不同系列须重新核对规格书'],
        source_pdf=str(source),source_pdf_sha256=recipe['source']['sha256'],standard_recipe=copy.deepcopy(recipe))

def graphics(category):
    if category=='resistor':
        return [[0,50,40,50],[40,30,80,30],[80,30,80,70],[80,70,40,70],[40,70,40,30],[80,50,120,50]]
    if category=='capacitor':return [[0,50,40,50],[40,20,40,80],[80,20,80,80],[80,50,120,50]]
    if category=='diode':return [[0,50,45,50],[45,25,45,75],[45,50,85,25],[85,25,85,75],[85,75,45,50],[85,50,120,50]]
    lines=[[0,50,30,50],[90,50,120,50]]
    for start in (30,45,60,75):
        points=[[round(start+7.5-7.5*math.cos(i*math.pi/8),3),round(50-15*math.sin(i*math.pi/8),3)] for i in range(9)]
        # Capture drawing units are integral MIL; electrical hot spots use10MIL.
        points=[[round(x),round(y)] for x,y in points]
        lines.extend([*a,*b] for a,b in zip(points,points[1:]))
    return lines

def project(recipe,spec):
    import assistant_core as c
    p=c.new_project();p.update(device=recipe['device'],footprint=spec['name'],manufacturer=recipe['manufacturer'],description=recipe['category']+' / '+recipe['notes'],profile='generic',expected_count=2,library_category=recipe['category'],sources=[dict(path=spec['source_pdf'],sha256=spec['source_pdf_sha256'])])
    p['pins']=[dict(id=str(i),name=('K' if i==1 else 'A') if recipe['category']=='diode' else str(i),type='PASS',side='LEFT' if i==1 else 'RIGHT',group='',part='A',confidence=1.,conflicts=[]) for i in (1,2)]
    p['symbol_layout']=dict(frame=[120,100],pins={'1':dict(side='LEFT',offset=50),'2':dict(side='RIGHT',offset=50)})
    p['symbol_graphics']=dict(frame_visible=False,segments=graphics(recipe['category']),type=recipe['category'],designator={'resistor':'R','capacitor':'C','inductor':'L','diode':'D'}[recipe['category']])
    if recipe['category'] in ('resistor','capacitor'):
        import re
        size=re.match(r'[RC](\d{4})_',recipe['device'])
        p['symbol_pin_length']=10
        p['symbol_graphics'].update(pin_names_visible=False,pin_length_style='short')
        if size:p['symbol_graphics']['texts']=[dict(text=size[1],x=60,y=50,height=12)]
    p['pcb']=dict(spec=spec,confirmed=False,needs=spec['needs'],notes=spec['notes'])
    p['reviewed']=[i['key'] for i in c.issues(p) if not i['blocking']]
    return p

def plan(spec,options):
    import polygon_smd
    polygon_smd.validate(spec)
    if options.get('confirmed') is not True:raise ValueError('请确认原厂尺寸及外观近似')
    r=spec['standard_recipe'];h=options.get('total_height',r['model_height'])
    if not isinstance(h,(int,float)) or not math.isfinite(h) or not spec['height_min']<=h<=spec['height_max'] or h<=0:raise ValueError('3D高度超出该系列尺寸范围')
    return dict(kind='standard_smd',revision=2,name=spec['name'],body=spec['body'],total_height=h,recipe=r,pads=[[p['id'],*p['xy']] for p in spec['pads']],optical=None,dimension_source=r['source'],approximation=r['notes'],appearance_presets='Rounded chip terminations, ceramic/alumina and coating colors, mould edge radius and diode lead bend radii are appearance approximations, not manufacturer dimensions. No invented value or batch marking.')

def generate(folder):
    import cadquery as cq
    folder=Path(folder);p=json.loads((folder/'input.json').read_text(encoding='utf8'));r=p['recipe'];l,w=p['body'];h=p['total_height'];t=r['terminal'];shapes=[]
    def box(x0,y0,z0,x1,y1,z1):return cq.Solid.makeBox(x1-x0,y1-y0,z1-z0,cq.Vector(x0,y0,z0))
    def rounded(shape,radius):return cq.Workplane(obj=shape).edges().fillet(radius).val()
    def put(name,shape,color):shapes.append((name,shape.clean(),color))
    metal=[.74,.76,.79]
    if r['style']=='diode':
        c=t['thickness'];span=t['overall'];b=t['width'];foot=t['foot_length'];stand=t['standoff']
        body=rounded(box(-l/2,-w/2,stand,l/2,w/2,h),min(.08,w*.06,(h-stand)*.06))
        for i,side in [(1,-1),(2,1)]:
            # Piecewise lead follows the shown foot/riser; bend radii are approximate.
            neck0=min(l/2-.03,span/2-foot/2);neck1=max(l/2+.03,span/2-foot/2)
            lead=box(span/2-foot,-b/2,0,span/2,b/2,c).fuse(box(neck0,-b/2,c/2,neck1,b/2,max(c*1.5,stand+c)))
            if side<0:lead=lead.mirror('YZ')
            body=body.cut(lead);put('TERMINAL_'+str(i),lead,metal)
        depth=min(.006,h*.02);stripe=box(-l/2+l*.12,-w/2,h-depth,-l/2+l*.20,w/2,h)
        stripe=stripe.intersect(body)
        body=body.cut(stripe);put('MOLDED_BODY_APPROX',body,[.12,.13,.15]);put('CATHODE_BAND_APPROX',stripe,[.73,.73,.70])
    elif r['style']=='drum':
        thick=t['thickness'];term=t['bottom_length'];tw=t['width'];flange=h*.18
        body=box(-l/2,-w/2,thick,l/2,w/2,flange)
        top=box(-l/2,-w/2,h-flange,l/2,w/2,h)
        core=box(-l*.35,-w*.35,flange,l*.35,w*.35,h-flange)
        winding=box(-l*.44,-w*.44,flange,l*.44,w*.44,h-flange).cut(core)
        put('FERRITE_LOWER_APPROX',body,[.16,.16,.17]);put('FERRITE_UPPER_APPROX',top,[.18,.18,.20]);put('CORE_APPROX',core,[.12,.12,.13]);put('WINDING_COATING_APPROX',winding,[.10,.095,.085])
        put('TERMINAL_1',box(-l/2,-tw/2,0,-l/2+term,tw/2,thick),metal);put('TERMINAL_2',box(l/2-term,-tw/2,0,l/2,tw/2,thick),metal)
    else:
        thick=t['thickness'];bottom=t['bottom_length'];top=t['top_length']
        edge=min(.06,w*.06,h*.10)
        body=rounded(box(-l/2,-w/2,0,l/2,w/2,h),edge)
        # Carry the end plating around the rounded corners as one connected
        # solid; the un-dimensioned wrap depth is an appearance preset.
        cap=box(l/2-bottom,-w/2,0,l/2,w/2,thick).fuse(box(l/2-top,-w/2,h-thick,l/2,w/2,h)).fuse(box(l/2-edge-thick,-w/2,0,l/2,w/2,h)).clean()
        for i,side in [(1,-1),(2,1)]:
            terminal=(cap if side>0 else cap.mirror('YZ')).intersect(body);body=body.cut(terminal);put('TERMINAL_'+str(i),terminal,metal)
        if r['category']=='resistor':
            film=box(-l/2+top,-w/2,h-.004,l/2-top,w/2,h).intersect(body);body=body.cut(film);put('RESISTIVE_COATING_APPROX',film,[.10,.12,.14])
        put('CERAMIC_BODY_APPROX' if r['category']=='capacitor' else 'ALUMINA_BODY_APPROX',body,[.70,.53,.32] if r['category']=='capacitor' else [.81,.78,.66])
    for name,shape,_ in shapes:
        if not shape.isValid() or len(shape.Solids())!=1:raise ValueError('Invalid standard SMD solid '+name)
    assembly=cq.Assembly(name=p['name'])
    for name,shape,color in shapes:assembly.add(shape,name=name,color=cq.Color(*color))
    step=folder/(p['name']+'.step');assembly.export(str(step),exportType='STEP');loaded=cq.importers.importStep(str(step)).val();solids=list(loaded.Solids())
    def bounds(s):
        b=s.BoundingBox();return [b.xmin,b.ymin,b.zmin,b.xmax,b.ymax,b.zmax]
    span=t.get('overall',l);expected=[-span/2,-w/2,0,span/2,w/2,h];actual=bounds(loaded)
    if not loaded.isValid() or len(solids)!=len(shapes) or max(abs(a-b) for a,b in zip(actual,expected))>1e-5:raise ValueError('Standard SMD STEP envelope/topology mismatch')
    rest=solids[:];meshes=[]
    for name,shape,color in shapes:
        found=[s for s in rest if max(abs(a-b) for a,b in zip(bounds(s),bounds(shape)))<1e-5 and abs(s.Volume()-shape.Volume())<1e-6]
        if len(found)!=1:raise ValueError('STEP solid mismatch '+name)
        s=found[0];rest.remove(s);v,tri=s.tessellate(.015,.2);meshes.append(dict(name=name,color=color,opacity=1,vertices=[[q.x,q.y,q.z] for q in v],triangles=tri))
    (folder/'mesh.json').write_text(json.dumps(dict(kind='standard_smd',bounds=actual,meshes=meshes,optical=None,initial_pitch=.72,appearance_notice=r['notes']+' '+p['appearance_presets'])),encoding='utf8')
    report=dict(status='PASS',revision=1,kind='standard_smd',step=step.name,plan=p,units='mm',bounds=actual,solids=len(solids),checks=['saved STEP reimport topology and solid count','mechanical envelope and board contact Z=0','each solid bounds and volume','preview meshes tessellated from STEP reimport'],limitation=r['notes']+' '+p['appearance_presets'],file_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [step,folder/'mesh.json']})
    (folder/'model3d.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
