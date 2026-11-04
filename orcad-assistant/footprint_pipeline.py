"""CSP footprint pipeline adapted from the user's 20261103 reference kit."""
import csv
import importlib.util
import json
import math
import re
import shutil
from pathlib import Path
from datetime import datetime
from templates.footprint.reference_generator import padstack_name
from templates.footprint.drawing import presentation

BASE=Path(__file__).parent
TEMPLATES=BASE/'templates'/'footprint'


def require_height(spec):
    value=spec.get('height_max')
    minimum=spec.get('height_min',0)
    if (not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0
        or not isinstance(minimum,(int,float)) or not math.isfinite(minimum) or not 0<=minimum<=value):
        raise ValueError('请填写有效的器件最大高度（mm），用于 Place Bound 高度检查')


def drawing_readback_il(parent='(axlDBGetDesign)', pins='((axlDBGetDesign)->pins)', offset=0):
    return '\n'.join([
        '(setq presentationFactor (axlMKSConvert 1.0 "design" "millimeters"))',
        f'(setq presentationOffset {offset:.6f})',
        '(setq drawingOut (outfile "drawing.csv"))',
        '(fprintf drawingOut "kind,id,layer,x0,y0,x1,y1,font_width,font_height,stroke,height_min,height_max\\n")',
        '(defun dumpPresentationText (tx kind ID)',
        ' (setq bb tx->bBox)',
        ' (setq tp (axlGetParam (strcat "paramTextBlock:" tx->textBlock)))',
        ' (fprintf drawingOut "%s,%s,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,,\\n" kind ID tx->layer',
        '  (difference (times presentationFactor (caar bb)) presentationOffset)',
        '  (difference (times presentationFactor (cadar bb)) presentationOffset)',
        '  (difference (times presentationFactor (caadr bb)) presentationOffset)',
        '  (difference (times presentationFactor (cadadr bb)) presentationOffset)',
        '  (times presentationFactor tp->width) (times presentationFactor tp->height) (times presentationFactor tp->photoWidth)))',
        f'(foreach pn {pins} (foreach tx (axlDBGetAttachedText pn) (dumpPresentationText tx "PIN" pn->number)))',
        f'(foreach tx (axlDBGetAttachedText {parent})',
        ' (dumpPresentationText tx (if (member tx->layer (list "REF DES/ASSEMBLY_TOP" "REF DES/SILKSCREEN_TOP")) "REF" "ANNOT") "text"))',
        '(foreach pb (axlDBGetShapes "PACKAGE GEOMETRY/PLACE_BOUND_TOP")',
        ' (setq bb pb->bBox)',
        ' (setq props (axlDBGetProperties pb))',
        ' (fprintf drawingOut "BOUND,place_bound,%s,%.6f,%.6f,%.6f,%.6f,0,0,0,%s,%s\\n" pb->layer',
        '  (difference (times presentationFactor (caar bb)) presentationOffset)',
        '  (difference (times presentationFactor (cadar bb)) presentationOffset)',
        '  (difference (times presentationFactor (caadr bb)) presentationOffset)',
        '  (difference (times presentationFactor (cadadr bb)) presentationOffset)',
        '  (cadr (assoc \'PACKAGE_HEIGHT_MIN props)) (cadr (assoc \'PACKAGE_HEIGHT_MAX props))))',
        '(close drawingOut)',
        '(axlVisibleDesign t)',
        '(axlClearSelSet)',
        '(axlSetFindFilter ?enabled (list "noall" "alltypes") ?onButtons (list "noall" "alltypes"))',
        '(axlAddSelectAll)',
        '(let ((o (outfile "paths.csv")))',
        ' (fprintf o "layer,x0,y0,x1,y1,stroke\\n")',
        ' (foreach obj (axlGetSelSet) (when (equal obj->objType "path")',
        '  (setq bb obj->bBox)',
        '  (foreach seg obj->segments (fprintf o "%s,%.6f,%.6f,%.6f,%.6f,%.6f\\n" obj->layer',
        '   (difference (times presentationFactor (caar bb)) presentationOffset)',
        '   (difference (times presentationFactor (cadar bb)) presentationOffset)',
        '   (difference (times presentationFactor (caadr bb)) presentationOffset)',
        '   (difference (times presentationFactor (cadadr bb)) presentationOffset)',
        '   (times presentationFactor seg->width))))) (close o))',
        '(let ((o (outfile "geometry-objects.txt"))) (foreach obj (axlGetSelSet) (fprintf o "%L\\n" obj->??)) (close o))',
        '(axlClearSelSet)'])


