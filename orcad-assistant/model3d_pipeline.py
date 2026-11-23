"""Optional CSP/BGA mechanical approximation; Z=0 is the PCB contact plane."""
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
import footprint_pipeline as fp
import model3d_details

BASE=Path(__file__).resolve().parent


def plan(spec, options):
    if spec.get('kind')=='polygon_smd':
        from polygon_model3d import plan as polygon_plan
        return polygon_plan(spec,options)
    pads=fp.geometry(spec)
    if options.get('confirmed') is not True:
        raise ValueError('请先确认 3D 总高度、焊球高度和简化结构')
    total=options.get('total_height');stand=options.get('ball_height')
    if not all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) for v in (total,stand)):
        raise ValueError('请填写有限的 3D 总高度和焊球高度（mm）')
    if not 0<stand<=spec['ball_dia'] or not stand<total<=100:
        raise ValueError('焊球高度必须大于 0 且不超过球径，总高度必须大于焊球高度（上限 100 mm）')
    if len(pads)>1000:raise ValueError('简化 3D 当前最多支持 1000 个焊球')
    if spec['ball_dia']>=min(spec['pitch']):raise ValueError('焊球直径不能达到相邻球间距')
    w,h=spec['body'];radius=spec['ball_dia']/2
    if any(abs(x)+radius>w/2+1e-4 or abs(y)+radius>h/2+1e-4 for _,x,y in pads):
        raise ValueError('焊球超出本体范围，请核对机械尺寸')
    optical=None
    if spec.get('sensor_array'):
        size=spec['sensor_array'];glass=spec.get('glass_thickness')
        if (len(size)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in size)
            or size[0]>=w or size[1]>=h or not isinstance(glass,(int,float)) or not 0<glass<total-stand):
            raise ValueError('感光区域或玻璃厚度无效，玻璃须小于本体厚度')
        optical=dict(size=size,center=spec['centers']['OPT'],glass_thickness=glass,
                     die_size=spec.get('die_size',size),appearance_depth=.002,
                     top_to_wafer=spec.get('top_to_wafer',glass))
        dw,dh=optical['die_size'];cx,cy=optical['center']
        wafer_depth=optical['top_to_wafer']
        if not isinstance(wafer_depth,(int,float)) or isinstance(wafer_depth,bool) or not math.isfinite(wafer_depth):
            raise ValueError('玻璃顶面到晶圆的距离必须为有限毫米值')
        if (dw<size[0] or dh<size[1] or abs(cx)+dw/2>w/2 or abs(cy)+dh/2>h/2
            or not glass<=optical['top_to_wafer']<total-stand-optical['appearance_depth']):
            raise ValueError('芯片表面、感光区域或玻璃层叠超出本体范围')
    appearance=model3d_details.validate(spec.get('appearance_profile'))
    result=dict(revision=1,name=spec['name'],units='mm',body=[w,h],total_height=total,optical=optical,
        ball_height=stand,ball_dia=spec['ball_dia'],pads=pads,
        mechanical_dimensions=spec.get('mechanical_dimensions',{}),
        body_thickness=total-stand,
        origin='BODY XY center; PCB contact plane Z=0; top view +Y up',
        approximation=('Glass cover, sensor surface and die outline are appearance approximations; sensor XY and glass thickness follow datasheet; excludes internal circuitry and lens'
                       if optical else 'Rectangular body and spherical-cap balls; excludes cover glass, lens, chamfers and internal structure'),
        dimension_source=str(options.get('dimension_source','用户确认；缺失细节采用简化结构')))
    if appearance and optical:result['appearance_profile']=appearance
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def runtime():
    candidate=BASE/'workspace/model3d-runtime'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if candidate.is_file():return str(candidate)
    try:
        import cadquery  # noqa: F401
        return sys.executable
    except ImportError:
        raise ValueError('尚未安装 3D 引擎，请按 README 安装 requirements-model3d.txt（不影响 OLB / PCB）')


def build(spec, options, output, progress=lambda s:None):
    p=plan(spec,options);python=runtime();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    (output/'input.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
    progress('正在生成 STEP 本体与焊球，并独立重新导入核对…')
    result=subprocess.run([python,str(BASE/'model3d_worker.py'),str(output)],capture_output=True,
        text=True,encoding='utf8',errors='replace',timeout=180)
    if result.returncode:
        (output/'error.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
        raise ValueError('3D 引擎生成未完成，请检查独立环境和参数；日志：'+str(output/'error.log'))
    record=verify(output,expected=p)
    return dict(directory=str(output),step=str(output/record['step']),report=record)


def verify(output, expected=None):
    output=Path(output).resolve();r=json.loads((output/'model3d.json').read_text(encoding='utf8'))
    if r.get('status')!='PASS' or r.get('revision')!=1:raise ValueError('3D 重新导入检查未通过')
    if expected is not None and r.get('plan')!=json.loads(json.dumps(expected)):
        raise ValueError('3D 模型与当前机械参数不一致，请重新生成')
    for name,digest in r['file_hashes'].items():
        file=(output/name).resolve()
        if not file.is_relative_to(output) or file.suffix.lower() not in ('.step','.json'):
            raise ValueError('3D 文件路径无效')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise ValueError('3D 文件在验证后被修改')
    if r['step'] not in r['file_hashes'] or 'mesh.json' not in r['file_hashes']:
        raise ValueError('3D 文件校验记录不完整')
    return r
