"""Allegro polygon pads use SSM shapes plus PADs, not decorative copper."""
import csv,json,shutil,subprocess,time,hashlib
from pathlib import Path
import polygon_smd as poly
BASE=Path(__file__).parent

def pt(v):return '(list '+ ' '.join(f'{n:.5f}' for n in v)+')'
def points(v):return '(list '+' '.join(pt(q) for q in v+[v[0]])+')'

def run(folder,stem,code,executable):
    folder=Path(folder);marker=folder/(stem+'-complete.txt');marker.unlink(missing_ok=True)
    (folder/(stem+'.il')).write_text(code,encoding='ascii')
    script='\n'.join(['scriptmode +invisible +noinfo','skill \'(axlSetVariable "NOCONFIRM" t)\'',f'skill \'(load "{stem}.il")\'',f'skill \'(let ((o (outfile "{marker.name}"))) (fprintf o "DONE") (close o))\'','exit',''])
    (folder/(stem+'.scr')).write_text(script,encoding='ascii')
    with (folder/(stem+'.log')).open('wb') as log:
        p=subprocess.Popen([executable,'-s',stem+'.scr','-nograph'],cwd=folder,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline=time.monotonic()+600
            while p.poll() is None and not marker.is_file() and time.monotonic()<deadline:time.sleep(.4)
            if marker.is_file():
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:pass
            elif p.poll() is None:p.terminate();raise TimeoutError('Allegro timed out: '+str(folder/stem))
        finally:
            if p.poll() is None:p.terminate()
    if not marker.is_file() or '*Error*' in (folder/(stem+'.log')).read_text(errors='replace'):raise ValueError('Allegro step failed: '+str(folder/stem))

CLEAN='''(axlVisibleDesign t)
(axlClearSelSet)
(axlSetFindFilter ?enabled (list "noall" "alltypes") ?onButtons (list "noall" "alltypes"))
(axlAddSelectAll)
(foreach obj (axlGetSelSet) (unless (axlDeleteObject obj) (error "Cleanup failed")))
(axlClearSelSet)
'''

def read_code(file='readback.csv',design=True):
    return f'''(setq factor (axlMKSConvert 1.0 "design" "millimeters"))
(setq o (outfile "{file}"))
(fprintf o "record,id,layer,x,y,value\\n")
(fprintf o "U,%s,units,%.9f,%d,0\\n" (car (axlDBGetDesignUnits)) factor (cadr (axlDBGetDesignUnits)))
(foreach pin (axlDBGetDesign)->pins
 (foreach layer (list (strcat "ETCH/" (axlConductorTopLayer)) "PIN/SOLDERMASK_TOP" "PIN/PASTEMASK_TOP")
  (setq pad (axlDBGetPad pin layer "REGULAR"))
  (unless (equal pad->figureName "SHAPE") (error "Custom shape missing"))
  (setq pid pin->number)
  (unless (and pid (not (equal pid ""))) (setq pid (sprintf nil "MECH%.5f" (car pin->xy))))
  (fprintf o "P,%s,%s,%.8f,%.8f,0\\n" pid layer (times factor (car pin->xy)) (times factor (cadr pin->xy)))
  (setq polygons (axlPolyFromDB pin ?layer layer))
  (unless (equal (length polygons) 1) (error "Unexpected contour count"))
  (foreach polygon polygons
   (fprintf o "A,%s,%s,0,0,%.9f\\n" pid layer (times factor factor (abs polygon->area)))
   (foreach v polygon->vertices
    (fprintf o "V,%s,%s,%.8f,%.8f,%.8f\\n" pid layer (times factor (caar v)) (times factor (cadar v)) (cadr v))))))
(close o)
'''

def prepare(spec,output):
    poly.validate(spec);out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False);adir=out/'allegro';adir.mkdir()
    shutil.copy2(BASE/'templates/footprint/blank_symbol.dra',adir/'seed.dra')
    assets=poly.native_assets(spec);shapes={};padshapes={}
    for pad in spec['pads']:
        padshapes[pad['id']]={}
        x,y=pad['xy']
        for layer in ('copper','mask','paste'):
            # This first profile has one contour per layer; multi-window support
            # must be implemented explicitly before accepting >1 here.
            if len(pad[layer])!=1:raise ValueError('当前原生异形焊盘每层只接受一个闭合轮廓，尚未支持多窗口')
            contour=[[round(a-x,5),round(b-y,5)] for a,b in pad[layer][0]]
            key='qs_'+hashlib.sha256(json.dumps(contour).encode()).hexdigest()[:14]
            shapes[key]=contour;padshapes[pad['id']][layer]=key
    code=[]
    for name,contour in shapes.items():
        code += ['(unless (axlOpenDesign ?design "seed.dra" ?mode "wf" ?noMru t) (error "Seed open failed"))','(axlDBChangeDesignUnits "millimeters" 4)','(axlSetSymbolType "shape")',CLEAN,
            f'(setq outline (axlPathStart {points(contour)} 0.0))',
            '(unless (axlDBCreateShape outline t (strcat "ETCH/" (axlConductorTopLayer))) (error "Shape creation failed"))',
            f'(unless (axlCompileSymbol ?symbol "{name}" ?silent t ?silentOnOverwrite t) (error "SSM compile failed"))',
            f'(axlSaveDesign ?design "{name}.dra" ?noMru t ?noConfirm t)']
    (adir/'shape-code.txt').write_text('\n'.join(code),encoding='ascii')
    code=['(unless (axlOpenDesign ?design "seed.dra" ?mode "wf" ?noMru t) (error "Seed open failed"))','(axlSetSymbolType "package")','(axlDBChangeDesignUnits "millimeters" 4)',CLEAN,"(axlPurgePadstacks 'padstacks nil)",'(axlSetVariable "padpath" (list "."))','(axlSetVariable "psmpath" (list "."))',
        '(setq tp (axlGetParam "paramTextBlock:1"))','tp->width = 0.045','tp->height = 0.08','tp->photoWidth = 0.01','tp->charSpace = 0.008','(axlSetParam tp)']
    for p in spec['pads']:
        code.append('(setq pad_list (list')
        for layer,native in [('copper','(axlConductorTopLayer)'),('mask','"SOLDERMASK_TOP"'),('paste','"PASTEMASK_TOP"')]:
            coords=p[layer][0];w=max(a for a,b in coords)-min(a for a,b in coords);h=max(b for a,b in coords)-min(b for a,b in coords)
            code.append(f'(make_axlPadStackPad ?layer {native} ?type \'REGULAR ?figure "{padshapes[p["id"]][layer]}" ?figureSize {w+.0002:.5f}:{h+.0002:.5f})')
        code += ['))',f'(setq ps (axlDBCreatePadStack "{assets[p["id"]]}" nil pad_list t))','(unless ps (error "Padstack creation failed"))',f'(unless (axlDBCreatePin ps {pt(p["xy"])} '+('nil' if p.get('role')=='mounting' else f'(make_axlPinText ?number "{p["id"]}" ?offset (list 0.0 -0.0267) ?text (make_axlTextOrientation ?textBlock "1" ?rotation 0.0 ?justify "center"))')+') (error "Pin failed"))', '(unless (axlPadstackToDisk ps->name) (error "PAD export failed"))']
    w,h=spec['body'];e=spec['courtyard_excess']
    if spec.get('draw_body',True):code.append(f'(axlDBCreateLine {points([[-w/2,-h/2],[w/2,-h/2],[w/2,h/2],[-w/2,h/2]])} .03 "PACKAGE GEOMETRY/ASSEMBLY_TOP")')
    if spec.get('family')=='connector':
        coords=[xy for pad in spec['pads'] for xy in pad['copper'][0]]
        lo=[min(q[0] for q in coords)-e,min(q[1] for q in coords)-e]
        hi=[max(q[0] for q in coords)+e,max(q[1] for q in coords)+e]
    else:lo=[-w/2-e,-h/2-e];hi=[w/2+e,h/2+e]
    code += [f'(setq bound (car (axlDBCreateRectangle (list {pt(lo)} {pt(hi)}) t "PACKAGE GEOMETRY/PLACE_BOUND_TOP")))',f'(unless (axlDBAddProp (list bound) (list (list "PACKAGE_HEIGHT_MAX" "{spec["height_max"]}mm") (list "PACKAGE_HEIGHT_MIN" "{spec["height_min"]}mm"))) (error "Height failed"))',
        '(setq tp (axlGetParam "paramTextBlock:2"))','tp->width = .35','tp->height = .5','tp->photoWidth = .15','tp->charSpace = .04','(axlSetParam tp)',f'(axlDBCreateText "#REFDES" {pt([0,h/2+.7])} (make_axlTextOrientation ?textBlock "2" ?rotation 0.0 ?justify "center") "REF DES/SILKSCREEN_TOP")',
        f'(unless (equal (length (axlDBGetDesign)->pins) {len(spec["pads"])}) (error "Pin count mismatch"))',
        f'(unless (axlCompileSymbol ?symbol "{spec["name"]}" ?silent t ?silentOnOverwrite t) (error "PSM compile failed"))',f'(unless (axlSaveDesign ?design "{spec["name"]}.dra" ?noMru t ?noConfirm t) (error "DRA save failed"))']
    (adir/'package-code.txt').write_text('\n'.join(code),encoding='ascii')
    (out/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf8');poly.preview(spec,out)
    return out,adir,shapes

def check_contours(spec,file,unit='millimeters',offset=(0,0)):
    from shapely.geometry import Polygon
    rows=list(csv.DictReader(Path(file).open()));u=[r for r in rows if r['record']=='U']
    if len(u)!=1 or u[0]['id']!=unit or abs(float(u[0]['x'])-(1 if unit=='millimeters' else .0254))>1e-8:raise ValueError('异形焊盘数据库单位错误')
    expected={p['id']:p for p in spec['pads']};layers={'copper':None,'mask':'PIN/SOLDERMASK_TOP','paste':'PIN/PASTEMASK_TOP'}
    mechanical={}
    for row in rows:
        if row['record']=='P' and row['id'].startswith('MECH'):
            xy=[float(row['x'])-offset[0],float(row['y'])-offset[1]]
            found=[p['id'] for p in spec['pads'] if p.get('role')=='mounting' and max(abs(a-b) for a,b in zip(xy,p['xy']))<.00016]
            if len(found)!=1:raise ValueError('无编号机械焊盘坐标不匹配')
            mechanical[row['id']]=found[0]
    for row in rows:
        if row['id'] in mechanical:row['id']=mechanical[row['id']]
    pins=[r for r in rows if r['record']=='P']
    if len(pins)!=len(expected)*3 or len({(r['id'],r['layer']) for r in pins})!=len(expected)*3:raise ValueError('回读脚号或图层重复/缺失')
    for pin in pins:
        p=expected[pin['id']];layer=pin['layer'];key='copper' if layer.startswith('ETCH/') else 'mask' if 'SOLDER' in layer else 'paste'
        if max(abs(float(pin[k])-n) for k,n in zip(('x','y'),[a+b for a,b in zip(p['xy'],offset)]))>.00016:raise ValueError('连接点坐标错误')
        coords=[[float(r['x']),float(r['y'])] for r in rows if r['record']=='V' and r['id']==p['id'] and r['layer']==layer]
        actual=Polygon([[x-offset[0],y-offset[1]] for x,y in coords]);want=Polygon(p[key][0])
        if not actual.is_valid or actual.hausdorff_distance(want)>.0003 or actual.symmetric_difference(want).area>.00015:raise ValueError(f'异形轮廓不一致: {p["id"]}/{key}')
    return len(pins)

def build(spec,output,progress=lambda s:None,executable='D:/tools/pcb/bin/allegro.exe'):
    out,adir,shapes=prepare(spec,output)
    progress('生成独立 SSM 铜/阻焊/锡膏轮廓…');run(adir,'shapes',(adir/'shape-code.txt').read_text(),executable)
    progress('生成异形 PAD 与封装 DRA/PSM…');run(adir,'package',(adir/'package-code.txt').read_text(),executable)
    read=f'(axlOpenDesign ?design "{spec["name"]}.dra" ?mode "wf" ?noMru t)\n'+read_code()
    progress('独立重开 DRA 回读全部多边形…');run(adir,'read',read,executable);check_contours(spec,adir/'readback.csv')
    return finish(spec,out,progress,executable)


def finish(spec,out,progress,executable):
    out=Path(out);adir=out/'allegro';shapes={p.stem:None for p in adir.glob('*.ssm')}
    checks=[]
    for unit in ('millimeters','mils'):
        check=out/'checks'/('offset-'+unit);check.mkdir(parents=True,exist_ok=True)
        for p in adir.iterdir():
            if p.suffix.lower() in ('.ssm','.pad','.psm'):shutil.copy2(p,check/p.name)
        # Fresh board, not reopened DRA, verifies actual placement units.
        code=['(axlDBControl \'drcEnable nil)',f'(axlDBChangeDesignUnits "{unit}" 4)','(axlSetVariable "padpath" (list "."))','(axlSetVariable "psmpath" (list "."))','(setq anchor (quotient 25.4 (axlMKSConvert 1.0 "design" "millimeters")))',f'(unless (axlDBCreateSymbol (list "{spec["name"]}" "PACKAGE") (list anchor anchor)) (error "PSM import failed"))']
        # In board context pins belong to the placed package symbol.
        code.append(read_code().replace('(foreach pin (axlDBGetDesign)->pins','(foreach pin (car (axlDBGetDesign)->symbols)->pins'))
        progress('隔离 PCB 导入 '+unit+'，回读多边形…')
        if not (check/'import-complete.txt').is_file():run(check,'import','\n'.join(code),executable)
        check_contours(spec,check/'readback.csv',unit,(25.4,25.4));checks.append(unit)
    names={spec['name'].lower()+'.dra',spec['name'].lower()+'.psm'}|{n.lower()+'.pad' for n in poly.native_assets(spec).values()}|{n.lower()+'.ssm' for n in shapes}
    assets=[p for p in adir.iterdir() if p.name.lower() in names]
    report=dict(status='PASS',revision=1,kind='polygon_smd',pins=len(spec['pads']),layer_records=3*len(spec['pads']),units='millimeters',checks=['independent DRA polygon vertex readback','per-pin copper/mask/paste contour Hausdorff and area','physical mm/mil PSM import'],imports=checks,assets=[p.name for p in assets],file_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in assets},limitation='Manufacturer reference land/stencil examples; no target-project DRC or manufacturing acceptance')
    (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf8');return report

def verify(output):
    out=Path(output);r=json.loads((out/'verification.json').read_text(encoding='utf8'));s=json.loads((out/'spec.json').read_text(encoding='utf8'));poly.validate(s)
    if r.get('status')!='PASS' or r.get('kind')!='polygon_smd':raise ValueError('异形封装验证记录无效')
    for name,digest in r['file_hashes'].items():
        p=(out/'allegro'/name).resolve()
        if not p.is_relative_to((out/'allegro').resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('异形封装库文件被修改')
    if not (out/'allegro/read-complete.txt').is_file():raise ValueError('DRA 回读没有完成')
    check_contours(s,out/'allegro/readback.csv')
    for unit in ('millimeters','mils'):
        folder=out/'checks'/('offset-'+unit)
        if not (folder/'import-complete.txt').is_file():raise ValueError('PCB 导入回读没有完成')
        check_contours(s,folder/'readback.csv',unit,(25.4,25.4))
    return r
