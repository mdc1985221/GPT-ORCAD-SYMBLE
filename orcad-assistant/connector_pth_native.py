"""Isolated native PTH connector candidate builder with independent readback."""
import csv,json,shutil,hashlib,sys
from pathlib import Path
import polygon_native as native

def read_code(board=False):
    pins='(car (axlDBGetDesign)->symbols)->pins' if board else '(axlDBGetDesign)->pins'
    return '''(setq factor (axlMKSConvert 1.0 "design" "millimeters"))
(setq o (outfile "readback.csv"))
(fprintf o "id,x,y,layer,shape,w,h,drill,plating\\n")
'''+f'(foreach pin {pins}\n'+'''
 (setq ps (axlLoadPadstack pin->name))
 (unless ps (error "Padstack read failed"))
 (foreach layer (list (strcat "ETCH/" (axlConductorTopLayer)) "ETCH/BOTTOM" "PIN/SOLDERMASK_TOP" "PIN/SOLDERMASK_BOTTOM")
  (setq pad (axlDBGetPad pin layer "REGULAR"))
  (unless pad (error "PTH layer missing"))
  (setq bb pad->bBox)
  (fprintf o "%s,%.8f,%.8f,%s,%s,%.8f,%.8f,%.8f,%s\\n" pin->number (times factor (car pin->xy)) (times factor (cadr pin->xy)) layer pad->figureName (times factor (difference (caadr bb) (caar bb))) (times factor (difference (cadadr bb) (cadar bb))) (times factor ps->drillDiameter) ps->plating))
 (foreach layer (list "PIN/PASTEMASK_TOP" "PIN/PASTEMASK_BOTTOM")
  (setq paste (axlDBGetPad pin layer "REGULAR"))
  (when (and paste (not (equal paste->figureName "NULL"))) (error "Unexpected PTH paste"))))
(close o)
'''

def check(s,file,offset=0):
    rows=list(csv.DictReader(Path(file).open()));pos={p['id']:p for p in s['positions']}
    if len(rows)!=4*len(pos) or len({(r['id'],r['layer']) for r in rows})!=len(rows):raise ValueError('通孔回读脚号/图层缺失')
    for r in rows:
        p=pos[r['id']];size=s['mask_diameter'] if 'SOLDERMASK' in r['layer'] else s['pad']
        wanted=[p['x']+offset,p['y']+offset,size,size,s['drill']]
        if max(abs(float(r[k])-v) for k,v in zip(['x','y','w','h','drill'],wanted))>.00015:raise ValueError('通孔坐标/铜/阻焊/孔径回读不符')
        if r['plating']!='PLATED' or r['shape']!=('SQUARE' if r['id']=='1' else 'CIRCLE'):raise ValueError('通孔电镀/1脚形状不符')
    return len(rows)

