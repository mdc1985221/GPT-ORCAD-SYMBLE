"""Project, extraction and layout model shared by desktop and CLI."""
import csv
import hashlib
import json
import math
import re
from collections import Counter, OrderedDict
from pathlib import Path
from templates import gen_sensor_symbol as generator

SIDES = ('TOP', 'BOT', 'LEFT', 'RIGHT')
SIDE_LABELS = {'TOP': '顶部', 'BOT': '底部', 'LEFT': '左侧', 'RIGHT': '右侧'}
TYPES = ('PWR', 'GND', 'NC', 'IN', 'OUT', 'IO', 'ANA')
DEFAULT_ENV = dict(allegro='D:/tools/pcb/bin/allegro.exe',tclsh='D:/tools/tcltk/8.4/bin/tclsh84.exe',
                   dll='D:/tools/capture/orDb_Dll_Tcl.dll', bin='D:/tools/bin',
                   src_lib='D:/tools/capture/library/MiscLinear.olb', src_part='LM555')
PIN_RE = re.compile(r'^(?:[A-Z]{1,3}[1-9]\d{0,3}|[1-9]\d{0,4}|EP\d*|PAD\d*)$')


def natural(value):
    return tuple((1, int(x)) if x.isdigit() else (0, x.upper())
                 for x in re.split(r'(\d+)', str(value)) if x)


def pin_type(raw):
    text = re.sub(r'\s+', ' ', str(raw or '').strip().upper())
    if text in TYPES:
        return text
    chinese = {'地线': 'GND', '地': 'GND', '电源': 'PWR', '输入': 'IN',
               '输出': 'OUT', '输入/输出': 'IO', '模拟': 'ANA', '悬空': 'NC'}
    if text in chinese:
        return chinese[text]
    if 'GROUND' in text:
        return 'GND'
    if 'POWER' in text:
        return 'PWR'
    if re.search(r'\bNC\b|NOT CONNECT', text):
        return 'NC'
    if ('INPUT' in text and 'OUTPUT' in text) or text in ('I/O', 'I\\O'):
        return 'IO'
    if 'OUTPUT' in text:
        return 'OUT'
    if 'INPUT' in text:
        return 'IN'
    if 'ANALOG' in text:
        return 'ANA'
    return ''


def new_project():
    return dict(version=1, device='', footprint='', profile='sensor', pitch=10,
                expected_count=None, sources=[], pins=[], reviewed=[], generated=None,
                parts={'A': '主单元'}, references=[])


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def load_project(path):
    project = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if project.get('version') != 1 or not isinstance(project.get('pins'), list):
        raise ValueError('不是受支持的符号项目文件')
    if project.get('profile') not in ('sensor', 'simple'):
        raise ValueError('未知布局模板')
    if not isinstance(project.get('pitch'), int) or project['pitch'] < 10 or project['pitch'] % 10:
        raise ValueError('项目间距必须是正的 10 MIL 整数倍')
    for pin in project['pins']:
        if not all(isinstance(pin.get(k), str) for k in ('id', 'name', 'type', 'side', 'group')):
            raise ValueError('项目引脚数据损坏')
        pin.setdefault('part', 'A')
    project.setdefault('parts', {'A': '主单元'})
    project.setdefault('references', [])
    invalidate_legacy_pcb(project)
    return project


def invalidate_legacy_pcb(project):
    """Numerical-only legacy verification did not establish physical units."""
    generated = project.get('generated') or {}
    report = generated.get('report', {})
    if 'pcb' in report and report['pcb'].get('units') != 'millimeters':
        generated['report']['status'] = 'INVALID_UNITS'
        generated['report']['pcb']['status'] = 'INVALID_UNITS'
        generated.pop('archive', None)
        generated['warning'] = '旧版 PCB 使用 mil 数据库写入毫米数值，物理比例错误。请重新生成；勿使用旧 DRA/PSM/PAD。'
    elif 'pcb' in report and report['pcb'].get('pad_imports',{}).get('status') != 'PASS':
        report['status'] = 'REBUILD_PADSTACK'
        report['pcb']['status'] = 'REBUILD_PADSTACK'
        generated.pop('archive',None)
        generated['warning'] = '旧版通用 BALL20 名称可能命中 PCB 内的 0.2 mil 旧焊盘。请重新生成，使用新版独立命名 PAD，并更新已有 PCB 的封装实例。'
    elif 'pcb' in report and report['pcb'].get('drawing',{}).get('revision') != 2:
        report['status']='REBUILD_GEOMETRY'
        report['pcb']['status']='REBUILD_GEOMETRY'
        generated.pop('archive',None)
        generated['warning']='请重新生成以更新中心箭头标注、脚号及 Place Bound 高度，并更新 PCB 中的旧封装实例。'