def verify_drawing(spec, directory, require_paths=True):
    require_height(spec)
    style=presentation(spec)
    records=list(csv.DictReader((Path(directory)/'drawing.csv').open()))
    expected={p[0]:p[1:] for p in geometry(spec)}
    pins=[r for r in records if r['kind']=='PIN']
    if len(pins)!=len(expected) or {r['id'] for r in pins}!=set(expected):
        raise ValueError('脚号文字回读不完整')
    for row in pins:
        values=[float(row[k]) for k in ('x0','y0','x1','y1','font_width','font_height','stroke')]
        if not all(math.isfinite(v) for v in values):raise ValueError('脚号文字尺寸无效')
        x0,y0,x1,y1,fw,fh,stroke=values;x,y=expected[row['id']]
        if (abs((x0+x1)/2-x)>.001 or abs((y0+y1)/2-y)>.001
            or max(math.hypot(a-x,b-y) for a in (x0,x1) for b in (y0,y1))>spec['pad_dia']/2+.001):
            raise ValueError('脚号文字未居中或超出焊盘：'+row['id'])
    refs=[r for r in records if r['kind']=='REF']
    if len(refs)!=2 or {r['layer'] for r in refs}!={'REF DES/ASSEMBLY_TOP','REF DES/SILKSCREEN_TOP'}:
        raise ValueError('REF 图层不完整')
    if any(abs(float(r['stroke'])-.15)>.00011 for r in refs):raise ValueError('REF 线宽不是 0.15 mm')
    annotations=[r for r in records if r['kind']=='ANNOT']
    same=all(abs(a-b)<.00005 for a,b in zip(spec['centers']['BGA'],spec['centers']['OPT']))
    if (len(annotations)!=3 or any(r['layer']!='PACKAGE GEOMETRY/ASSEMBLY_TOP'
        or abs(float(r['font_height'])-.18)>.00011 or float(r['stroke'])!=0 for r in annotations)):
        raise ValueError('中心标注不正确或残留了模板尺寸文字')
    bounds=[r for r in records if r['kind']=='BOUND']
    if len(bounds)!=1:raise ValueError('Place Bound 必须且只能有一个，发现缺失或残留大框')
    bound=bounds[0];w=style['place_bound']['width'];h=style['place_bound']['height']
    if any(abs(float(bound[k])-v)>.00011 for k,v in zip(('x0','y0','x1','y1'),(-w/2,-h/2,w/2,h/2))):
        raise ValueError('Place Bound 位置或尺寸错误，可能残留模板大框')
    def mm(value):
        m=re.fullmatch(r'\s*([\d.+-]+)\s*(MM|MILS?|IN(?:CH(?:ES)?)?)\s*',value,re.I)
        if not m:raise ValueError('Place Bound 高度属性缺失或单位不明确')
        return float(m[1])*({'MM':1,'MIL':.0254,'MILS':.0254}.get(m[2].upper(),25.4))
    if abs(mm(bound['height_max'])-spec['height_max'])>.00011 or abs(mm(bound['height_min'])-spec.get('height_min',0))>.00011:
        raise ValueError('Place Bound 器件高度不一致')
    if require_paths:
        paths=list(csv.DictReader((Path(directory)/'paths.csv').open()))
        if not paths:raise ValueError('缺少图形回读')
        leader_paths=[]
        for mark in style['annotations']:
            for (x0,y0),(x1,y1) in mark['segments']:
                wanted=(min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1))
                found=[r for r in paths if r['layer']=='PACKAGE GEOMETRY/ASSEMBLY_TOP'
                    and float(r['stroke'])==0 and all(abs(float(r[k])-v)<.00011
                        for k,v in zip(('x0','y0','x1','y1'),wanted))]
                if len(found)!=1:raise ValueError(mark['name']+' 引出线或箭头回读不一致')
                leader_paths.extend(found)
        for r in paths:
            if r['layer'] not in {'PACKAGE GEOMETRY/ASSEMBLY_TOP','PACKAGE GEOMETRY/SILKSCREEN_TOP'}:
                raise ValueError('封装残留意外图层图形：'+r['layer'])
            if r not in leader_paths and any(abs(float(r[k]))>limit+.00011 for k,limit in [('x0',w/2),('x1',w/2),('y0',h/2),('y1',h/2)]):
                raise ValueError('封装残留了范围以外的大框或尺寸线')
        crosses=[]
        centers=[(0,0,.12),(*spec['centers']['BGA'],.10)]
        if not same:centers.append((*spec['centers']['OPT'],.10))
        for x,y,radius in centers:
            for wanted in [(x-radius,y,x+radius,y),(x,y-radius,x,y+radius)]:
                found=[r for r in paths if r['layer']=='PACKAGE GEOMETRY/ASSEMBLY_TOP'
                    and all(abs(float(r[k])-v)<.00011 for k,v in zip(('x0','y0','x1','y1'),wanted))]
                if len(found)!=1 or float(found[0]['stroke'])!=0:raise ValueError('中心十字缺失或线宽不是 0')
                crosses.extend(found)
    return dict(status='PASS',revision=style['revision'],pin_texts=len(pins),pin_text_inside_pad=True,
                ref_stroke_mm=.15,center_stroke_mm=0,center_leaders=3,seed_geometry_cleared=True,
                place_bound_count=1,place_bound_mm=[w,h],height_max_mm=spec['height_max'])