def build(s,out,exe='D:/tools/pcb/bin/allegro.exe'):
    out=Path(out).resolve();adir=out/'allegro';adir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(native.BASE/'templates/footprint/blank_symbol.dra',adir/'seed.dra')
    code=['(axlOpenDesign ?design "seed.dra" ?mode "wf" ?noMru t)','(axlDBChangeDesignUnits "millimeters" 4)','(axlSetSymbolType "package")',native.CLEAN,"(axlPurgePadstacks 'padstacks nil)",'(axlSetVariable "padpath" (list "."))','(axlSetVariable "psmpath" (list "."))','(setq tp (axlGetParam "paramTextBlock:1"))','tp->width = .4','tp->height = .6','tp->photoWidth = .08','(axlSetParam tp)']
    for shape in ('SQUARE','CIRCLE'):
        name='DIP_H102_C180_'+('S' if shape=='SQUARE' else 'R')
        code.append('(setq pads (list')
        for layer in ('TOP','DEFAULT INTERNAL','BOTTOM','SOLDERMASK_TOP','SOLDERMASK_BOTTOM'):
            size=s['mask_diameter'] if layer.startswith('SOLDER') else s['pad']
            code.append(f'(make_axlPadStackPad ?layer "{layer}" ?type \'REGULAR ?figure "{shape}" ?figureSize {size}:{size})')
        code+=['))',f'(setq ps (axlDBCreatePadStack "{name}" (make_axlPadStackDrill ?drillDiameter {s["drill"]} ?figure \'CIRCLE ?figureSize {s["drill"]}:{s["drill"]} ?plating \'PLATED) pads t))','(unless ps (error "PTH creation failed"))']
        for p in s['positions']:
            if (p['id']=='1')!=(shape=='SQUARE'):continue
            code.append(f'(unless (axlDBCreatePin ps (list {p["x"]} {p["y"]}) (make_axlPinText ?number "{p["id"]}" ?offset (list 0.0 -.2) ?text (make_axlTextOrientation ?textBlock "1" ?rotation 0.0 ?justify "center"))) (error "Pin failed"))')
        code.append('(unless (axlPadstackToDisk ps->name) (error "PAD export failed"))')
    w,d=s['body'];pts=native.points([[-w/2,-d/2],[w/2,-d/2],[w/2,d/2],[-w/2,d/2]])
    code+=[f'(axlDBCreateLine {pts} .10 "PACKAGE GEOMETRY/ASSEMBLY_TOP")',f'(axlDBCreateLine {pts} .15 "PACKAGE GEOMETRY/SILKSCREEN_TOP")',f'(setq bound (car (axlDBCreateRectangle (list (list {-w/2} {-d/2}) (list {w/2} {d/2})) t "PACKAGE GEOMETRY/PLACE_BOUND_TOP")))',f'(axlDBAddProp (list bound) (list (list "PACKAGE_HEIGHT_MAX" "{s["height_max"]}mm") (list "PACKAGE_HEIGHT_MIN" "{s["height_min"]}mm")))','(setq tp (axlGetParam "paramTextBlock:2"))','tp->width = .6','tp->height = 1.0','tp->photoWidth = .15','(axlSetParam tp)','(axlDBCreateText "#REFDES" (list 0.0 3.6) (make_axlTextOrientation ?textBlock "2" ?justify "center" ?rotation 0.0) "REF DES/SILKSCREEN_TOP")',f'(unless (equal (length (axlDBGetDesign)->pins) {len(s["positions"])}) (error "Pin count mismatch"))',f'(unless (axlCompileSymbol ?symbol "{s["name"]}" ?silent t ?silentOnOverwrite t) (error "Compile failed"))',f'(unless (axlSaveDesign ?design "{s["name"]}.dra" ?noMru t ?noConfirm t) (error "Save failed"))']
    # A long connector exceeds the small sensor seed drawing's extents.
    code.insert(2,'(unless (axlDBChangeDesignExtents (list (list -100.0 -100.0) (list 100.0 100.0))) (error "Drawing extents failed"))')
    # A long connector exceeds the small sensor seed drawing's extents.
    code.insert(2,'(unless (axlDBChangeDesignExtents (list (list -100.0 -100.0) (list 100.0 100.0))) (error "Drawing extents failed"))')
    print('native build',flush=True);native.run(adir,'build','\n'.join(code),exe)
    if not (adir/(s['name']+'.psm')).is_file():raise ValueError('原生封装未完成，不能用脚本结束标志代替文件验证')
    if not (adir/(s['name']+'.psm')).is_file():raise ValueError('原生封装未完成，不能用脚本结束标志代替文件验证')
    native.run(adir,'read',f'(axlOpenDesign ?design "{s["name"]}.dra" ?mode "wf" ?noMru t)\n'+read_code(),exe);check(s,adir/'readback.csv')
    for unit in ('millimeters','mils'):
        p=out/'checks'/unit;p.mkdir(parents=True,exist_ok=True)
        for f in adir.iterdir():
            if f.suffix.lower() in ('.pad','.psm'):shutil.copy2(f,p/f.name)
        c=f'''(axlDBControl 'drcEnable nil)
(axlDBChangeDesignUnits "{unit}" 4)
(setq ext (quotient 200.0 (axlMKSConvert 1.0 "design" "millimeters")))
(axlDBChangeDesignExtents (list (list (minus ext) (minus ext)) (list ext ext)))
(axlSetVariable "padpath" (list "."))
(axlSetVariable "psmpath" (list "."))
(setq v (quotient 25.4 (axlMKSConvert 1.0 "design" "millimeters")))
(unless (axlDBCreateSymbol (list "{s['name']}" "PACKAGE") (list v v)) (error "PSM import failed"))
'''+read_code(True)
        print('import',unit,flush=True);native.run(p,'import',c,exe);check(s,p/'readback.csv',25.4)
    files=[p for p in adir.iterdir() if p.suffix.lower() in ('.pad','.psm') or p.name==s['name']+'.dra']
    r=dict(status='PASS',physical_pins=len(s['positions']),checks=['DRA independent per-pin copper/mask/hole/plating/no-paste readback','millimeter and mil PSM placement'],file_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files},limitation='Candidate copper/mask process presets and user numbering; target board DRC/assembly pending')
    (out/'verification.json').write_text(json.dumps(r,indent=2),encoding='utf8');print('PCB PASS',flush=True)

if __name__=='__main__':build(json.loads(Path(sys.argv[1]).read_text(encoding='utf8')),sys.argv[2])
