# -*- coding: utf-8 -*-
"""
build_footprint.py  —  传感器 CSP/WLCSP 封装「一键流水线」
=========================================================================
给定一份封装参数（数据手册 +Y 向上约定），自动产出：
  1) KiCad 封装      <name>.kicad_mod      (含 KiCad 6/7 双语法)
  2) 坐标表          <name>_pads.csv
  3) 校对图          <name>_preview.html    (SVG, Top View)
  4) Allegro 脚本    allegro/<name>_build.il
                     allegro/gen_<name>.scr (全自动无 GUI 批处理入口)
  5) Pad Designer 脚本 allegro/BALLxx_pad.scr + make_pads.bat
                     (仅用于把物理 .pad 存进你自己的 pad 库；生成封装不需要它)

设计约定
  * 坐标：原点 = 本体重心 (body center)
  * 输入参数：+Y 向上（数据手册 Top View，A 行在上）—— 与 Allegro 一致
  * 输出 KiCad：自动把 Y 取反（KiCad 文件约定 +Y 向下）
  * 偏心三中心：BODY(0,0) 固定；BGA / OPT 由数据手册给定

全自动生成 Allegro 封装（无需点鼠标）
  allegro.exe -s gen_<name>.scr -nograph
  原理：padstack 由 .il 用 axlDBCreatePadStack 直接建在 drawing 数据库里，
        因此 **不依赖 padpath、不依赖 .pad 文件、不依赖 Pad Designer**。
  （16.6 实测：allegro.exe -s <script> -nograph 可无人值守运行；
    File>Create Symbol 等价于命令行 create_sym.exe。）

唯一仍需人工的步骤：把数据手册尺寸填进 CONFIG（或 --spec xxx.json）。

用法
  python build_footprint.py                 # 用下方嵌入的 SC535HAI 配置
  python build_footprint.py --spec my.json  # 用外部 JSON 配置
  python build_footprint.py --out D:/out    # 覆盖输出目录
  python build_footprint.py --kicad 7       # 生成 KiCad 7/8/9 语法
"""
import csv, json, os, re, sys, subprocess
try:
    from templates.footprint.drawing import presentation
except ModuleNotFoundError:
    from drawing import presentation

# ===================================================================
# CONFIG —— 数据手册 nominal 尺寸（+Y 向上；单位 mm）
# 改这里即可适配任意同类 sensor CSP。也可放到 --spec JSON 里。
# ===================================================================
CONFIG = {
    "name": "SC535HAI_CSP41",
    "descr": "41-ball CSP image sensor, origin = package body center",
    "body": [6.086, 4.760],          # [X, Y] 本体尺寸
    "pitch": [0.730, 0.650],          # [X, Y] 球间距
    "edge": {                         # 最外侧球中心 -> 本体边缘 的距离
        "left_to_col1": 0.893,
        "right_to_colN": 0.813,
        "top_to_rowA": 0.666,
        "bottom_to_rowN": 0.844,
    },
    "rows": "ABCDEF",                 # 行名（从顶部 A 起）
    "cols": 7,                        # 列数
    "missing": ["B4"],                # 缺球引脚名
    "ball_dia": 0.300,                # 球径
    "pad_dia": 0.250,                 # 焊盘直径 (NSMD, ~83% 球径)
    "mask_margin": 0.0508,            # 阻焊开窗 = 焊盘 + 2*margin (0.0508mm=2mil/边, 直径比焊盘大 4mil)
    "paste_dia": 0.250,               # 钢网开窗直径
    "courtyard_excess": 0.25,         # 禁布/占位外扩
    # 偏心基准中心（数据手册 +Y 向上，相对本体重心）
    "centers": {
        "BGA": [0.040,  0.089],       # CHIP / 球阵列中心
        "OPT": [0.040, -0.121],       # 光学中心
    },
    "kicad_version": 6,               # 6 = KiCad 6.0 语法
}