def geometry(spec):
    """Explicit checks remain active even when Python runs with -O."""
    if len(spec['body'])!=2 or len(spec['pitch'])!=2 or any(len(spec['centers'][k])!=2 for k in ('BGA','OPT')):
        raise ValueError('本体、间距、中心必须为二维坐标')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',spec['name']):
        raise ValueError('封装名称须为 1～40 个英文字母、数字或下划线')
    numbers=[*spec['body'],*spec['pitch'],*spec['edge'].values(),spec['pad_dia'],spec['mask_margin'],spec['paste_dia'],spec['courtyard_excess'],spec['ball_dia']]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for k in ('BGA','OPT') for v in spec['centers'][k]):
        raise ValueError('中心坐标必须为有限数值')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in numbers):
        raise ValueError('尺寸必须为有限的非负数')
    if spec['name'].upper() in {'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(1,10)),*('LPT'+str(i) for i in range(1,10))}:
        raise ValueError('不能使用 Windows 保留名称')
    if min(*spec['body'],*spec['pitch'],spec['pad_dia'],spec['paste_dia'],spec['ball_dia'])<=0:
        raise ValueError('本体、间距、焊盘和锡膏尺寸必须大于 0')
    rows=spec['rows']; cols=spec['cols']; e=spec['edge']; w,h=spec['body']; px,py=spec['pitch']
    if not re.fullmatch('[A-Z]+',rows) or len(set(rows))!=len(rows) or not isinstance(cols,int) or not 1<=cols<=100:
        raise ValueError('行名或列数无效')
    grid={r+str(c) for r in rows for c in range(1,cols+1)}
    if not set(spec['missing'])<=grid or len(set(spec['missing']))!=len(spec['missing']):
        raise ValueError('缺球编号无效或重复')
    if abs(e['left_to_col1']+(cols-1)*px+e['right_to_colN']-w)>1e-6:
        raise ValueError('X 方向尺寸不闭合')
    if abs(e['top_to_rowA']+(len(rows)-1)*py+e['bottom_to_rowN']-h)>1e-6:
        raise ValueError('Y 方向尺寸不闭合')
    cx=(e['left_to_col1']-e['right_to_colN'])/2
    cy=(e['bottom_to_rowN']-e['top_to_rowA'])/2
    if any(abs(a-b)>1e-6 for a,b in zip((cx,cy),spec['centers']['BGA'])):
        raise ValueError('阵列中心与边距计算不一致')
    if max(spec['pad_dia']+2*spec['mask_margin'],spec['paste_dia'])>=min(px,py):
        raise ValueError('阻焊开口与相邻焊盘开口相交')
    pads=[(r+str(c+1),round(-w/2+e['left_to_col1']+c*px,4),round(h/2-e['top_to_rowA']-i*py,4))
          for i,r in enumerate(rows) for c in range(cols) if r+str(c+1) not in spec['missing']]
    if not pads:
        raise ValueError('不能生成空焊盘阵列')
    if spec.get('height_max') is not None:
        require_height(spec)
    return pads


def prepare(spec, output):
    expected=geometry(spec)
    require_height(spec)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    module=importlib.util.spec_from_file_location('footprint_reference',TEMPLATES/'reference_generator.py')
    generator=importlib.util.module_from_spec(module);module.loader.exec_module(generator)
    geo=generator.compute(spec)
    generator.gen_kicad(spec,geo,str(output))
    _,_,adir=generator.gen_allegro(spec,geo,str(output))
    adir=Path(adir)
    shutil.copy2(TEMPLATES/'blank_symbol.dra',adir/'_seed_blank.dra')
    name=spec['name']
    ilpath=adir/f'{name}_build.il'
    text=ilpath.read_text(encoding='utf-8')
    # Never accept a same-name inherited padstack as a successful creation.
    start=text.index('(when (null ps_name)')
    end=text.index(';; ---- 2)',start)
    text=text[:start]+'(unless ps_name (error "Native padstack creation failed"))\n\n'+text[end:]
    text=text.replace('(when (errset (axlDBCreatePin ps_name (list (cadr p) (caddr p)) myPin))',
                      '(when (axlDBCreatePin ps_name (list (cadr p) (caddr p)) myPin)')
    text+='\n(unless (equal (length (axlDBGetDesign)->pins) '+str(len(expected))+') (error "Pin count mismatch"))\n'
    text+='(unless (axlPadstackToDisk (ps_name->name)) (error "PAD export failed"))\n'
    ilpath.write_text(text,encoding='utf-8')
    script='\n'.join(['scriptmode +invisible +noinfo',
       'skill \'(axlSetVariable "NOCONFIRM" t)\'',
       'skill \'(unless (axlOpenDesign ?design "_seed_blank.dra" ?mode "wf" ?noMru t) (error "Seed open failed"))\'',
       'skill \'(axlSetSymbolType "package")\'',
       f'skill \'(load "{name}_build.il")\'',
       f'skill \'(unless (axlCompileSymbol ?symbol "{name}" ?silent t ?silentOnOverwrite t) (error "Compile failed"))\'',
       f'skill \'(unless (axlSaveDesign ?design "{name}.dra" ?noMru t ?noConfirm t) (error "Save failed"))\'',
       'skill \'(let ((out (outfile "build-complete.txt"))) (fprintf out "BUILD_COMPLETE\\n") (close out))\'',
       'exit',''])
    (adir/'build.scr').write_text(script,encoding='ascii')
    # Separate process opens saved DRA, reporting every pin and its actual geometry.
    read=['(let ((u (axlDBGetDesignUnits)) (o (outfile "units.csv")))',
      '(fprintf o "units,accuracy,mm_per_unit\\n")',
      '(fprintf o "%s,%d,%.8f\\n" (car u) (cadr u) (axlMKSConvert 1.0 "design" "millimeters"))',
      '(close o))',
      '(let ((out (outfile "readback.csv")) (pad nil) (bb nil) (factor (axlMKSConvert 1.0 "design" "millimeters")))',
      '(fprintf out "id,x,y,layer,shape,width,height,drill\\n")',
      '(setq ps (axlLoadPadstack "'+padstack_name(spec)+'"))',
      '(foreach pin ((axlDBGetDesign)->pins)',
      '(foreach layer (list (strcat "ETCH/" (axlConductorTopLayer)) "PIN/SOLDERMASK_TOP" "PIN/PASTEMASK_TOP" "ETCH/BOTTOM")',
      '(setq pad (axlDBGetPad pin layer "REGULAR"))',
      '(unless pad (error "Missing pad layer"))',
      '(setq bb (pad->bBox))',
      '(fprintf out "%s,%.6f,%.6f,%s,%s,%.6f,%.6f,%.6f\\n" (pin->number) (times factor (car (pin->xy))) (times factor (cadr (pin->xy))) layer (pad->figureName) (times factor (difference (caadr bb) (caar bb))) (times factor (difference (cadadr bb) (cadar bb))) (times factor (ps->drillDiameter)))',
      ')) (close out))']
    (adir/'read.il').write_text('\n'.join(read)+'\n'+drawing_readback_il(),encoding='ascii')
    (adir/'read.scr').write_text('\n'.join(['scriptmode +invisible +noinfo',
      'skill \'(axlSetVariable "NOCONFIRM" t)\'',
      f'skill \'(unless (axlOpenDesign ?design "{name}.dra" ?mode "wf" ?noMru t) (error "Readback open failed"))\'',
      'skill \'(load "read.il")\'','exit','']),encoding='ascii')
    (output/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'expected.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['id','x','y']);writer.writerows(expected)
    return adir


def verify(output, require_imports=True):
    output=Path(output);spec=json.loads((output/'spec.json').read_text(encoding='utf-8'))
    expected={p[0]:p[1:] for p in geometry(spec)}
    adir=output/'allegro'
    unit_file=adir/'units.csv'
    if not unit_file.is_file():
        raise ValueError('缺少数据库单位回读，旧结果需重新生成，不能判定物理尺寸正确')
    with unit_file.open() as stream:
        units=list(csv.DictReader(stream))
    if (len(units)!=1 or units[0]['units']!='millimeters' or int(units[0]['accuracy'])!=4
            or not math.isfinite(float(units[0]['mm_per_unit']))
            or abs(float(units[0]['mm_per_unit'])-1)>1e-8):
        raise ValueError('数据库单位或物理比例错误：要求毫米、4 位精度、1 数据库单位 = 1 mm')
    records=list(csv.DictReader((adir/'readback.csv').open()))
    grouped={}
    for r in records:
        key=(r['id'],r['layer'])
        if key in grouped: raise ValueError('重复引脚或重复层回读')
        if r['layer'] not in ('ETCH/TOP','PIN/SOLDERMASK_TOP','PIN/PASTEMASK_TOP','ETCH/BOTTOM'):
            raise ValueError('意外的焊盘层')
        if not all(math.isfinite(float(r[k])) for k in ('x','y','width','height','drill')):
            raise ValueError('回读尺寸不是有限数值')
        grouped[key]=r
        if r['id'] not in expected: raise ValueError('出现多余引脚')
        if any(abs(float(v)-a)>.00011 for v,a in zip((r['x'],r['y']),expected[r['id']])):raise ValueError('坐标不一致：'+r['id'])
        if float(r['drill'])!=0: raise ValueError('SMD 焊盘意外包含钻孔')
        size=0 if r['layer']=='ETCH/BOTTOM' else spec['pad_dia']+2*spec['mask_margin'] if 'SOLDERMASK' in r['layer'] else spec['paste_dia'] if 'PASTEMASK' in r['layer'] else spec['pad_dia']
        if r['shape']!=('CIRCLE' if size else 'NULL') or any(abs(float(r[k])-size)>.00011 for k in ('width','height')):
            raise ValueError('焊盘形状或尺寸不一致：'+str(key))
    if len(records)!=len(expected)*4 or {r['id'] for r in records}!=set(expected):raise ValueError('引脚或层数量不完整')
    # Independently compare KiCad's on-disk pad coordinates (+Y down).
    kmod=next(output.glob('*.kicad_mod')).read_text(encoding='utf-8')
    pads=re.findall(r'\(pad "?([A-Z]+\d+)"? smd \w+\s*\(at ([\d.\-]+) ([\d.\-]+)',kmod)
    if len(pads)!=len(expected) or len({p[0] for p in pads})!=len(expected):raise ValueError('KiCad 焊盘数量不完整')
    for pid,x,y in pads:
        if not all(math.isfinite(float(v)) for v in (x,y)) or pid not in expected or abs(float(x)-expected[pid][0])>.0006 or abs(float(y)+expected[pid][1])>.0006:raise ValueError('KiCad/Allegro 坐标不一致')
    name=spec['name']
    for file in (adir/f'{name}.dra',adir/f'{name.lower()}.psm'):
        if not file.exists() or not file.stat().st_size: raise ValueError('缺少 DRA/PSM 成品')
    report=dict(status='PASS',pins=len(expected),layer_records=len(records),units='millimeters',accuracy=4,mm_per_database_unit=1,
                checks=['数据库毫米单位及物理换算','独立 DRA 回读','逐脚毫米坐标','铜/阻焊/锡膏毫米直径','无钻孔及底层铜','KiCad Y 反转互校'],
                limitation='已在隔离 PCB 验证 PSM 导入；实际目标工程的旧封装实例需刷新，机械光学和制造工艺仍需确认。')
    report['drawing']=verify_drawing(spec,adir)
    if require_imports:
        report['pad_imports']=verify_import_checks(spec,output)
        report['checks'].append('独立磁盘 PAD 及含旧 BALL20 的 PCB 在 mm/mil 下导入验证')
        (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def prepare_import_checks(spec, output):
    """Load the exported PAD and PSM in fresh databases, including a stale BALL20."""
    output=Path(output)
    psname=padstack_name(spec)
    directories=[]
    for kind in ('pad','psm'):
        for unit in ('millimeters','mils'):
            directory=output/'checks'/(kind+'-'+unit)
            directory.mkdir(parents=True,exist_ok=False)
            shutil.copy2(TEMPLATES/'blank_symbol.dra',directory/'seed.dra')
            shutil.copy2(output/'allegro'/(psname.lower()+'.pad'),directory/(psname.lower()+'.pad'))
            if kind=='psm':
                shutil.copy2(output/'allegro'/(spec['name'].lower()+'.psm'),directory/(spec['name'].lower()+'.psm'))
            lines=['(axlDBControl \'drcEnable nil)']
            if kind=='pad':
                lines.append('(axlOpenDesign ?design "seed.dra" ?mode "wf" ?noMru t)')
            lines += [f'(axlDBChangeDesignUnits "{unit}" 4)',
                '(axlDBControl \'drcEnable nil)',
                '(axlSetVariable "padpath" (list "."))',
                '(axlSetVariable "psmpath" (list "."))',
                '(setq factor (axlMKSConvert 1.0 "design" "millimeters"))',
                f'(unless (equal (car (axlDBGetDesignUnits)) "{unit}") (error "Wrong check units"))',
                '(let ((o (outfile "units.csv"))) (fprintf o "units,mm_per_unit\\n")',
                '(fprintf o "%s,%.8f\\n" (car (axlDBGetDesignUnits)) factor) (close o))']
            if kind=='pad':
                lines += ['(axlPurgePadstacks \'padstacks nil)',
                    f'(setq checkItems (list (axlLoadPadstack "{psname}")))',
                    '(unless (car checkItems) (error "Disk PAD not loaded"))']
            else:
                # Reproduce the user's 0.2 mil failure in a disposable PCB.
                lines += ['(setq oldDiameter (quotient 0.00508 factor))',
                    '(setq oldPads (list (make_axlPadStackPad ?layer (axlConductorTopLayer) ?type \'REGULAR ?figure \'CIRCLE ?figureSize (list oldDiameter oldDiameter))))',
                    '(unless (axlDBCreatePadStack "BALL20" nil oldPads t) (error "Cache test setup failed"))',
                    '(setq anchor (quotient 25.4 factor))',
                    f'(setq placed (axlDBCreateSymbol (list "{spec["name"]}" "PACKAGE") (list anchor anchor)))',
                    '(unless placed (error "PSM placement failed"))',
                    '(setq checkItems ((car placed)->pins))']
            lines += ['(let ((out (outfile "readback.csv")) (pad nil) (bb nil))',
                '(fprintf out "id,x,y,layer,shape,width,height,drill\\n")',
                f'(setq ps (axlLoadPadstack "{psname}"))',
                '(foreach item checkItems',
                '(foreach layer (list "ETCH/TOP" "PIN/SOLDERMASK_TOP" "PIN/PASTEMASK_TOP" "ETCH/BOTTOM")',
                '(setq pad (axlDBGetPad item layer "REGULAR"))',
                '(unless pad (error "Check layer missing"))',
                '(setq bb (pad->bBox))']
            pid='"PAD"' if kind=='pad' else '(item->number)'
            x='0.0' if kind=='pad' else '(difference (times factor (car (item->xy))) 25.4)'
            y='0.0' if kind=='pad' else '(difference (times factor (cadr (item->xy))) 25.4)'
            lines += [f'(fprintf out "%s,%.6f,%.6f,%s,%s,%.6f,%.6f,%.6f\\n" {pid} {x} {y} layer (pad->figureName) (times factor (difference (caadr bb) (caar bb))) (times factor (difference (cadadr bb) (cadar bb))) (times factor (ps->drillDiameter)))',
                ')) (close out))']
            if kind=='psm':lines.append(drawing_readback_il('(car placed)','checkItems',25.4))
            lines += [
                f'(unless (axlSaveDesign ?design "check.{"dra" if kind=="pad" else "brd"}" ?noMru t ?noConfirm t) (error "Check database save failed"))',
                '(let ((o (outfile "complete.txt"))) (fprintf o "COMPLETE") (close o))']
            (directory/'validate.il').write_text('\n'.join(lines)+'\n',encoding='ascii')
            (directory/'validate.scr').write_text('\n'.join(['scriptmode +invisible +noinfo',
                'skill \'(axlSetVariable "NOCONFIRM" t)\'',
                'skill \'(load "validate.il")\'','exit','']),encoding='ascii')
            directories.append(directory)
    return directories


def verify_import_checks(spec, output):
    expected={p[0]:p[1:] for p in geometry(spec)}
    layers={'ETCH/TOP':spec['pad_dia'],'PIN/SOLDERMASK_TOP':spec['pad_dia']+2*spec['mask_margin'],
            'PIN/PASTEMASK_TOP':spec['paste_dia'],'ETCH/BOTTOM':0}
    results=[]
    for kind in ('pad','psm'):
        for unit,factor in (('millimeters',1),('mils',.0254)):
            directory=Path(output)/'checks'/(kind+'-'+unit)
            with (directory/'units.csv').open() as stream:units=list(csv.DictReader(stream))
            if len(units)!=1 or units[0]['units']!=unit or not math.isclose(float(units[0]['mm_per_unit']),factor,abs_tol=1e-9):
                raise ValueError('PAD/PSM 导入单位校验失败')
            with (directory/'readback.csv').open() as stream:records=list(csv.DictReader(stream))
            wanted={'PAD':(0,0)} if kind=='pad' else expected
            if {(r['id'],r['layer']) for r in records}!={(pid,layer) for pid in wanted for layer in layers} or len(records)!=len(wanted)*4:
                raise ValueError('独立 PAD/PSM 导入引脚或层不完整')
            for row in records:
                numbers=[float(row[k]) for k in ('x','y','width','height','drill')]
                if not all(math.isfinite(v) for v in numbers):raise ValueError('PAD/PSM 回读尺寸无效')
                x,y,w,h,drill=numbers;size=layers[row['layer']]
                if (any(abs(a-b)>.00011 for a,b in zip((x,y),wanted[row['id']]))
                    or any(abs(v-size)>.00011 for v in (w,h)) or drill!=0
                    or row['shape']!=('CIRCLE' if size else 'NULL')):
                    raise ValueError(f'{kind}/{unit} 导入后的物理焊盘尺寸或坐标错误：'+row['id'])
            if not (directory/'complete.txt').is_file():raise ValueError('PAD/PSM 验证没有完整结束')
            if kind=='psm':verify_drawing(spec,directory,require_paths=False)
            results.append(dict(kind=kind,units=unit,records=len(records),status='PASS'))
    return dict(status='PASS',padstack=padstack_name(spec),checks=results,
                legacy_collision='0.2 mil BALL20 exists in both disposable PCB tests; new PSM retains correct pad diameter')


def build(spec, output, progress, executable='D:/tools/pcb/bin/allegro.exe'):
    import subprocess
    import time
    if not Path(executable).is_file():
        raise ValueError('找不到 Allegro，请在环境设置中配置 allegro 路径')
    adir = prepare(spec, output)
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    def run(script, marker, directory=adir):
        progress('PCB：'+('生成 DRA / PSM / PAD' if script=='build.scr' else
                         '验证磁盘焊盘与 PCB 导入：'+directory.name if script=='validate.scr' else '独立打开 DRA 逐脚回读'))
        with (directory/(script+'.log')).open('wb') as log:
            process = subprocess.Popen([executable, '-s', script, '-nograph'], cwd=directory,
                                       stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic()+120
            while time.monotonic()<deadline:
                if (directory/marker).exists():
                    process.wait(timeout=15)
                    return
                if process.poll() not in (None, 0):
                    raise RuntimeError('Allegro 执行失败，请查看 '+str(directory))
                time.sleep(.5)
            # Never kill unrelated user editors. Preserve diagnostics on timeout.
            if process.poll() is None: process.terminate()
            raise TimeoutError('Allegro 超时，未得到完成标记；诊断目录：'+str(directory))
    run('build.scr','build-complete.txt')
    # Marker is written after the complete CSV is closed, not when the file appears.
    readscript=adir/'read.scr'
    text=readscript.read_text(encoding='ascii').replace('\nexit', '\nskill \'(let ((o (outfile "read-complete.txt"))) (fprintf o "DONE") (close o))\'\nexit')
    readscript.write_text(text,encoding='ascii')
    run('read.scr','read-complete.txt')
    progress('正在比较铜、阻焊、锡膏、编号与坐标…')
    verify(output,require_imports=False)
    for directory in prepare_import_checks(spec,output):
        run('validate.scr','complete.txt',directory)
    return verify(output)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--spec',default=str(TEMPLATES/'gc4693.json'));parser.add_argument('--output');parser.add_argument('--verify')
    args=parser.parse_args()
    if args.verify: print(json.dumps(verify(args.verify),ensure_ascii=False,indent=2))
    else:
        spec=json.loads(Path(args.spec).read_text(encoding='utf-8'))
        output=args.output or str(BASE/'footprint-validation'/('GC4693-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
        print(prepare(spec,output))