def source_record(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def import_csv(path):
    pins = []
    with open(path, encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    if not rows:
        raise ValueError('CSV 是空的')
    header = [x.strip().lower() for x in rows[0]]
    aliases = {'id': ('ball', 'pin', 'id', 'number', '脚号'),
               'name': ('name', '名称'), 'type': ('type', '类型'),
               'side': ('edge', 'side', '边'), 'group': ('group', '分组'), 'part': ('part','section','单元')}
    indexes = {key: next((header.index(a) for a in names if a in header), None)
               for key, names in aliases.items()}
    if indexes['id'] is None or indexes['name'] is None:
        indexes = dict(id=0, name=1, type=2, side=3, group=4, part=None)
    else:
        rows = rows[1:]
    for number, row in enumerate(rows, 2):
        if not row or row[0].startswith('#'):
            continue
        def cell(key):
            idx = indexes[key]
            return row[idx].strip() if idx is not None and idx < len(row) else ''
        if not cell('id') or not cell('name'):
            raise ValueError(f'CSV 第 {number} 行缺少脚号或名称')
        side = cell('side').upper()
        pins.append(dict(id=cell('id').upper(), name=cell('name'), type=pin_type(cell('type')), part=cell('part').upper() or 'A',
                         side=side if side in SIDES else '', group=cell('group'),
                         page=None, source=str(Path(path).resolve()), raw=', '.join(row),
                         confidence=1.0, conflicts=[]))
    if not pins:
        raise ValueError('CSV 中没有引脚')
    return pins


def extract_pdf(path, progress=lambda msg: None):
    """Text tables first. Preserve page, bbox and conflicting observations."""
    import pdfplumber
    observations = []
    text_pages = 0
    table_count = 0
    with pdfplumber.open(path) as pdf:
        previous = None
        for number, page in enumerate(pdf.pages, 1):
            page_start = len(observations)
            progress(f'正在读取规格书：第 {number} / {len(pdf.pages)} 页')
            tables = page.find_tables({'snap_tolerance': 4})
            table_count += len(tables)
            for table in tables:
                rows = table.extract()
                if not rows:
                    continue
                columns = None
                start = 0
                for index, row in enumerate(rows[:3]):
                    head = [re.sub(r'\s+', ' ', c or '').strip().lower() for c in row]
                    head = [re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', c) for c in head]
                    def locate(pattern):
                        return next((i for i, c in enumerate(head) if re.fullmatch(pattern, c)), None)
                    ident = locate(r'(?:pin|pad|ball)(?:\s*(?:no\.?|number|#|num\.?))?\.?|引脚(?:编号|号)?|管脚(?:编号|号)?|球号|编号')
                    name = locate(r'(?:pin |signal |pad |ball )?name|signal|symbol|引脚名称|信号名称|信号名|管脚名称')
                    typ = locate(r'(?:pin |signal )?type|i/o|io|类型|引脚类型')
                    if ident is not None and name is not None:
                        columns = (ident, name, typ)
                        previous = (columns, len(row), number)
                        start = index + 1
                        break
                # Only accept continuation with compatible shape on next page.
                if columns is None and previous and previous[2] in (number - 1, number):
                    cols, width, _ = previous
                    if len(rows[0]) == width:
                        columns = cols
                if columns is None:
                    continue
                ident, name, typ = columns
                for row in rows[start:]:
                    if max(ident, name) >= len(row):
                        continue
                    pid = re.sub(r'\s+', '', row[ident] or '').upper()
                    pname = re.sub(r'\s+', '', row[name] or '')
                    if not PIN_RE.fullmatch(pid) or not pname or pname == '\\':
                        continue
                    raw_type = row[typ] if typ is not None and typ < len(row) else ''
                    resolved_type = pin_type(raw_type)
                    if not resolved_type and pname.upper() == 'NC':
                        resolved_type = 'NC'
                    observations.append(dict(id=pid, name=pname, type=resolved_type, part='A',
                        side='', group='', page=number, bbox=list(table.bbox),
                        source=str(Path(path).resolve()), raw=' | '.join(c or '' for c in row),
                        confidence=0.9, conflicts=[]))
            # Text fallback restricted to pin-description pages; never replace table results.
            text = page.extract_text() or ''
            if text.strip():
                text_pages += 1
            if len(observations) == page_start and re.search(r'pin descriptions?|pad configuration|pin assignment|引脚说明|引脚描述', text, re.I):
                for line in text.splitlines():
                    match = re.match(r'^\s*([A-Z]{1,3}\d+|\d+|EP)\s+([A-Za-z][\w/+.\-]*)\s+(.+)$', line)
                    if match and PIN_RE.fullmatch(match[1]):
                        typ = pin_type(match[3])
                        if typ:
                            observations.append(dict(id=match[1], name=match[2], type=typ, part='A',
                                side='', group='', page=number, source=str(Path(path).resolve()),
                                raw=line, confidence=0.65, conflicts=[]))
    # PDF line art and watermarks can merge cells. Parse vertically stored
    # description tables using native text order, only after an explicit header.
    import fitz
    from contextlib import nullcontext
    with (fitz.open(path) if Path(path).is_file() else nullcontext([])) as native:
        for number, page in enumerate(native, 1):
            text = page.get_text()
            header = re.search(r'Pin\s+Name\s+Type\s+A/D\s+Description', text)
            if not header:
                continue
            body = text[header.end():]
            pattern = r'(?m)^([A-Z]{1,3}[1-9]\d*)\s*\n([A-Za-z][\w/+.\-]*)\s*\n(Ground|Power(?:/NC)?|Input/Output|Input(?:/NC)?|Output|NC)\s*\n([AD/])\s*\n'
            matches = list(re.finditer(pattern, body))
            if not matches:
                continue
            observations = [p for p in observations if p['page'] != number]
            for index, match in enumerate(matches):
                raw = body[match.start():matches[index+1].start() if index+1<len(matches) else len(body)].strip()
                typ = pin_type(match[3])
                # Explicit model-specific NC instruction overrides a shared-family label.
                nc_model = re.search(r'NC for ([A-Z]+[0-9]+)', raw)
                if nc_model and re.search(r'\b'+re.escape(nc_model[1])+r'\b', text[:header.start()]):
                    typ = 'NC'
                observations.append(dict(id=match[1], name=match[2], type=typ, part='A',
                    side='', group='', page=number, source=str(Path(path).resolve()),
                    raw=raw, confidence=.9, conflicts=[]))
    found = OrderedDict()
    for pin in observations:
        old = found.get(pin['id'])
        if old is None:
            found[pin['id']] = pin
        elif (old['name'], old['type']) != (pin['name'], pin['type']):
            old['conflicts'].append(dict(name=pin['name'], type=pin['type'], page=pin['page'], raw=pin['raw']))
    if not found:
        reason = ('未检测到可提取的文字，可能是扫描件；当前尚不支持扫描 PDF 的引脚表 OCR。'
                  if not text_pages else
                  'PDF 中有文字，但未识别到受支持的引脚表结构；这不代表它是扫描件。')
        raise ValueError(f'未能提取引脚表：{Path(path).name}\n\n{reason}\n'
                         f'检测结果：{text_pages} 个页面含文字，{table_count} 个候选表格。\n\n'
                         '请提供这份 PDF 以适配格式，或暂时导入含脚号、名称、类型的 CSV。')
    return list(found.values())


def high_speed(name):
    return bool(re.fullmatch(r'(?:M\d+(?:C|D\d+)[PN]|MD(?:[PN]\d*|\d+[PN])|MC[PN]|MIPI\w*|D[0-9]+[PN]|CLK[PN]|CK[PN])', name.upper()))


def signal_order(pin):
    name = pin['name'].upper()
    port = re.fullmatch(r'M(\d+)(C|D(\d+))([PN])', name)
    if port:
        return (-1, int(port[1]), -1 if port[2] == 'C' else int(port[3]), 0 if port[4] == 'N' else 1)
    clock = bool(re.match(r'^(?:MC[PN]|CLK[PN]|CK[PN])$', name))
    pair = re.match(r'^(.*?)([PN])(?:_?(\d+))?$', name)
    pair2 = re.match(r'^(MD)([PN])(\d+)$', name)
    lane = re.match(r'^(?:MD|D)(\d+)([PN])$', name)
    if lane:
        return (1, natural(lane[1]), 0 if lane[2] == 'N' else 1, natural(pin['id']))
    if pair2:
        return (1, natural(pair2[3]), 0 if pair2[2] == 'N' else 1, natural(pin['id']))
    if pair:
        return (0 if clock else 2, natural(pair[1] + (pair[3] or '')), 0 if pair[2] == 'N' else 1, natural(pin['id']))
    priorities = {'RESET': 0, 'RST': 0, 'XSHUTDOWN': 1, 'PWDN': 2, 'MCLK': 3, 'INCLK': 3, 'SCL': 4, 'SBCL': 4, 'SDA': 5, 'SBDATA': 5}
    return (3, ((1, priorities.get(name, 10)),) + natural(name), 0, natural(pin['id']))


def auto_layout(project):
    pins = project['pins']
    if project['profile'] == 'simple':
        exposed = [p for p in pins if re.fullmatch(r'(?:EP|PAD)\d*', p['id'])]
        ordered = sorted([p for p in pins if p not in exposed], key=lambda p: natural(p['id']))
        half = math.ceil(len(ordered) / 2)
        left = ordered[:half][::-1]
        right = ordered[half:]
        for p in left:
            p.update(side='LEFT', group='引脚')
        for p in right:
            p.update(side='RIGHT', group='引脚')
        for p in exposed:
            p.update(side='BOT', group='裸露焊盘')
        project['pins'] = left + right + exposed
        return
    for p in pins:
        typ = p['type']
        side = 'TOP' if typ == 'PWR' else 'BOT' if typ in ('GND', 'NC') else 'RIGHT' if high_speed(p['name']) else 'LEFT'
        group = re.sub(r'_\d+$', '', p['name']) if typ in ('PWR', 'GND') else 'NC' if typ == 'NC' else 'MIPI' if side == 'RIGHT' else '信号'
        p.update(side=side, group=group)
    pins.sort(key=lambda p: (SIDES.index(p['side']),
                            (1 if p['type'] == 'NC' else 0),
                            natural(p['group']), signal_order(p)))


def issues(project):
    result = []
    def add(key, text, pin='', blocking=False):
        result.append(dict(key=key, text=text, pin=pin, blocking=blocking))
    if not project['pins']:
        add('empty', '先导入规格书或引脚表', blocking=True)
    ids = Counter(p['id'] for p in project['pins'])
    for pin in project['pins']:
        pid = pin['id']
        if not re.fullmatch(r'[A-Z]{1,2}',pin.get('part','A')):
            add('part-format:' + pid, f'{pid}：PART 名请使用 A～Z 或 AA～ZZ', pid, True)
        if pin.get('part', 'A') not in project.get('parts', {'A': '主单元'}):
            add('part:' + pid, f'{pid}：所属 PART 不存在', pid, True)
        if ids[pid] > 1:
            add('duplicate:' + pid, f'{pid}：脚号重复，请修正', pid, True)
        if not PIN_RE.fullmatch(pid):
            add('id:' + pid, f'{pid}：请核对脚号格式', pid, True)
        if not pin['name'].strip() or re.search(r'[\x00-\x1f|]', pin['name']):
            add('name:' + pid, f'{pid}：名称为空或含控制字符 / 分隔符', pid, True)
        if pin['type'] not in TYPES:
            add('type:' + pid, f'{pid}：请选择电气类型', pid, True)
        if pin['side'] not in SIDES:
            add('side:' + pid, f'{pid}：请选择位置', pid, True)
        if pin.get('conflicts'):
            signature = hashlib.sha256(json.dumps([pin['name'], pin['type'], pin['conflicts']], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
            add(f'conflict:{pid}:{signature}', f'{pid}：规格书出现不同定义，请对照原文', pid)
        if pin.get('confidence', 1) < 0.8:
            add('confidence:' + pid + ':' + pin['name'], f'{pid}：来自文本行推断，请核对原文', pid)
    for reference in project.get('references', []):
        add('reference:' + reference['id'], f'截图布局：匹配 {reference["matched"]} 脚，未匹配 {reference["unmatched"]} 脚；请检查预览后确认')
    expected = project.get('expected_count')
    if expected and expected != len(project['pins']):
        add(f'count:{expected}:{len(project["pins"])}', f'预期 {expected} 脚，当前 {len(project["pins"])} 脚，请核对空白球位 / EP', blocking=True)
    for source in project.get('sources', []):
        if source['path'].lower().endswith('.pdf'):
            signature = hashlib.sha256(json.dumps([(p['id'], p['name'], p['type']) for p in project['pins']], ensure_ascii=False).encode()).hexdigest()[:12]
            add('coverage:' + source['sha256'] + ':' + signature,
                '请确认规格书的引脚总数及空白球位；文字抽取无法独立证明没有漏脚')
    reviewed = set(project.get('reviewed', []))
    return [r for r in result if r['blocking'] or r['key'] not in reviewed]


def config(project, env):
    device = project['device'].strip()
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}', device) or device.endswith('.'):
        raise ValueError('器件名请使用字母、数字、下划线、短横线或点（最多 80 字符）')
    if device.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}:
        raise ValueError('器件名不能使用 Windows 保留名称')
    if not project['footprint'].strip():
        raise ValueError('请填写 PCB 封装名；不确定时可先预览')
    blocking = [i for i in issues(project) if i['blocking']]
    if blocking:
        raise ValueError(blocking[0]['text'])
    groups = {}
    for side in SIDES:
        collected = []
        # Preserve explicit list order (including drag edits); separate consecutive groups.
        for pin in (p for p in project['pins'] if p['side'] == side):
            label = pin['group'] or '引脚'
            if collected and collected[-1][0] == label:
                collected[-1][1].append(pin['id'])
            else:
                collected.append((label, [pin['id']]))
        groups[side] = collected
    pitch = int(project['pitch'])
    if pitch < 10 or pitch % 10:
        raise ValueError('间距必须是正的 10 MIL 整数倍')
    def span(side):
        return max(0, sum(len(g[1]) for g in groups[side]) - 1 + max(0, len(groups[side]) - 1)) * pitch
    # Label lengths require room along the inside normal, not wider pin spacing.
    horizontal = max((len(p['name']) for p in project['pins'] if p['side'] in ('LEFT', 'RIGHT')), default=4) * 6
    vertical = max((len(p['name']) for p in project['pins'] if p['side'] in ('TOP', 'BOT')), default=4) * 6
    margin_y = math.ceil(max(60, vertical + 40) / 10) * 10
    margin_x = math.ceil(max(60, horizontal + 40) / 10) * 10
    round20 = lambda n: math.ceil(n / 20) * 20
    width = round20(max(260, max(span('TOP'), span('BOT')) + 2 * margin_x, 2 * horizontal + 120))
    height = round20(max(260, max(span('LEFT'), span('RIGHT')) + 2 * margin_y, 2 * vertical + 120))
    return dict(device=device, part_suffix='Normal', out_lib=device + '.OLB',
                pcb_footprint=project['footprint'].strip(), ref_des='U',
                src_lib=env['src_lib'].replace('\\', '/'), src_part=env['src_part'],
                dll_path=env['dll'].replace('\\', '/'), tcl_pkg='DboTclWriteBasic',
                layout_style='grouped', MASTER={p['id']: (p['name'], p['type']) for p in project['pins']},
                W=width, H=height, Y0=margin_y, PITCH=pitch, GAP=1,
                REF_POS=(width // 2, height // 2 - 20), VAL_POS=(width // 2, height // 2 + 20),
                DROP_BALLS=set(), DROP_NC=False, **groups)


def layout(project, env):
    cfg = config(project, env)
    return cfg, generator.build(cfg, dry_run=True)


def part_ids(project):
    used = {p.get('part', 'A') for p in project['pins']}
    return [key for key in project.get('parts', {'A': '主单元'}) if key in used] or ['A']


def subproject(project, part):
    import copy
    result = copy.deepcopy(project)
    result['pins'] = [p for p in result['pins'] if p.get('part', 'A') == part]
    result['expected_count'] = None
    result['references'] = []
    return result


def split_parts(project, maximum=64):
    if maximum < 8 or maximum > 500:
        raise ValueError('每个 PART 的脚数上限请设为 8～500')
    buckets = OrderedDict()
    for pin in project['pins']:
        category = '电源与地' if pin['type'] in ('PWR','GND','NC') else '高速接口' if high_speed(pin['name']) else '控制与信号'
        buckets.setdefault(category, []).append(pin)
    parts = {}
    count = 0
    for category, pins in buckets.items():
        chunks = []
        for pin in pins:
            if not chunks or len(chunks[-1]) >= maximum:
                # Never split an adjacent differential pair between two parts.
                paired = bool(chunks and re.sub(r'[PN](?=\d*$)', '', pin['name']) == re.sub(r'[PN](?=\d*$)', '', chunks[-1][-1]['name']))
                if not paired:
                    chunks.append([])
            chunks[-1].append(pin)
        for index, chunk in enumerate(chunks):
            label = chr(65 + count) if count < 26 else 'A' + chr(65 + count - 26)
            if count >= 52:
                raise ValueError('当前最多支持 52 个 PART')
            parts[label] = category + (f' {index+1}' if len(chunks)>1 else '')
            for pin in chunk:
                pin['part'] = label
            count += 1
    project['parts'] = parts or {'A':'主单元'}


def section_layouts(project, env):
    # Resolve names globally before splitting, so duplicate power pins remain unique.
    _, all_pins = layout(project, env)
    names = {p[0]: p[1] for p in all_pins}
    sections = []
    for section in part_ids(project):
        part = subproject(project, section)
        for pin in part['pins']:
            pin['name'] = names[pin['id']]
        cfg = config(part, env)
        cfg['device'] = project['device'] + ' ' + section
        cfg['package_name'] = project['device']
        cfg['out_lib'] = project['device'] + '.OLB'
        sections.append((section, cfg))
    width = max(cfg['W'] for _, cfg in sections)
    height = max(cfg['H'] for _, cfg in sections)
    for _, cfg in sections:
        cfg.update(W=width, H=height, REF_POS=(width//2,height//2-20), VAL_POS=(width//2,height//2+20))
    return [(section, cfg, generator.build(cfg, dry_run=True)) for section, cfg in sections]


def export_svg(cfg, pins, path):
    from html import escape
    w, h = cfg['W'], cfg['H']
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-100 -100 {w+200} {h+200}">',
             '<rect x="-100" y="-100" width="100%" height="100%" fill="#f8fafc"/>',
             f'<rect width="{w}" height="{h}" fill="white" stroke="#344862"/>']
    for pid, name, typ, x, y, hx, hy in pins:
        lines.append(f'<line x1="{x}" y1="{y}" x2="{hx}" y2="{hy}" stroke="#2563eb"/>')
        rotate = -90 if x == hx else 0
        tx = x + 5 if x == 0 else x - 5 if x == w else x
        ty = y + 8 if y == 0 else y - 8 if y == h else y
        anchor = 'end' if x == w or y == 0 else 'start'
        lines.append(f'<text x="{tx}" y="{ty}" font-family="sans-serif" font-size="6" text-anchor="{anchor}" transform="rotate({rotate},{tx},{ty})">{escape(name)}</text>')
        nx, ny = (x - 3, (y + hy) / 2) if x == hx else ((x + hx) / 2, y - 3)
        lines.append(f'<text x="{nx}" y="{ny}" text-anchor="middle" transform="rotate({rotate},{nx},{ny})" font-family="sans-serif" font-size="5" fill="#64748b">{escape(pid)}</text>')
    lines.append(f'<text x="{w/2}" y="{h/2}" text-anchor="middle" font-family="sans-serif" font-size="12">{escape(cfg["device"])}</text></svg>')
    Path(path).write_text('\n'.join(lines), encoding='utf-8')
