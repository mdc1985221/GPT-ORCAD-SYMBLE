"""Isolated OrCAD builds; publish a new version only after independent readback."""
import copy
import json
import os
import re
import struct
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
import assistant_core as core


def check_environment(env):
    problems = []
    for key, label in [('tclsh', 'OrCAD Tcl'), ('dll', 'OrCAD 数据库组件'), ('src_lib', '矩形源库'), ('bin', '依赖目录')]:
        if not Path(env.get(key, '')).exists() or not env.get(key):
            problems.append(f'{label}不存在：{env.get(key, "未设置")}')
    if not env.get('src_part', '').strip():
        problems.append('未设置源库中的矩形器件名')
    return problems


def run_tcl(script, directory, env, log):
    path = Path(script)
    # Tclsh can exit zero after a script error, so require a unique success marker too.
    content = path.read_text(encoding='utf-8')
    wrapped = 'if {[catch {\n' + content + '\n} reason]} {\n puts stderr $reason\n exit 1\n}\n'
    path.write_text(wrapped, encoding='utf-8')
    process_env = os.environ.copy()
    process_env['PATH'] = env['bin'] + os.pathsep + process_env.get('PATH', '')
    result = subprocess.run([env['tclsh'], str(path.resolve())], cwd=directory, env=process_env,
                            capture_output=True, timeout=120,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    output = result.stdout.decode('utf-8', errors='replace')
    error = result.stderr.decode('utf-8', errors='replace')
    log(output + error)
    if result.returncode or error.strip():
        raise RuntimeError(f'OrCAD 执行失败（{result.returncode}）：{error[-1500:] or output[-1500:]}')
    return output


def patch_frame(path, package, width, height, expected_frames=1):
    """Fail closed for the tested LM555 80x90 template; no global replacement."""
    import olefile
    if not (0 < width <= 32767 and 0 < height <= 32767):
        raise ValueError('外框超出当前模板的尺寸范围')
    with olefile.OleFileIO(str(path), write_mode=True) as ole:
        stream = 'Packages/' + package
        data = ole.openstream(stream).read()
        tag32 = struct.pack('<iiii', 0, 0, 80, 90)
        tag16 = struct.pack('<hhhh', 0, 0, 80, 90)
        offsets32 = [m.start() for m in re.finditer(re.escape(tag32), data)]
        offsets16 = [m.start() for m in re.finditer(re.escape(tag16), data)
                     if not any(i <= m.start() < i + 16 for i in offsets32)]
        if len(offsets32) != expected_frames or len(offsets16) != expected_frames:
            raise ValueError(f'源库外框结构不匹配（边界 {len(offsets32)}，矩形 {len(offsets16)}）；保留构建现场，请使用已验证的 LM555 源库')
        result = bytearray(data)
        for i in offsets32:
            result[i:i+16] = struct.pack('<iiii', 0, 0, width, height)
        for j in offsets16:
            result[j:j+8] = struct.pack('<hhhh', 0, 0, width, height)
        ole.write_stream(stream, bytes(result))
    with olefile.OleFileIO(str(path)) as ole:
        reread = ole.openstream(stream).read()
        if any(reread[i:i+16] != struct.pack('<iiii', 0, 0, width, height) for i in offsets32) or any(reread[j:j+8] != struct.pack('<hhhh', 0, 0, width, height) for j in offsets16):
            raise RuntimeError('外框写入后校验失败')
    return dict(bbox_offsets=offsets32, rectangle_offsets=offsets16, width=width, height=height)


def readback(path, cfg, env, log, designator=None, expected_devices=1):
    q = core.generator.tcl_quote
    script = Path(path).parent / ('verify-' + (designator or 'single') + '.tcl')
    source = f'''package require Tcl 8.4
load {q(env['dll'].replace(chr(92), '/'))} DboTclWriteBasic
proc str {{s}} {{return [DboTclHelper_sMakeCString $s]}}
proc sv {{s}} {{return [DboTclHelper_sGetConstCharPtr $s]}}
proc hx {{s}} {{binary scan [encoding convertto utf-8 $s] H* h; return $h}}
proc xy {{p}} {{return "[DboTclHelper_sGetCPointX $p]|[DboTclHelper_sGetCPointY $p]"}}
set s [DboTclHelper_sCreateSession]
set st [DboState]
set lib [$s GetLib [str {q(str(Path(path).resolve()).replace(chr(92), '/'))}] $st]
if {{[$st Failed]}} {{error "Library open failed"}}
set it [$lib NewPartsIter $st]
set part ""
for {{set n 0}} {{$n < 10000}} {{incr n}} {{
 set ps [DboState]; set p [$it NextPart $ps]
 if {{[$ps Failed]}} break
 set cs [str ""]; $p GetName $cs
 if {{[sv $cs] eq {q(cfg['device'] + '.Normal')}}} {{set part $p}}
}}
if {{$n == 10000 || $part eq ""}} {{error "Part missing or iteration limit"}}
set pkg [$part GetPackagePtr]
set pn [str ""]; $pkg GetName $pn
if {{[sv $pn] ne {q(cfg.get('package_name', cfg['device']))}}} {{error "Wrong shared package"}}
set cs [str ""]; $pkg GetPCBFootprint $cs
puts "FOOTPRINT|[hx [sv $cs]]"
set dit [$pkg NewDevicesIter [DboState]]
set count 0
set dev ""
while {{$count < 10000}} {{
 set ds [DboState]; set d [$dit NextDevice $ds]
 if {{[$ds Failed]}} break
 set dn [str ""]; $d GetDesignator $dn
 if {{{'1' if designator is None else '[sv $dn] eq ' + q(designator)}}} {{set dev $d}}
 incr count
}}
if {{$count != {expected_devices} || $dev eq ""}} {{error "Unexpected device count or missing section: $count"}}
if {{{expected_devices} > 1 && [$pkg IsHomogeneous [DboState]]}} {{error "Expected heterogeneous package"}}
puts "DEVICES|$count"
set pit [$part NewPinsIter [DboState]]
set idx 0
while {{$idx < 10000}} {{
 set ps [DboState]; set pin [$pit NextPin $ps]
 if {{[$ps Failed]}} break
 set nm [str ""]; $pin GetPinName $nm
 set cs [str ""]; set ns [$dev GetPinNumber $idx $cs]
 if {{[$ns Failed]}} {{error "Pin number missing"}}
 set ts [DboState]; set typ [$pin GetPinType $ts]
 set st0 [DboState]; set p0 [$pin GetStartPoint $st0]
 set st1 [DboState]; set p1 [$pin GetHotSpot $st1]
 puts "PIN|[hx [sv $cs]]|[hx [sv $nm]]|$typ|[xy $p0]|[xy $p1]"
 incr idx
}}
if {{$idx == 10000}} {{error "Pin iteration limit"}}
set cs [str ""]; set extra [$dev GetPinNumber $idx $cs]
if {{![$extra Failed] && [sv $cs] ne ""}} {{error "Extra device pin number"}}
DboTclHelper_sDeleteSession $s
puts "VERIFY_COMPLETE"
'''
    script.write_text(source, encoding='utf-8')
    output = run_tcl(script, Path(path).parent, env, log)
    if 'VERIFY_COMPLETE' not in output:
        raise RuntimeError('回读未正常完成')
    actual = []
    footprint = None
    for line in output.splitlines():
        if line.startswith('FOOTPRINT|'):
            footprint = bytes.fromhex(line.split('|')[1]).decode('utf-8')
        elif line.startswith('PIN|'):
            _, pid, name, *numbers = line.split('|')
            actual.append((bytes.fromhex(pid).decode('utf-8'), bytes.fromhex(name).decode('utf-8'), *map(int, numbers)))
    if footprint != cfg['pcb_footprint']:
        raise ValueError('回读 PCB Footprint 与项目不一致')
    return actual


def build(project, env, output_root, progress=lambda msg: None):
    project = copy.deepcopy(project)
    pending = core.issues(project)
    if pending:
        raise ValueError('请先处理待核对事项：' + pending[0]['text'])
    if len(core.part_ids(project)) > 1:
        return build_multipart(project, env, output_root, progress)
    cfg, expected = core.layout(project, env)
    errors = check_environment(env)
    if errors:
        raise ValueError('\n'.join(errors))
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    token = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    staging = root / ('.building-' + token)
    staging.mkdir()
    logs = []
    def log(msg):
        logs.append(msg)
        (staging / 'build.log').write_text('\n'.join(logs), encoding='utf-8')
    try:
        progress('正在生成构建脚本…')
        script, golden = core.generator.build(cfg, str(staging))
        core.export_svg(cfg, expected, staging / 'preview.svg')
        core.atomic_json(staging / 'project.json', project)
        progress('正在调用 OrCAD 构建符号…')
        text = run_tcl(script, staging, env, log)
        olb = staging / cfg['out_lib']
        if 'BUILD_COMPLETE' not in text or not olb.is_file() or olb.stat().st_size == 0:
            raise RuntimeError('OrCAD 未生成完整的新文件')
        progress('正在校准外框…')
        frame = patch_frame(olb, cfg['device'], cfg['W'], cfg['H'])
        progress('正在重新打开 OLB，逐脚验证…')
        actual = readback(olb, cfg, env, log)
        if len(actual) != len(expected) or set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))[:5]
            extra = sorted(set(actual) - set(expected))[:5]
            raise ValueError(f'OLB 回读与布局不一致：期望 {len(expected)} 脚，实际 {len(actual)} 脚；缺失 {missing}；异常 {extra}')
        report = dict(status='PASS', pins=len(actual), checks=['编号与名称配对', '电气类型', '全部端点坐标', '单一 device', 'PCB Footprint', '外框二进制回读'],
                      frame=frame, source_review='user_confirmed' if project.get('sources') else 'manual_input',
                      limitation='布局预览不是 Capture 截图；字体显示和实际网表/PCB 导入需在目标工程检查。')
        core.atomic_json(staging / 'verification.json', report)
        destination = root / (cfg['device'] + '-' + token)
        staging.rename(destination)
        progress('完成：OLB 已通过逐脚回读验证')
        return dict(directory=str(destination), olb=str(destination / olb.name), report=report)
    except Exception as exc:
        core.atomic_json(staging / 'verification.json', dict(status='FAILED', error=str(exc)))
        raise RuntimeError(f'{exc}\n\n上一次的成品未改动。诊断文件：{staging}') from exc