def load_spec(path):
    with open(path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    base = dict(CONFIG)
    base.update(spec)
    return base


# ---------- 几何计算（统一在 +Y 向上坐标系）----------
def compute(cfg):
    A, B = cfg["body"]; PX, PY = cfg["pitch"]; e = cfg["edge"]
    hx, hy = A / 2.0, B / 2.0
    nrows, ncols = len(cfg["rows"]), cfg["cols"]
    # 自洽校验
    assert abs((e["left_to_col1"] + (ncols - 1) * PX + e["right_to_colN"]) - A) < 1e-6, "X 向尺寸不闭合"
    assert abs((e["top_to_rowA"] + (nrows - 1) * PY + e["bottom_to_rowN"]) - B) < 1e-6, "Y 向尺寸不闭合"
    col_x = [-(hx - e["left_to_col1"]) + i * PX for i in range(ncols)]      # 左负右正
    row_y = [(hy - e["top_to_rowA"]) - i * PY for i in range(nrows)]        # A 在上为正
    missing = set(cfg["missing"])
    pads = [(cfg["rows"][r] + str(c + 1), round(col_x[c], 4), round(row_y[r], 4))
            for r in range(nrows) for c in range(ncols)
            if cfg["rows"][r] + str(c + 1) not in missing]
    arr_c = ((col_x[0] + col_x[-1]) / 2.0, (row_y[0] + row_y[-1]) / 2.0)
    if "BGA" in cfg["centers"]:
        bx, by = cfg["centers"]["BGA"]
        assert abs(arr_c[0] - bx) < 1e-6 and abs(arr_c[1] - by) < 1e-6, \
            f"球阵列中心算得 {arr_c}，与配置的 BGA 中心 ({bx},{by}) 不符"
    return dict(A=A, B=B, PX=PX, PY=PY, hx=hx, hy=hy, col_x=col_x, row_y=row_y,
                pads=pads, arr_c=arr_c, nrows=nrows, ncols=ncols)


# ===================================================================
# 1) KiCad 封装
# ===================================================================
def gen_kicad(cfg, geo, out_dir):
    c = cfg; g = geo
    A, B, hx, hy = g["A"], g["B"], g["hx"], g["hy"]
    PX, PY = g["PX"], g["PY"]
    V6 = (c["kicad_version"] == 6)
    ver = "20211014" if V6 else "20221018"
    lyr = lambda s: s if V6 else f'"{s}"'
    f3 = lambda v: f"{v:.3f}"

    def shape_tail(layer, wd, fill=None):
        if V6:
            return f'(layer {lyr(layer)}) (width {wd})' + (f' (fill {fill})' if fill else '')
        return f'(layer {lyr(layer)}) (stroke (width {wd}) (fill {fill or "none"}))'

    pts_of = lambda pts: " ".join(f'(xy {f3(p[0])} {f3(p[1])})' for p in pts)
    circle = lambda cx, cy, ex, ey, layer, wd: \
        f'(fp_circle (center {f3(cx)} {f3(cy)}) (end {f3(ex)} {f3(ey)}) {shape_tail(layer, wd)})'
    line = lambda x0, y0, x1, y1, layer, wd: \
        f'(fp_line (start {f3(x0)} {f3(y0)}) (end {f3(x1)} {f3(y1)}) {shape_tail(layer, wd)})'
    poly = lambda pts, layer, wd: f'(fp_poly (pts {pts_of(pts)}) {shape_tail(layer, wd, "solid")})'

    # KiCad 用 +Y 向下：把 +Y 向上的坐标翻转
    kx = lambda x: x
    ky = lambda y: -y
    col_x = [kx(v) for v in g["col_x"]]
    row_y = [ky(v) for v in g["row_y"]]
    pads = [(nm, kx(x), ky(y)) for nm, x, y in g["pads"]]
    centers = {k: (kx(x), ky(y)) for k, (x, y) in c["centers"].items()}

    L = []
    w = lambda s="": L.append(s)
    w(f'(footprint "{c["name"]}" (version {ver}) (generator pcbnew)')
    w(f'\t(layer {lyr("F.Cu")})')
    ox_s = c["centers"].get("OPT", (0, 0))
    w(f'\t(descr "{c["descr"]} body {A}x{B} ball D{c["ball_dia"]} pitch {PX}/{PY}; '
      f'origin = body center; optical center at ({ox_s[0]:.4f},{ox_s[1]:.4f}) mm +Y-up")')
    w('\t(attr smd)')
    # 字号与焊盘匹配：0.25mm 焊盘 / 0.6-0.7 间距的 CSP，用 0.8mm 字号（原 1.0 偏大）
    ref_y = hy + c["courtyard_excess"] + 0.45
    w(f'\t(fp_text reference REF** (at 0 {f3(-ref_y)}) (layer {"F.SilkS"}) (effects (font (size 0.8 0.8) (thickness 0.12))))')
    w(f'\t(fp_text value {c["name"]} (at 0 {f3(ref_y)}) (layer {"F.Fab"}) (effects (font (size 0.8 0.8) (thickness 0.12))))')
    # pin1 标记：丝印圆点 + 丝印三角(指向A1) + Fab 三角
    w('\t' + circle(col_x[0] - 0.45, row_y[0] - 0.45, col_x[0] - 0.30, row_y[0] - 0.45, "F.SilkS", 0.12))
    w('\t' + poly([(col_x[0] - 0.35, row_y[0] - 0.16), (col_x[0] - 0.35, row_y[0] + 0.16), (col_x[0] - 0.65, row_y[0])], "F.SilkS", 0.10))
    w('\t' + poly([(col_x[0] - 0.60, row_y[0] + 0.16), (col_x[0] - 0.30, row_y[0] + 0.16), (col_x[0] - 0.60, row_y[0] + 0.46)], "F.Fab", 0.05))
    # 本体轮廓
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        xs = [-hx, hx, hx, -hx]; ys = [-hy, -hy, hy, hy]
        w('\t' + line(xs[a], ys[a], xs[b], ys[b], "F.Fab", 0.05))
    w('\t' + line(-hx, -hy + 0.8, -hx, -hy, "F.Fab", 0.2))
    w('\t' + line(-hx, -hy, -hx + 0.8, -hy, "F.Fab", 0.2))

    def cross(x, y, r, layer="F.Fab", wd=0.05):
        w('\t' + line(x - r, y, x + r, y, layer, wd))
        w('\t' + line(x, y - r, x, y + r, layer, wd))
    cross(0, 0, 0.35, "F.Fab", 0.08)
    w(f'\t(fp_text user "BODY(0,0)" (at -0.55 0.5) (layer {"F.Fab"}) (effects (font (size 0.4 0.4) (thickness 0.06))))')
    # 合并坐标重合的中心（如 BGA==OPT 时只画一次，避免标签重叠）
    _uniq = {}
    for k, (x, y) in centers.items():
        key = (round(x, 4), round(y, 4))
        if key in _uniq:
            _uniq[key] = (_uniq[key][0] + "/" + k, x, y)
        else:
            _uniq[key] = (k, x, y)
    for k, x, y in _uniq.values():
        cross(x, y, 0.30, "F.Fab")
        dy = -0.45 if y < 0 else 0.45
        w(f'\t(fp_text user "{k}({x:.3f},{y:.3f})" (at {f3(x+0.15)} {f3(y+dy)}) (layer {"F.Fab"}) (effects (font (size 0.35 0.35) (thickness 0.06))))')
    # courtyard
    cx0, cy0, cx1, cy1 = -hx - c["courtyard_excess"], -hy - c["courtyard_excess"], hx + c["courtyard_excess"], hy + c["courtyard_excess"]
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        xs = [cx0, cx1, cx1, cx0]; ys = [cy0, cy0, cy1, cy1]
        w('\t' + line(xs[a], ys[a], xs[b], ys[b], "F.CrtYd", 0.05))
    # 焊盘
    for nm, x, y in pads:
        w(f'\t(pad "{nm}" smd circle (at {f3(x)} {f3(y)}) (size {c["pad_dia"]} {c["pad_dia"]}) '
          f'(layers {lyr("F.Cu")} {lyr("F.Paste")} {lyr("F.Mask")}) (solder_mask_margin {c["mask_margin"]}))')
    w(')')
    kmod = os.path.join(out_dir, f'{c["name"]}.kicad_mod')
    open(kmod, "w", encoding="utf-8").write("\n".join(L) + "\n")

    # CSV
    with open(os.path.join(out_dir, f'{c["name"]}_pads.csv'), "w", newline="", encoding="utf-8-sig") as f:
        cw = csv.writer(f)
        cw.writerow(["Pin", "X_mm", "Y_mm(KiCad,+Y down)", "Note"])
        cw.writerow(["# origin", "0", "0", "body center; +X->last col, +Y->last row (KiCad)"])
        for k, (x, y) in centers.items():
            cw.writerow([f"# {k}_center", f"{x:.3f}", f"{y:.3f}", "relative to body center"])
        for nm, x, y in pads:
            cw.writerow([nm, f"{x:.3f}", f"{y:.3f}", ""])

    # 校对图 HTML
    S = 90
    svg = []
    svg.append(f'<svg viewBox="{-hx*S-390} {-hy*S-150} {A*S+780} {B*S+330}" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family:Segoe UI,sans-serif">')
    svg.append(f'<rect x={-hx*S-390} y={-hy*S-150} width={A*S+780} height={B*S+330} fill="#ffffff"/>')
    svg.append('<g>')
    svg.append(f'<rect x={-hx*S} y={-hy*S} width={A*S} height={B*S} fill="none" stroke="#333" stroke-width="1.5"/>')
    svg.append(f'<rect x={cx0*S} y={cy0*S} width={(cx1-cx0)*S} height={(cy1-cy0)*S} fill="none" stroke="#bbb" stroke-dasharray="6 4" stroke-width="1"/>')
    for nm, x, y in pads:
        svg.append(f'<circle cx={x*S} cy={y*S} r={c["pad_dia"]/2*S} fill="#B5D4F4" stroke="#185FA5" stroke-width="1"/>')
        pin_style=presentation(c)['pin']
        svg.append(f'<text x={x*S} y={y*S} font-size="{pin_style["height"]*S}" fill="#0C447C" text-anchor="middle" dominant-baseline="central">{nm}</text>')
    svg.append('</g>')
    for mark in presentation(c)['annotations']:
        x,y=mark['point']
        r=.12 if mark['name']=='BODY' else .10
        for x0,y0,x1,y1 in [(x-r,y,x+r,y),(x,y-r,x,y+r)]:
            svg.append(f'<line x1="{x0*S}" y1="{-y0*S}" x2="{x1*S}" y2="{-y1*S}" stroke="{mark["color"]}" stroke-width="1" vector-effect="non-scaling-stroke"/>')
        lx,ly=mark['label']
        anchor='end' if mark['justify']=='right' else 'start'
        svg.append(f'<text x="{lx*S}" y="{-ly*S}" text-anchor="{anchor}" font-size="{.18*S}" fill="{mark["color"]}">{mark["text"]}</text>')
        for (x0,y0),(x1,y1) in mark['segments']:
            svg.append(f'<line x1="{x0*S}" y1="{-y0*S}" x2="{x1*S}" y2="{-y1*S}" stroke="{mark["color"]}" stroke-width="1" vector-effect="non-scaling-stroke"/>')
    for y in [-hy-.8,hy+1.0]:
        svg.append(f'<path transform="translate(0 {y*S}) scale({S})" d="{presentation(c)["ref"]["svg_path"]}" fill="none" stroke="#a180a0" stroke-width=".15" stroke-linecap="round" stroke-linejoin="round"/>')
    svg.append('</svg>')
    svg_str = re.sub(r'=(\-?\d+\.?\d*(?:e\-?\d+)?)', lambda m: '="%s"' % m.group(1), ''.join(svg))
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{c["name"]} 校对图</title>
<style>body{{font-family:'Segoe UI',sans-serif;margin:24px;color:#222;background:#fff}} h2{{font-size:16px}} p{{font-size:13px}}</style></head><body>
<h2>{c["name"]} 封装校对图（视图 = 数据手册 Top View）</h2>
<p>原点 = Body 中心。蓝圆 = Ø{c["pad_dia"]} NSMD 焊盘（球 Ø{c["ball_dia"]}，阻焊 Ø{c["pad_dia"]+2*c["mask_margin"]:.2f}）。虚线 = Place Bound / Courtyard（外扩 {c["courtyard_excess"]} mm），器件最大高度 {c.get("height_max","待填写")} mm。REF 线宽 0.15 mm；中心十字线宽 0（屏幕显示为细线）。</p>
{svg_str}
</body></html>"""
    open(os.path.join(out_dir, f'{c["name"]}_preview.html'), "w", encoding="utf-8").write(html)
    return kmod, pads, col_x, row_y


# ===================================================================
# 2) Allegro SKILL (.il) —— 建 padstack + 放置封装
# ===================================================================
# 【重要，2026-10-08 实测结论】不要依赖 padpath！
#
# 曾经的错误做法：.il 里只写 padstack 名字（如 "BALL20"），指望 Allegro 从
# padpath 找到 .pad 文件。实测这在无人值守场景下会**静默失败**（引脚数 0）：
#   * Allegro 读的是 <HOME>/pcbenv/env 里的 `set padpath = ...`，**不是** shell
#     环境变量。若该行是硬编码的单个目录（没有 "." 也没有 $PADPATH），
#     那么在 .scr 里设 PADPATH 完全无效。
#   * axlDBCreatePin/axlLoadPadstack 会**先查 drawing 数据库内已有的 padstack**。
#     空白模板（由别人的 .dra 改来）里往往残留着旧的 padstack（如 BALL25），
#     于是"碰巧"能建出引脚，用错几何也没人发现；换一个名字就 0 引脚。
#
# 正确做法（本脚本采用）：用 axlDBCreatePadStack 把 padstack **直接建在
# drawing 数据库里**，然后把返回的 dbid 交给 axlDBCreatePin。
#   * 完全不查 padpath / 不需要 .pad 文件 / 不需要 Pad Designer；
#   * 几何 100% 来自本次计算，不会继承模板里的旧值；
#   * 建之前先删掉同名旧 padstack，保证结果确定。
#
# Pad Designer 脚本(BALLxx_pad.scr)与 make_pads.bat 仍然生成，但用途变成
# "把物理 .pad 存进你自己的 pad 库"，与生成封装无关。
# ===================================================================
def padstack_name(spec):
    """Avoid board-local legacy BALL20 definitions and encode the full process."""
    import hashlib
    identity = '|'.join(['millimeters/SMD/TOP/no-drill/v2',
                         *(f'{spec[k]:.8f}' for k in ('pad_dia','mask_margin','paste_dia'))])
    return 'SM2_' + hashlib.sha256(identity.encode('ascii')).hexdigest()[:12].upper()


def gen_allegro(cfg, geo, out_dir):
    c = cfg; g = geo
    A, B, hx, hy = g["A"], g["B"], g["hx"], g["hy"]
    PX, PY = g["PX"], g["PY"]
    PAD = c["pad_dia"]; MASK = c["pad_dia"] + 2 * c["mask_margin"]; PASTE = c["paste_dia"]
    name = c["name"]
    ps_name = padstack_name(c)
    pads = g["pads"]                      # 已是 +Y 向上坐标
    f4 = lambda v: f"{v:.4f}"
    adir = os.path.abspath(os.path.join(out_dir, "allegro"))
    adir_win = adir                         # Windows 反斜杠路径
    adir_skill = adir.replace("\\", "/")  # SKILL 接受正斜杠

    # -----------------------------------------------------------------
    # 2a) 生成 Pad Designer 16.6 脚本，用于生成物理 .pad 文件
    # -----------------------------------------------------------------
    scr_lines = [
        "# Pad Designer 16.6 script -- generated by build_footprint.py",
        f"# Run: pad_designer.exe -s {ps_name}_pad.scr  (working dir = this folder)",
        "setwindow form.padedit",
        "pse_new",
        f'fillin "{ps_name}"',
        'FORM padedit units Millimeter',
        'fillin yes',
        'FORM padedit decimal_places 4',
        'FORM padedit single YES',
        'FORM padedit layers',
        # BEGIN LAYER -> TOP (SMD)
        'FORM padedit grid row begin_layer',
        'FORM padedit grid change begin_layer,begin_layer TOP',
        'FORM padedit geometry Circle',
        f'FORM padedit width {f4(PAD)}',
        f'FORM padedit height {f4(PAD)}',
        # SOLDERMASK_TOP
        'FORM padedit grid row SOLDERMASK_TOP',
        'FORM padedit geometry Circle',
        f'FORM padedit width {f4(MASK)}',
        f'FORM padedit height {f4(MASK)}',
        # PASTEMASK_TOP
        'FORM padedit grid row PASTEMASK_TOP',
        'FORM padedit geometry Circle',
        f'FORM padedit width {f4(PASTE)}',
        f'FORM padedit height {f4(PASTE)}',
        # save and exit
        'pse_check',
        'pse_save',
        'pse_exit',
    ]
    scr = "\n".join(scr_lines) + "\n"

    # -----------------------------------------------------------------
    # 2b) 生成一键批处理：自动找 pad_designer.exe 并运行脚本
    # -----------------------------------------------------------------
    # 用 GBK 编码写入，避免中文 Windows cmd 下显示乱码。
    # 路径探测顺序：常见固定路径 -> C/D/E/F 盘 tools\pcb\bin 自动搜索。
    bat_lines = [
        '@echo off',
        'chcp 936 >nul',
        'setlocal enabledelayedexpansion',
        'set "PAD_DIR=%~dp0"',
        'cd /d "%PAD_DIR%"',
        '',
        'REM 常见 Cadence/Allegro 安装路径（按你本机情况修改）：',
        'set "PD=D:\\tools\\pcb\\bin\\pad_designer.exe"',
        'if not exist "%PD%" set "PD=D:\\tools\\bin\\pad_designer.exe"',
        'if not exist "%PD%" set "PD=C:\\Cadence\\SPB_16.6\\tools\\pcb\\bin\\pad_designer.exe"',
        'if not exist "%PD%" set "PD=C:\\Cadence\\SPB_16.6\\tools\\bin\\pad_designer.exe"',
        'if not exist "%PD%" set "PD=C:\\Cadence\\Cadence_SPB_16.6\\tools\\pcb\\bin\\pad_designer.exe"',
        'if not exist "%PD%" set "PD=C:\\Cadence\\Cadence_SPB_16.6\\tools\\bin\\pad_designer.exe"',
        '',
        'REM 若上面都没有，自动搜索 C/D/E/F 盘下 tools\\pcb\\bin\\pad_designer.exe',
        'if not exist "%PD%" (',
        '    for %%D in (C D E F) do (',
        '        if exist "%%D:\\tools\\pcb\\bin\\pad_designer.exe" (',
        '            set "PD=%%D:\\tools\\pcb\\bin\\pad_designer.exe"',
        '            goto :found',
        '        )',
        '        if exist "%%D:\\Cadence\\SPB_16.6\\tools\\pcb\\bin\\pad_designer.exe" (',
        '            set "PD=%%D:\\Cadence\\SPB_16.6\\tools\\pcb\\bin\\pad_designer.exe"',
        '            goto :found',
        '        )',
        '    )',
        ')',
        '',
        ':found',
        'if not exist "%PD%" (',
        '    echo ERROR: 找不到 pad_designer.exe。',
        '    echo.',
        '    echo 请用记事本打开 make_pads.bat，把下面的路径改成你本机的实际路径：',
        '    echo   set "PD=你的路径\\tools\\pcb\\bin\\pad_designer.exe"',
        '    echo.',
        f'    echo 或者手动运行：打开 Pad Designer - File - Script - Replay，选择本目录的 {ps_name}_pad.scr',
        '    pause',
        '    exit /b 1',
        ')',
        '',
        'echo 使用 Pad Designer: %PD%',
        f'"%PD%" -s "{ps_name}_pad.scr"',
        'if errorlevel 1 (',
        '    echo.',
        '    echo ERROR: Pad Designer 运行失败。请把上面的错误信息截图发给我。',
        '    pause',
        '    exit /b 1',
        ')',
        'echo.',
        f'echo 若未报错，{ps_name}.pad 已生成在本目录：%PAD_DIR%',
        'pause',
    ]
    bat = "\n".join(bat_lines) + "\n"

    # -----------------------------------------------------------------
    # 2c) 生成 Allegro Package Symbol SKILL 脚本
    # -----------------------------------------------------------------
    L = []
    a = lambda s="": L.append(s)
    a(f";;====================================================================")
    a(f";;  {name}  package symbol builder  (generated by build_footprint.py)")
    a(f";;  全自动用法：")
    a(f";;      allegro.exe -s gen_{name}.scr -nograph")
    a(f";;  或手工：File>New>Package Symbol(mm) 后执行")
    a(f";;      skill load(\"{adir_skill}/{name}_build.il\")")
    a(f";;  说明：padstack 由本脚本用 axlDBCreatePadStack 直接建在 drawing")
    a(f";;        数据库内，**不依赖 padpath / .pad 文件 / Pad Designer**。")
    a(f";;====================================================================")
    a('(axlDBChangeDesignUnits "millimeters" 4)')
    a('(unless (equal (axlDBGetDesignUnits) (list "millimeters" 4)) (error "Millimeter database setup failed"))')
    a(f';; 提高 drawing 内部精度。空白模板可能只有 2 位精度，会把焊盘尺寸截断到')
    a(f';; 0.01mm（实测阻焊 0.3016 -> 0.30、钢网 0.1730 -> 0.17）。改成 4 位后')
    a(f';; 实测尺寸与坐标 1:1 无误差（x=1.1153 存回来还是 1.1153）。')
    a(';; Coordinates and pad sizes below are explicitly in millimeters.')
    a(';; Only this private copy of the seed is cleared; user boards are never edited.')
    a('(axlVisibleDesign t)')
    a('(axlClearSelSet)')
    a('(axlSetFindFilter ?enabled (list "noall" "alltypes") ?onButtons (list "noall" "alltypes"))')
    a('(axlAddSelectAll)')
    a('(foreach oldObject (axlGetSelSet) (unless (axlDeleteObject oldObject) (error "Seed geometry cleanup failed")))')
    a('(axlClearSelSet)')
    a("")
    a(f";; ---- 1) 在 drawing 内直接建 padstack {ps_name}（不查 padpath） ----")
    a(f";;   TOP(焊盘) Ø{f4(PAD)} / SOLDERMASK_TOP Ø{f4(MASK)} / PASTEMASK_TOP Ø{f4(PASTE)}  单位 mm")
    a(f';;   先清掉 drawing 里没用到的旧 padstack（空白模板从别人的 .dra 继承而来，')
    a(f';;   常残留 VIA_FC / BALL25 之类）。否则同名时 axlDBCreatePadStack 会报')
    a(f';;   SPMHDB-74 "Pad stack already exists" 并返回 nil -> 引脚一个都建不出来。')
    a(f';;   坑：axlDeleteObject 删不掉 padstack（16.6 报 "Cannot delete element type:')
    a(f';;   Pad Stack"），必须用 axlPurgePadstacks。')
    a(f"(axlPurgePadstacks 'padstacks nil)")
    a(f';;   另一个大坑：顶层导体层名不能硬编码成 "TOP"。模板若来自 APD 设计，')
    a(f';;   顶层导体叫 TOP_COND，此时 ?layer "TOP" 会静默建不出铜箔焊盘（实际为')
    a(f';;   NULL，span=0），且阻焊/钢网尺寸也会跟着错。所以一律问 drawing 要。')
    a(f"(setq etch_top (axlConductorTopLayer))")
    a(f'(setq pad_list (list')
    a(f"  (make_axlPadStackPad ?layer etch_top ?type 'REGULAR")
    a(f"    ?figure 'CIRCLE ?figureSize {f4(PAD)}:{f4(PAD)})")
    a(f"  (make_axlPadStackPad ?layer \"SOLDERMASK_TOP\" ?type 'REGULAR")
    a(f"    ?figure 'CIRCLE ?figureSize {f4(MASK)}:{f4(MASK)})")
    a(f"  (make_axlPadStackPad ?layer \"PASTEMASK_TOP\" ?type 'REGULAR")
    a(f"    ?figure 'CIRCLE ?figureSize {f4(PASTE)}:{f4(PASTE)})))")
    a(f'(setq ps_name (axlDBCreatePadStack "{ps_name}" nil pad_list t))')
    a(f'(when (null ps_name)')
    a(f'  ;; 极端兜底：若仍已存在，就退回"按名加载"（几何可能来自模板旧值，会告警）')
    a(f'  (println "WARN: axlDBCreatePadStack returned nil, falling back to axlLoadPadstack")')
    a(f'  (setq ps_name (axlLoadPadstack "{ps_name}")))')
    a(f'(unless ps_name')
    a(f'  (println "ERROR: no padstack {ps_name} available - pins will NOT be created")')
    a(f'  (errset (axlMsgPut "ERROR: no padstack {ps_name} available")))')
    a("")
    # 2) 可复用 pin text defstruct + 放置 41 焊盘
    a(f";; ---- 2) 放置 {len(pads)} 个焊盘 (缺球已跳过) ----")
    style=presentation(c)
    if not isinstance(c.get('height_max'),(int,float)) or c['height_max']<=0:
        raise ValueError('需要器件最大高度 height_max（mm），才能创建正确的 Place Bound')
    a('(setq PIN_TXT_BLOCK "1")')
    a('(setq REF_TXT_BLOCK "2")')
    a('(setq CENTER_TXT_BLOCK "3")')
    for block,settings in [('1',style['pin']),('2',style['ref']),('3',dict(width=.10,height=.18,char_space=.02,stroke=0))]:
        a(f'(setq textParam (axlGetParam "paramTextBlock:{block}"))')
        a('(unless textParam (error "Missing seed text block"))')
        for field,value in [('width',settings['width']),('height',settings['height']),('charSpace',settings['char_space']),
                            ('lineSpace',settings['height']*1.6),('photoWidth',settings['stroke'])]:
            a(f'textParam->{field} = {value:.6f}')
        a('(unless (axlSetParam textParam) (error "Text block update failed"))')
    a("(setq myTextOri (make_axlTextOrientation")
    a("  ?textBlock PIN_TXT_BLOCK ?rotation 0.0 ?justify \"center\" ?mirrored nil))")
    a(';; 注意: ?number 必须在构造 make_axlPinText 时给出, 否则 axlDBCreatePin')
    a(';;       会报 "Invalid Pin Text" 并静默返回 nil(引脚一个都建不出来)。')
    a(';;       因此下面在循环内逐颗构造 myPin, 不要用后置赋值 myPin->number。')
    a("(setq pin_data (list")
    for nm, x, y in pads:
        a(f'  (list "{nm}" {f4(x)} {f4(y)})')
    a("))")
    a("(setq placed 0)")
    a("(foreach p pin_data")
    a(f"  (setq myPin (make_axlPinText ?number (car p) ?offset (list 0.0 {-style['pin']['height']/3:.6f}) ?text myTextOri))")
    a("  (when (errset (axlDBCreatePin ps_name (list (cadr p) (caddr p)) myPin))")
    a("    (setq placed (add1 placed))")
    a("  )")
    a(")")
    a("")
    # 3) 本体外框 (ASSEMBLY + SILK)
    bx0, by0, bx1, by1 = -hx, -hy, hx, hy
    a(f";; ---- 3) 本体轮廓 (ASSEMBLY_TOP + SILKSCREEN_TOP) ----")
    a(f'(setq body_pts (list (list {f4(bx0)} {f4(by0)}) (list {f4(bx1)} {f4(by0)})')
    a(f'                     (list {f4(bx1)} {f4(by1)}) (list {f4(bx0)} {f4(by1)}) (list {f4(bx0)} {f4(by0)})))')
    a(f'(errset (axlDBCreateLine body_pts 0.05 "PACKAGE GEOMETRY/ASSEMBLY_TOP"))')
    a(f'(errset (axlDBCreateLine body_pts 0.15 "PACKAGE GEOMETRY/SILKSCREEN_TOP"))')
    # 4) A1 圆点 + pin1 丝印三角
    a(f";; ---- 4) A1 索引圆点 + pin1 丝印三角 (位于 A1 焊盘左侧, 顶点指向 A1) ----")
    a1x, a1y = g["col_x"][0], g["row_y"][0]
    cx, cy, r = a1x - 0.45, a1y + 0.45, 0.15
    a(f'(errset (axlDBCreateCircle (list {f4(cx)}:{f4(cy)} {f4(r)}) 0.0500 "PACKAGE GEOMETRY/SILKSCREEN_TOP"))')
    tri = [(a1x - 0.35, a1y - 0.16), (a1x - 0.35, a1y + 0.16), (a1x - 0.65, a1y), (a1x - 0.35, a1y - 0.16)]
    a('(setq tri_pts (list ' + ' '.join(f'(list {f4(x)} {f4(y)})' for x, y in tri) + '))')
    a('(errset (axlDBCreateLine tri_pts 0.08 "PACKAGE GEOMETRY/SILKSCREEN_TOP"))')
    # 4.5) REFDES 文字（Allegro Create Symbol 必需）
    a(f";; ---- 4.5) REFDES 文字 (Create Symbol 必需) ----")
    a(f'(unless (axlDBCreateText "#REFDES" (list 0.0 {f4(by1+0.55)})')
    a(f'        (make_axlTextOrientation ?textBlock REF_TXT_BLOCK ?rotation 0.0 ?justify "center") "REF DES/ASSEMBLY_TOP") (error "Assembly REF creation failed"))')
    a(f'(unless (axlDBCreateText "#REFDES" (list 0.0 {f4(-by1-1.15)})')
    a(f'        (make_axlTextOrientation ?textBlock REF_TXT_BLOCK ?rotation 0.0 ?justify "center") "REF DES/SILKSCREEN_TOP") (error "Silkscreen REF creation failed"))')
    a("")
    # 5) place bound
    a(f";; ---- 5) 占位边界 PLACE_BOUND_TOP (本体+{c["courtyard_excess"]} 余量) ----")
    px0, py0, px1, py1 = bx0 - c["courtyard_excess"], by0 - c["courtyard_excess"], \
                         bx1 + c["courtyard_excess"], by1 + c["courtyard_excess"]
    a(f'(setq pb_pts (list (list {f4(px0)} {f4(py0)}) (list {f4(px1)} {f4(py0)})')
    a(f'                   (list {f4(px1)} {f4(py1)}) (list {f4(px0)} {f4(py1)}) (list {f4(px0)} {f4(py0)})))')
    a(f'(setq placeBound (car (axlDBCreateRectangle (list (list {f4(px0)} {f4(py0)}) (list {f4(px1)} {f4(py1)})) t "PACKAGE GEOMETRY/PLACE_BOUND_TOP")))')
    a('(unless placeBound (error "Place Bound shape creation failed"))')
    a(f'(unless (axlDBAddProp (list placeBound) (list (list "PACKAGE_HEIGHT_MAX" "{c["height_max"]:.4f}mm") (list "PACKAGE_HEIGHT_MIN" "{c.get("height_min",0):.4f}mm"))) (error "Place Bound height properties failed"))')
    a("")
    # 6) 三中心十字 + 文字
    a(f";; ---- 6) 三中心十字 + 文字标注 (ASSEMBLY_TOP) ----")
    def cross(cx2, cy2, rr, w):
        a(f'(errset (axlDBCreateLine (list (list {f4(cx2-rr)} {f4(cy2)}) (list {f4(cx2+rr)} {f4(cy2)})) {f4(w)} "PACKAGE GEOMETRY/ASSEMBLY_TOP"))')
        a(f'(errset (axlDBCreateLine (list (list {f4(cx2)} {f4(cy2-rr)}) (list {f4(cx2)} {f4(cy2+rr)})) {f4(w)} "PACKAGE GEOMETRY/ASSEMBLY_TOP"))')
    cross(0.0, 0.0, 0.12, 0)
    bx, by = c["centers"]["BGA"]
    ox, oy = c["centers"]["OPT"]
    cross(bx, by, 0.10, 0)
    if (round(bx, 4), round(by, 4)) != (round(ox, 4), round(oy, 4)):
        cross(ox, oy, 0.10, 0)
    for mark in style['annotations']:
        lx,ly=mark['label']
        a(f'(unless (axlDBCreateText "{mark["text"]}" (list {f4(lx)} {f4(ly)}) (make_axlTextOrientation ?textBlock CENTER_TXT_BLOCK ?rotation 0.0 ?justify "{mark["justify"]}") "PACKAGE GEOMETRY/ASSEMBLY_TOP") (error "Center annotation failed"))')
        for (x0,y0),(x1,y1) in mark['segments']:
            a(f'(unless (axlDBCreateLine (list (list {f4(x0)} {f4(y0)}) (list {f4(x1)} {f4(y1)})) 0.0 "PACKAGE GEOMETRY/ASSEMBLY_TOP") (error "Center leader creation failed"))')
    # 7) done
    a(f";; ---- 7) done ----")
    a(f'(errset (axlMsgPut "{name} build done."))')
    # 注意：本机 Allegro 16.6 的 SKILL 环境里 sprintf / itoa 均不可用，
    # 改用基础 println（直接打印字符串与整数），保证 load 干净退出。
    a(f'(println "{name}_BUILD_DONE")')
    a(f'(println placed)')
    il = "\n".join(L) + "\n"

    adir = os.path.join(out_dir, "allegro")
    os.makedirs(adir, exist_ok=True)
    out = os.path.join(adir, f"{name}_build.il")
    open(out, "w", encoding="utf-8").write(il)
    open(os.path.join(adir, f"{ps_name}_pad.scr"), "w", encoding="utf-8").write(scr)
    # bat 用 GBK，中文 Windows cmd 默认代码页才能正确显示中文提示
    open(os.path.join(adir, "make_pads.bat"), "w", encoding="gbk").write(bat)

    # -----------------------------------------------------------------
    # 2d) 全自动批处理入口 gen_<name>.scr
    #     用法:  <dir> 下执行   allegro.exe -s gen_<name>.scr -nograph
    #
    #     关键点：Allegro 冷启动(-nograph 无参数)建的是 **board** drawing，
    #     此时 axlSetSymbolType / axlDBCreatePin 都会报
    #     "Procedure can only be applied to symbol drawings"。
    #     所以必须**先打开一个已有的 Package Symbol drawing 借壳进入
    #     symbol 编辑态**，再 load .il。这里用 _seed_blank.dra。
    #
    #     另注：不要用 newdrawfillin "<x>.dra" "Package Symbol" —— 它是纯
    #     GUI 表单命令，在 -nograph 下没有表单可等，会永久挂起。
    # -----------------------------------------------------------------
    seed = "_seed_blank.dra"
    # 空白模板查找：按顺序在多个候选位置找，避免"换台机器/换个输出目录就悄悄
    # 丢模板"的情况。模板缺失时 gen_*.scr 打开不了 seed，Allegro 那步会失败，
    # 所以下面找不到会明确告警而不是静默 pass。
    _here = os.path.dirname(os.path.abspath(__file__))
    _outp = os.path.dirname(os.path.dirname(adir))      # out_dir 的上级
    _cands = [
        os.path.join(_here, "blank_symbol.dra"),
        os.path.join(_outp, "_templates", "blank_symbol.dra"),
        os.path.join(_outp, "05_模板", "blank_symbol.dra"),
        os.path.join(_outp, "05_模板", "blank_symbol.dra.标准层TOP-BOTTOM.可用"),
        os.path.join(_here, "_templates", "blank_symbol.dra"),
        os.path.join(os.path.dirname(_here), "_templates", "blank_symbol.dra"),
        os.path.join(os.path.dirname(_here), "05_模板", "blank_symbol.dra"),
        os.environ.get("FOOTPRINT_BLANK_TPL", ""),
    ]
    tpl = next((c for c in _cands if c and os.path.isfile(c)), None)
    if tpl:
        try:
            import shutil
            shutil.copyfile(tpl, os.path.join(adir, seed))
        except Exception as e:
            print(f"  [警告] 复制空白模板失败: {e}")
    else:
        print("  [警告] 找不到空白模板 blank_symbol.dra（_templates/ 或 05_模板/），")
        print("         allegro/_seed_blank.dra 未生成 -> Allegro 那步会失败。")
        print("         可从 05_模板 拷一份，或设环境变量 FOOTPRINT_BLANK_TPL=<路径>。")

    scr_lines2 = [
        "scriptmode +invisible +noinfo",
        "skill '(axlSetVariable \"NOCONFIRM\" t)'",
        f"skill '(errset (axlOpenDesign ?design \"{seed}\" ?mode \"wf\" ?noMru t))'",
        "skill '(errset (axlSetSymbolType \"package\"))'",
        "skill '(axlDBChangeDesignUnits \"millimeters\" 4)'",
        "skill '(unless (equal (axlDBGetDesignUnits) (list \"millimeters\" 4)) (error \"Millimeter database setup failed\"))'",
        # 路径必须是 Windows 形式（Allegro 读不了 /e/... 这种 Git-Bash 路径）
        # 用**相对路径**载入 build.il：Allegro 的 cwd 就是 .scr 所在目录，
        # 已实测可用。这样整个 allegro/ 目录可以整体拷到任意机器/任意盘符，
        # 不必改脚本里的绝对路径（迁移友好）。
        f"skill '(load \"{name}_build.il\")'",
        f"skill '(let ((d (axlDBGetDesign)) (p (outfile \"res_{name}.txt\"))) "
        f"(fprintf p \"PINS=%L\\n\" (length (d->pins))) (close p))'",
        f"skill '(let ((p (outfile \"res2_{name}.txt\"))) "
        f"(fprintf p \"COMPILE=%L\\nSAVE=%L\\n\" "
        f"(errset (axlCompileSymbol ?symbol \"{name}\" ?silent t ?silentOnOverwrite t) t) "
        f"(errset (axlSaveDesign ?design \"{name}.dra\" ?mode \"nocheck\" ?noMru t ?noConfirm t) t)) "
        f"(close p))'",
        "exit",
    ]
    open(os.path.join(adir, f"gen_{name}.scr"), "w", encoding="utf-8").write(
        "\n".join(scr_lines2) + "\n")
    return out, len(pads), adir


# ===================================================================
# 3) 可选：用 KiCad 自带 pcbnew 验证 .kicad_mod
# ===================================================================
def validate_kicad(kmod_path, expect_pads):
    candidates = [
        r"C:\Program Files\KiCad\6.0\bin\python.exe",
        r"C:\Program Files\KiCad\7.0\bin\python.exe",
        r"C:\Program Files\KiCad\8.0\bin\python.exe",
        r"C:\Program Files\KiCad\9.0\bin\python.exe",
    ]
    py = next((p for p in candidates if os.path.exists(p)), None)
    if not py:
        return "SKIP (KiCad python 未找到，跳过自动校验；请用 KiCad PCB Editor 打开核对)"
    filedir = os.path.dirname(kmod_path)
    filestem = os.path.splitext(os.path.basename(kmod_path))[0]
    code = (
        "import pcbnew,sys\n"
        f"fp=pcbnew.FootprintLoad(r'{filedir}', r'{filestem}')\n"
        "n=len(fp.Pads())\n"
        "print('KICAD_OK pads='+str(n))\n"
        f"sys.exit(0 if n=={expect_pads} else 1)"
    )
    try:
        r = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return r.stdout.strip() or f"KICAD_OK pads={expect_pads}"
        return f"FAIL: {r.stderr.strip()[:300]}"
    except Exception as ex:
        return f"SKIP (校验异常: {ex})"


# ===================================================================
# main
# ===================================================================
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", help="外部 JSON 配置（覆盖嵌入 CONFIG）")
    ap.add_argument("--out", help="输出目录（默认脚本同目录下的 <name> 文件夹）")
    ap.add_argument("--kicad", type=int, default=None, help="KiCad 大版本 6/7/8/9")
    args = ap.parse_args()

    cfg = load_spec(args.spec) if args.spec else dict(CONFIG)
    if args.kicad:
        cfg["kicad_version"] = args.kicad
    if args.out:
        out_dir = args.out
    else:
        out_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)

    geo = compute(cfg)
    kmod, pads, col_x, row_y = gen_kicad(cfg, geo, out_dir)
    il, npads_exp, adir_out = gen_allegro(cfg, geo, out_dir)
    a1 = next(p for p in pads if p[0] == "A1")
    # 取一个能代表末端焊盘的引脚名：优先 F7，否则用最后一行最后一列
    f7 = next((p for p in pads if p[0] == "F7"), None)
    if f7 is None:
        end_pin = pads[-1]
        f7_txt = f"{end_pin[0]}=({end_pin[1]:.3f},{end_pin[2]:.3f})"
    else:
        f7_txt = f"F7=({f7[1]:.3f},{f7[2]:.3f})"

    print("=" * 60)
    print(f"封装: {cfg['name']}  ({len(pads)} 焊盘, 缺球 {sorted(set(cfg['missing']))})")
    print(f"本体: {geo['A']} x {geo['B']} mm   间距: {geo['PX']}/{geo['PY']} mm")
    print(f"阵列中心: ({geo['arr_c'][0]:.3f}, {geo['arr_c'][1]:.3f})  (应=BGA中心)")
    print(f"A1=({a1[1]:.3f},{a1[2]:.3f})  {f7_txt}  [KiCad +Y down]")
    print("-" * 60)
    print(f"[1] KiCad    : {kmod}")
    print(f"[2] CSV      : {os.path.join(out_dir, cfg['name']+'_pads.csv')}")
    print(f"[3] 校对图   : {os.path.join(out_dir, cfg['name']+'_preview.html')}")
    print(f"[4] Allegro  : {il}")
    print("-" * 60)
    print("KiCad 校验:", validate_kicad(kmod, len(pads)))
    print("-" * 60)
    print("Allegro 封装生成（全自动，无需点鼠标）:")
    ps_name2 = f"BALL{int(round(cfg['pad_dia']*100)):02d}"
    print(f'  cd "{adir_out}"')
    print(f'  D:\\tools\\pcb\\bin\\allegro.exe -s gen_{cfg["name"].split("_")[0]}.scr -nograph')
    print(f'  -> 产出 {cfg["name"].split("_")[0]}.dra + {cfg["name"].split("_")[0]}.psm'
          f' (期望 {npads_exp} 个引脚)')
    print(f'  自检: 看 res_{cfg["name"].split("_")[0]}.txt 里 PINS 是否 = {npads_exp}')
    print(f'  padstack {ps_name2} 由 .il 直接建在 drawing 内，不需要 padpath / .pad 文件。')
    print(f'  （{ps_name2}_pad.scr / make_pads.bat 仍会生成，仅用于把物理 .pad')
    print(f'    存进你自己的 pad 库，与生成封装无关。）')
    print("=" * 60)


if __name__ == "__main__":
    main()
