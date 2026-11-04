"""Offline screenshot layout matching using Windows OCR and known pin names."""
import copy
import json
import os
import re
import subprocess
import tempfile
import uuid
from collections import defaultdict
from pathlib import Path
from PIL import Image, ImageOps


def normalized(text):
    return re.sub(r'[^A-Z0-9]', '', text.upper())


def windows_ocr(path, output):
    script = (Path(__file__).parent / 'ocr_windows.ps1').read_text(encoding='utf-8')
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    # Execute a fixed command block; do not change the machine's execution policy.
    command = '& {\n' + script + '\n} -ImagePath ' + quote(str(Path(path).resolve())) + ' -OutputPath ' + quote(str(Path(output).resolve()))
    executable = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, timeout=50, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or not Path(output).exists():
        error = result.stderr.decode('utf-8', errors='replace')
        raise ValueError('Windows OCR 无法识别截图，请确认已安装 OCR 语言包。' + error[-400:])
    return json.loads(Path(output).read_text(encoding='utf-8-sig'))['words']


def joined_words(words):
    """OCR sometimes splits MCP into MC and P. Join only close, collinear words."""
    result = list(words)
    rows = []
    for word in sorted(words, key=lambda w: (w['y'], w['x'])):
        row = next((r for r in rows if abs(r[0]['y']-word['y']) < max(word['h'], r[0]['h'])*0.5), None)
        if row is None:
            rows.append([word])
        else:
            row.append(word)
    for row in rows:
        row.sort(key=lambda w:w['x'])
        for i in range(len(row)):
            current = dict(row[i])
            for other in row[i+1:i+4]:
                if other['x']-(current['x']+current['w']) > max(current['h'],other['h'])*1.2:
                    break
                current['text'] += other['text']
                current['w'] = other['x']+other['w']-current['x']
                result.append(dict(current))
    return result


def detect_frame(image):
    import cv2
    import numpy as np
    array = np.array(image.convert('RGB'))
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    mask = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)[1]
    height, width = mask.shape
    lines = cv2.HoughLinesP(mask, 1, np.pi/180, threshold=50,
                           minLineLength=max(50, min(width,height)//5), maxLineGap=8)
    if lines is None:
        raise ValueError('截图里没有找到明确的符号外框，请裁剪到单个 PART，并保留完整矩形框')
    vertical, horizontal = [], []
    for ((x0,y0,x1,y1),) in lines:
        if abs(x1-x0) <= 3 and abs(y1-y0) > height*0.18:
            vertical.append((abs(y1-y0), (x0+x1)/2))
        if abs(y1-y0) <= 3 and abs(x1-x0) > width*0.18:
            horizontal.append((abs(x1-x0), (y0+y1)/2))
    def strongest_pair(values, length):
        positions = []
        for size, position in sorted(values, reverse=True):
            if any(abs(position-other)<8 for other in positions):
                continue
            positions.append(position)
            if len(positions)==2:
                break
        if len(positions)!=2 or abs(positions[0]-positions[1]) < length*0.15:
            raise ValueError('截图外框不明确，请裁剪到一个 PART，并保留完整边框')
        return sorted(positions)
    xs = strongest_pair(vertical, width)
    ys = strongest_pair(horizontal, height)
    return tuple(float(v) for v in (xs[0],ys[0],xs[1],ys[1]))


def match_words(pins, observations, frame):
    names = defaultdict(list)
    for pin in pins:
        names[normalized(pin['name'])].append(pin)
    hits = defaultdict(list)
    for word in observations:
        key = normalized(word['text'])
        if key not in names:
            continue
        point = (word['cx'], word['cy'])
        if any(abs(point[0]-old[0])+abs(point[1]-old[1]) < 18 for old in hits[key]):
            continue
        hits[key].append(point)
    x0,y0,x1,y1 = frame
    proposals = {}
    ambiguous = []
    for key, pins_for_name in names.items():
        points = hits.get(key, [])
        if len(points) != len(pins_for_name):
            if points:
                ambiguous.append(pins_for_name[0]['name'])
            continue
        points.sort(key=lambda point:(min(abs(point[0]-x0),abs(point[0]-x1),abs(point[1]-y0),abs(point[1]-y1)),point[1],point[0]))
        assigned = []
        for x,y in points:
            distances = {'LEFT':abs(x-x0),'RIGHT':abs(x-x1),'TOP':abs(y-y0),'BOT':abs(y-y1)}
            side = min(distances,key=distances.get)
            assigned.append((side, x if side in ('TOP','BOT') else y))
        assigned.sort(key=lambda item:(('TOP','BOT','LEFT','RIGHT').index(item[0]),item[1]))
        for pin, (side, position) in zip(pins_for_name,assigned):
            proposals[pin['id']] = dict(side=side, order=position)
    return proposals, ambiguous


def analyze(path, pins, progress=lambda msg: None):
    image = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    frame = detect_frame(image)
    width,height = image.size
    scale = min(2.0, 2300/max(width,height))
    base = image.resize((round(width*scale),round(height*scale)))
    words = []
    with tempfile.TemporaryDirectory(prefix='orcad-reference-') as temporary:
        for angle in (0,90,270):
            progress(f'正在识别截图布局（方向 {angle}°）…')
            rotated = base.rotate(angle, expand=True)
            path_variant = Path(temporary) / f'view-{angle}.png'
            rotated.save(path_variant)
            found = windows_ocr(path_variant, Path(temporary)/f'ocr-{angle}.json')
            for word in joined_words(found):
                x,y = word['x']+word['w']/2,word['y']+word['h']/2
                if angle==90:
                    x,y = base.width-y,x
                elif angle==270:
                    x,y = y,base.height-x
                words.append(dict(text=word['text'],cx=x/scale,cy=y/scale))
    proposals, ambiguous = match_words(pins,words,frame)
    if len(proposals) < min(2,len(pins)):
        raise ValueError('与当前 PART 匹配的引脚不足。请提供清晰的单个符号截图，截图名称应与规格书一致。')
    return dict(id=uuid.uuid4().hex, path=str(Path(path).resolve()), frame=frame,
                proposals=proposals, matched=len(proposals), unmatched=len(pins)-len(proposals), ambiguous=ambiguous,
                note='未匹配脚保留原布局；截图只调整位置和顺序，不修改引脚编号、名称或 10 MIL 间距。')


def apply(project, result, part):
    proposals = result['proposals']
    updated = []
    for pin in project['pins']:
        if pin.get('part','A')==part and pin['id'] in proposals:
            pin['side'] = proposals[pin['id']]['side']
        updated.append(pin)
    # Sort matched pins within each side; unmatched pins follow with stable order.
    target = [p for p in updated if p.get('part','A')==part]
    target.sort(key=lambda p:(('TOP','BOT','LEFT','RIGHT').index(p['side']),
                              proposals.get(p['id'],{}).get('order',float('inf'))))
    others = [p for p in updated if p.get('part','A')!=part]
    project['pins'] = others + target
    saved = {key:value for key,value in result.items() if key!='proposals'}
    saved['part'] = part
    project.setdefault('references',[]).append(saved)