def build_multipart(project, env, output_root, progress):
    import csv
    errors = check_environment(env)
    if errors:
        raise ValueError('\n'.join(errors))
    sections = core.section_layouts(project, env)
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    token = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    staging = root / ('.building-' + token)
    staging.mkdir()
    q = core.generator.tcl_quote
    logs = []
    def log(msg):
        logs.append(msg)
        (staging / 'build.log').write_text('\n'.join(logs), encoding='utf-8')
    try:
        device = project['device']
        lines = [f'load {q(env["dll"].replace(chr(92), "/"))} DboTclWriteBasic',
                 'proc str {s} {return [DboTclHelper_sMakeCString $s]}',
                 'proc pt {x y} {return [DboTclHelper_sMakeCPoint $x $y]}',
                 'set s [DboTclHelper_sCreateSession]; set st [DboState]',
                 f'set src [$s GetLib [str {q(env["src_lib"].replace(chr(92), "/"))}] $st]',
                 f'set sourcePkg [$src GetPackage [str {q(env["src_part"])}] $st]',
                 f'set lib [$s CreateLib [str {q(device + ".OLB")}] $st]',
                 f'set pkg [$lib NewPackage [str {q(device)}] $st]',
                 '$pkg SetDesignator [str "U"]', '$pkg SetReferenceTemplate [str "U"]',
                 f'$pkg SetPCBFootprint [str {q(project["footprint"].strip())}]']
        for number, (section, cfg, pins) in enumerate(sections):
            name = cfg['device']
            lines += [f'set borrowed [$lib CopyPackageAll $sourcePkg [str {q(name)}] $st]',
                      f'set cell [$lib GetCell [str {q(name)}] $st]',
                      f'set part [$lib GetPart [str {q(name + ".Normal")}] $st]',
                      '$part SetPackagePtr $pkg', '$part SetCellPtr $cell', '$part RemoveSymbolPins',
                      f'set dev [$pkg NewDevice [str {q(section)}] {number} $cell $st]']
            for idx, (pid, pname, typ, sx, sy, hx, hy) in enumerate(pins):
                lines += [f'$part NewSymbolPinScalar $st [str {q(pname)}] {typ} [pt {sx} {sy}] [pt {hx} {hy}] 1 {idx}',
                          f'$dev NewPinNumber [str {q(pid)}] [DboTclHelper_sMakeInt {idx}]']
            lines += ['$part SetReference [str "U"]', f'$part SetPartValue [str {q(device)}]',
                      '$part SetPinNumbersAreVisible 1',
                      'set propIter [$part NewDisplayPropsIter [DboState]]',
                      'for {set j 0} {$j < 100} {incr j} {',
                      'set ps [DboState]; set dp [$propIter NextProp $ps]; if {[$ps Failed]} break',
                      'set cs [str ""]; $dp GetName $cs; set propName [DboTclHelper_sGetConstCharPtr $cs]',
                      f'if {{$propName eq "Part Reference"}} {{$dp SetLocation [pt {cfg["REF_POS"][0]} {cfg["REF_POS"][1]}]}}',
                      f'if {{$propName eq "Value"}} {{$dp SetLocation [pt {cfg["VAL_POS"][0]} {cfg["VAL_POS"][1]}]}}',
                      '}', '$lib DeletePackage $borrowed',
                      f'$lib ExplicitlyAddCellDirName {q(name)}',
                      f'$lib ExplicitlyAddPartDirName {q(name + ".Normal")}',
                      '$lib SavePart $part; $lib SaveCell $cell']
            core.export_svg(cfg, pins, staging / f'preview-{section}.svg')
        lines += [f'$lib ExplicitlyAddPackageDirName {q(device)}', '$lib SavePackage $pkg',
                  '$s MarkAllLibForSave $lib', '$s SaveLib $lib',
                  'DboTclHelper_sDeleteSession $s', 'puts "BUILD_COMPLETE"']
        script = staging / ('create_' + device + '.tcl')
        script.write_text('\n'.join(lines), encoding='utf-8')
        core.atomic_json(staging / 'project.json', project)
        progress(f'正在构建 {len(sections)} 个 PART，共用同一器件封装…')
        output = run_tcl(script, staging, env, log)
        olb = staging / (device + '.OLB')
        if 'BUILD_COMPLETE' not in output or not olb.is_file():
            raise RuntimeError('多 PART 文件没有正常生成')
        frame = patch_frame(olb, device, sections[0][1]['W'], sections[0][1]['H'], len(sections))
        checked = []
        with (staging / (device + '_ballmap.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['ball','name','type','part'])
            for section, cfg, expected in sections:
                progress(f'正在独立回读 PART {section}…')
                actual = readback(olb, cfg, env, log, section, len(sections))
                if len(actual) != len(expected) or set(actual) != set(expected):
                    raise ValueError(f'PART {section} 回读与布局不一致')
                checked.append(dict(part=section, pins=len(actual)))
                for pid, pname, typ, *rest in actual:
                    writer.writerow([pid,pname,typ,section])
        if sum(p['pins'] for p in checked) != len(project['pins']):
            raise ValueError('多 PART 的总引脚数不一致')
        report = dict(status='PASS', pins=len(project['pins']), parts=len(sections), sections=checked,
                      package=device, heterogeneous=True, frame=frame,
                      checks=['同一 package', '异构多单元', '完整且互不重复脚号', '逐 PART 名称/类型/坐标回读', 'PCB Footprint', '全部外框'])
        core.atomic_json(staging / 'verification.json', report)
        destination = root / (device + '-' + token)
        staging.rename(destination)
        progress('完成：所有 PART 已验证并归入同一器件')
        return dict(directory=str(destination), olb=str(destination / olb.name), report=report)
    except Exception as exc:
        core.atomic_json(staging / 'verification.json', dict(status='FAILED', error=str(exc)))
        raise RuntimeError(f'{exc}\n诊断文件：{staging}') from exc
