# -*- coding: utf-8 -*-
# =============================================================================
#  gen_sensor_symbol.py — 通用 OrCAD 原理图符号生成器（填表式模板）
# -----------------------------------------------------------------------------
#  适用对象：所有按"球位(Ball Map)"布局的器件 ——
#            CSP / BGA / LGA / QFN 等阵列封装，以及任何需在符号四周按功能
#            分组摆引脚的 IC。
#
#  用法（只改底部 CONFIG，不碰上方通用逻辑）：
#    python gen_sensor_symbol.py            # 产出 create_<device>.tcl + <device>_ballmap.csv
#    再按 templates/README.md 跑 enlarge_olb.py + tclsh84 生成 .OLB
#
#  本文件可独立运行（用内置 demo），也可被 import：
#    import gen_sensor_symbol as G
#    G.build(你的_CONFIG)                   # 任何器件 = 一份纯数据 CONFIG
#
#  ★ 四条硬规则（模板已内置，勿删）：
#   R1  同名 PWR/GND/NC 自动加 _1.._N 数字后缀 —— Capture 会合并同名网络，
#       多路同名电源/地/NC 必须区分，否则网表错连。
#   R2  所有坐标须为 10 MIL 整数倍（W/H/PITCH/GAP 都要 10 倍数）—— 格点对齐。
#   R3  PCB Footprint 写到 PACKAGE 级（$pkg SetPCBFootprint），不是 part 级；
#       漏写会报 ORCAP-36002 中止网表。
#   R4  借外部矩形外框（src_lib/src_part）+ 生成前自动备份旧 OLB（防覆盖丢 part）。
#
#  布局（layout_style 决定，二选一）：
#   - "grouped"    ：按 TOP/BOT/LEFT/RIGHT 的"分组"依次摆放，组间留 GAP 空槽。
#                    适合电压域分段、功能簇分隔（SENSOR 类推荐）。
#   - "continuous" ：把 TOP/BOT/LEFT/RIGHT 各自当一条连续引脚带，组间不留空槽。
#                    适合紧凑截图风格。
#  无论哪种，摆位与"同名后缀编号顺序"都由 TOP/BOT/LEFT/RIGHT 的配置列表顺序决定。
# =============================================================================

# ============================ CONFIG（改这里） ============================
# ↓↓↓ 下面这份是小 demo（2 行 × 7 列 = 14 球），跑通后整段替换为你的器件数据。
#    真实示例见 examples/GC4693/gen_sensor_symbol_GC4693.py（GC4693 作为纯数据驱动本模板）。
CONFIG = {
    # ---- 基本属性 ----
    "device":        "EXAMPLE_SENSOR",      # 器件名 / part 名前缀
    "part_suffix":   "Normal",              # part 后缀（OrCAD 默认 Normal）
    "out_lib":       "EXAMPLE_SENSOR.OLB",  # 输出 .OLB 文件名
    "pcb_footprint": "EXAMPLE_PKG",         # PCB Footprint（写到 PACKAGE 级! 见 R3）
    "ref_des":       "U",                   # 位号前缀

    # ---- 借外框来源（库里需有这个 part 的矩形符号）----
    "src_lib":  "D:/tools/capture/library/MiscLinear.olb",
    "src_part": "LM555",                    # 借它的矩形外框，enlarge_olb.py 再放大到目标尺寸

    # ---- OrCAD 环境（换机按 01-环境配置.md 改）----
    "dll_path": "D:/tools/capture/orDb_Dll_Tcl",  # orDb_Dll_Tcl.dll 路径（不含扩展名）
    "tcl_pkg":  "DboTclWriteBasic",                 # load 的 Tcl 包名

    # ---- 布局风格 ----
    "layout_style": "grouped",              # "grouped" | "continuous"

    # ---- 球位表 MASTER：ball -> (信号名, 类型) ----
    #   ball：球位号。阵列封装用 A1/B2..；非阵列(纯数字脚号)用 1/2..
    #   name：引脚名（同名 PWR/GND/NC 会按 R1 自动加 _N）
    #   type：PWR | GND | NC | IN | OUT | IO | ANA
    "MASTER": {
        'A1': ('DVDD',  'PWR'), 'A2': ('DGND',  'GND'), 'A3': ('SCL',   'IN'),
        'A4': ('SDA',   'IO'),  'A5': ('RESET', 'IN'),  'A6': ('CLKP',  'OUT'),
        'A7': ('CLKN',  'OUT'), 'B1': ('AVDD',  'PWR'), 'B2': ('AGND',  'GND'),
        'B3': ('DOUT0', 'OUT'), 'B4': ('DOUT1', 'OUT'), 'B5': ('NC',    'NC'),
        'B6': ('NC',    'NC'),  'B7': ('TEST',  'IN'),
    },

    # ---- 功能分组：决定"摆位顺序" + "同名后缀编号顺序" ----
    #   元组 (分组标签, [ball, ...])。列表顺序即摆放/编号顺序；
    #   第一个同名也要带 _1（不是裸名）；顺序：TOP 左→右 / BOT 左→右 /
    #   LEFT 上→下 / RIGHT 上→下。
    "TOP": [
        ('DVDD', ['A1']),
        ('AVDD', ['B1']),
    ],
    "BOT": [
        ('DGND', ['A2']),
        ('AGND', ['B2']),
        ('NC',   ['B5', 'B6']),
    ],
    "LEFT": [
        ('SIG', ['A3', 'A4', 'A5', 'B7']),          # SCL SDA RESET TEST
    ],
    "RIGHT": [
        ('MIPI', ['A6', 'A7', 'B3', 'B4']),         # CLKP CLKN DOUT0 DOUT1
    ],

    # ---- 几何 (MIL；全部 10 整数倍；引脚名较长时 PITCH 取 20) ----
    "W": 200, "H": 300,
    "Y0": 60,                   # 左右列起始 y（顶/底净空 >=60 防名重叠）
    "PITCH": 20,                # 引脚间距（=格点）。长名需 20
    "GAP": 1,                   # 组间空槽 = GAP*PITCH（仅 grouped 风格用）
    "REF_POS": (100, 150),      # Part Reference 显示位置（体内空白中心）
    "VAL_POS": (100, 175),      # Value 显示位置

    # ---- 可选：剔除某些球（板上无焊盘 / 不引出）----
    #   若某球在 PCB 封装上没有焊盘，网表会 SPCODD-409，在此列出即可剔除。
    "DROP_BALLS": set(),        # 例: {'B5','B6'} 去掉某两个球
    "DROP_NC":     False,       # True = 自动剔除 MASTER 中所有 type==NC 的球
}

# ====================== 以上为配置，以下为通用逻辑 ======================
import csv
import os
import sys
from collections import Counter


def tcl_quote(value):
    """A single Tcl word, with substitutions disabled by escaping."""
    value = str(value)
    for a, b in [('\\', '\\\\'), ('"', '\\"'), ('$', '\\$'), ('[', '\\['), (']', '\\]'), ('\n', '\\n'), ('\r', '\\r'), ('\t', '\\t')]:
        value = value.replace(a, b)
    return '"' + value + '"'


def build(config, output_dir='.', dry_run=False):
    """通用生成器：吃一份 CONFIG，产出 golden CSV + create_<device>.tcl。"""
    D = config
    DEV = D["device"]
    MASTER = D["MASTER"]
    TOP, BOT, LEFT, RIGHT = D["TOP"], D["BOT"], D["LEFT"], D["RIGHT"]
    PITCH, GAP = D["PITCH"], D["GAP"]
    W, H, Y0 = D["W"], D["H"], D["Y0"]
    GROUPED = (D.get("layout_style", "grouped") == "grouped")

    # --- 一致性自检：MASTER 与 四个分组必须完全覆盖、不重不漏 ---
    group_balls = [b for g in TOP + BOT + LEFT + RIGHT for b in g[1]]
    assert len(MASTER) == len(group_balls), \
        f"MASTER {len(MASTER)} 与 分组总球数 {len(group_balls)} 不一致"
    assert len(set(group_balls)) == len(MASTER) and set(group_balls) == set(MASTER), "分组中存在重复 ball 或漏球"

    def flatten(groups):
        out = []
        for _, bs in groups:
            out.extend(bs)
        return out

    LAYOUT_ORDER = flatten(TOP) + flatten(BOT) + flatten(LEFT) + flatten(RIGHT)
    assert len(LAYOUT_ORDER) == len(MASTER) and len(set(LAYOUT_ORDER)) == len(MASTER), \
        "LAYOUT_ORDER 必须覆盖全部 ball 且不重复"

    # --- R1：同名 PWR/GND/NC 自动加 _1.._N 后缀 ---
    _base_cnt = Counter()
    for ball in LAYOUT_ORDER:
        base, cat = MASTER[ball]
        _base_cnt[base] += 1
    suffix_counters = {}
    NAME = {}
    for ball in LAYOUT_ORDER:
        base, cat = MASTER[ball]
        if _base_cnt[base] >= 2:
            c = suffix_counters.get(base, 0)
            suffix_counters[base] = c + 1
            NAME[ball] = f"{base}_{c + 1}"
        else:
            NAME[ball] = base

    TYPE_INT = {'PWR': 7, 'GND': 7, 'NC': 7, 'IN': 0, 'OUT': 2, 'IO': 3, 'ANA': 3}
    if len(set(NAME.values())) != len(NAME):
        raise ValueError('添加后缀后名称仍有冲突，请修改重复名称')
    if PITCH < 10 or PITCH % 10 or any(v <= 0 or v % 10 for v in (W, H)):
        raise ValueError('间距和外框尺寸必须是正的 10 MIL 整数倍')

    def span_of(groups, grouped):
        n = sum(len(g[1]) for g in groups)
        if grouped and len(groups) > 1:
            return (n - 1) * PITCH + (len(groups) - 1) * GAP * PITCH
        return max(0, n - 1) * PITCH

    def place_x_groups(groups, y_edge, hot_dir, x_start):
        res = []; x = x_start
        for g in groups:
            for ball in g[1]:
                res.append((ball, x, y_edge, x, y_edge + hot_dir * 30)); x += PITCH
            x += GAP * PITCH
        return res

    def place_y_groups(groups, x_edge, hot_dir, y_start):
        res = []; y = y_start
        for g in groups:
            for ball in g[1]:
                res.append((ball, x_edge, y, x_edge + hot_dir * 30, y)); y += PITCH
            y += GAP * PITCH
        return res

    def place_x_line(balls, y_edge, hot_dir, x_start):
        res = []; x = x_start
        for ball in balls:
            res.append((ball, x, y_edge, x, y_edge + hot_dir * 30)); x += PITCH
        return res

    def place_y_line(balls, x_edge, hot_dir, y_start):
        res = []; y = y_start
        for ball in balls:
            res.append((ball, x_edge, y, x_edge + hot_dir * 30, y)); y += PITCH
        return res

    # --- 布局：分组或连续，由 layout_style 决定 ---
    top_span = span_of(TOP, GROUPED)
    bot_span = span_of(BOT, GROUPED)
    left_span = span_of(LEFT, GROUPED)
    right_span = span_of(RIGHT, GROUPED)
    top_x0 = ((W - top_span) // (2 * PITCH)) * PITCH
    bot_x0 = ((W - bot_span) // (2 * PITCH)) * PITCH
    left_y0 = ((H - left_span) // (2 * PITCH)) * PITCH
    right_y0 = ((H - right_span) // (2 * PITCH)) * PITCH
    if min(left_y0, right_y0) < Y0 or max(left_y0 + left_span, right_y0 + right_span) > H - Y0:
        raise ValueError('左右引脚超出上下净空，请增大外框高度')
    if min(top_x0, bot_x0) < 60 or max(top_x0 + top_span, bot_x0 + bot_span) > W - 60:
        raise ValueError('上下引脚超出左右净空，请增大外框宽度')

    if GROUPED:
        placed = (place_x_groups(TOP, 0, -1, top_x0)
                  + place_x_groups(BOT, H, 1, bot_x0)
                  + place_y_groups(LEFT, 0, -1, left_y0)
                  + place_y_groups(RIGHT, W, 1, right_y0))
    else:
        placed = (place_x_line(flatten(TOP), 0, -1, top_x0)
                  + place_x_line(flatten(BOT), H, 1, bot_x0)
                  + place_y_line(flatten(LEFT), 0, -1, left_y0)
                  + place_y_line(flatten(RIGHT), W, 1, right_y0))

    pins = []
    for ball, sx, sy, hx, hy in placed:
        base, cat = MASTER[ball]
        pins.append((ball, NAME[ball], TYPE_INT[cat], sx, sy, hx, hy))
    for p in pins:
        for v in p[3:]:
            assert v % 10 == 0, f"非10倍数坐标: {p} (所有坐标须为 10 整数倍)"

    # --- 可选剔除球 ---
    drop = set(D.get("DROP_BALLS", set()))
    if D.get("DROP_NC", False):
        drop |= {b for b in LAYOUT_ORDER if MASTER[b][1] == 'NC'}
    dropped = [b for b in drop if b in MASTER]
    pins = [p for p in pins if p[0] not in drop]
    if dry_run:
        return pins
    os.makedirs(output_dir, exist_ok=True)

    # --- 黄金对照表 CSV ---
    gold_csv = os.path.join(output_dir, f"{DEV}_ballmap.csv")
    with open(gold_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['ball', 'name', 'type'])
        if dropped:
            w.writerow([f'# dropped (no pad on board / not routed): {",".join(sorted(dropped))}'])
        for ball, name, ti, sx, sy, hx, hy in pins:
            w.writerow([ball, name, MASTER[ball][1]])
    print(f'[1/2] golden CSV 写出: {gold_csv}  (行数 {len(pins)})')

    # --- 生成 Tcl ---
    lines = []
    A = lines.append
    A(f'# {DEV} 原理图符号生成 (通用模板 v6: 借外框 + 布局净空 + 显示属性定位)')
    A('package require Tcl 8.4')
    A(f'load {tcl_quote(D["dll_path"])} {tcl_quote(D["tcl_pkg"])}')
    A('proc str {s} { return [DboTclHelper_sMakeCString $s] }')
    A('proc pt {x y} { return [DboTclHelper_sMakeCPoint $x $y] }')
    A('proc sval {cs} { return [DboTclHelper_sGetConstCharPtr $cs] }')
    A('')
    A('set s [DboTclHelper_sCreateSession]')
    A('set st [DboState]')
    A(f'set OUT_LIB {tcl_quote(D["out_lib"])}')
    A(f'set PKGNAME {tcl_quote(DEV)}')
    A(f'set PARTNAME {tcl_quote(DEV + "." + D["part_suffix"])}')
    A('')
    A('# 0) 备份已存在的库，防 CreateLib 覆盖整个 OLB 导致其他 part 丢失')
    A('if {[file exists $OUT_LIB]} {')
    A('  error "Output already exists; use a fresh build directory"')
    A('}')
    A('')
    A('# 1) 空库')
    A('set lib [$s CreateLib [str $OUT_LIB] $st]')
    A('# 2) 借外框 -> enlarge_olb.py 用 olefile patch 到目标尺寸')
    A(f'set libSrc [$s GetLib [str {tcl_quote(D["src_lib"])}] $st]')
    A(f'set pkgSrc [$libSrc GetPackage [str {tcl_quote(D["src_part"])}] $st]')
    A('set pkg [$lib CopyPackageAll $pkgSrc [str $PKGNAME] $st]')
    A('set part [$lib GetPart [str $PARTNAME] $st]')
    A('$part RemoveSymbolPins')
    A('set cell [$lib GetCell [str $PKGNAME] $st]')
    A('# R3: PCB Footprint 写到 PACKAGE 级（漏写会 ORCAP-36002 中止网表）')
    A(f'$pkg SetPCBFootprint [str {tcl_quote(D["pcb_footprint"])}]')
    A('# 删除 CopyPackageAll 带来的【全部】继承 device')
    A('set positions {}')
    A('set dit0 [$pkg NewDevicesIter $st]')
    A('for {set i 0} {$i < 30} {incr i} {')
    A('  set sd0 [DboState]; set d [$dit0 NextDevice $sd0]')
    A('  if {[$sd0 Failed]} break')
    A('  set dsp [DboState]; set pos [$d GetPosition $dsp]')
    A('  lappend positions $pos')
    A('}')
    A('foreach pos $positions { catch {$pkg DeleteDevice $pos} }')
    A('puts "deleted [llength $positions] legacy device(s)"')
    A('# 新建【空 designator】device')
    A('set dev [$pkg NewDevice [str ""] 0 $cell $st]')
    A('# 清继承的管脚号表（源 part 自带）')
    A('for {set k 0} {$k < 200} {incr k} {')
    A('  set cs [DboTclHelper_sMakeCString ""]')
    A('  set rr [$dev GetPinNumber $k $cs]')
    A('  if {[$rr Failed]} break')
    A('  catch {$dev DeletePinNumber [DboTclHelper_sGetConstCharPtr $cs]}')
    A('}')
    A('')
    A('# 3) 加引脚（顺序即 slot index）')
    A('set idx 0')
    for ball, name, ti, sx, sy, hx, hy in pins:
        A(f'$part NewSymbolPinScalar $st [str {tcl_quote(name)}] {ti} [pt {sx} {sy}] [pt {hx} {hy}] 1 $idx')
        A(f'$dev NewPinNumber [str {tcl_quote(ball)}] [DboTclHelper_sMakeInt $idx]')
        A('incr idx')
    A('')
    A('# 4) 属性 + Reference/Value 定位到体内空白中心（避免压住引脚名）')
    A(f'$part SetReference [str {tcl_quote(D["ref_des"])}]')
    A(f'$part SetPartValue [str {tcl_quote(DEV)}]')
    A('catch {$part SetPinNumbersAreVisible 1}')
    A('set dit [$part NewDisplayPropsIter $st]')
    A('for {set i 0} {$i < 10} {incr i} {')
    A('  set sd [DboState]; set dp [$dit NextProp $sd]')
    A('  if {[$sd Failed]} break')
    A('  set pn [DboTclHelper_sMakeCString ""]; catch {$dp GetName $pn}')
    A('  set pname [sval $pn]')
    A(f'  if {{$pname eq "Part Reference"}} {{ catch {{$dp SetLocation [pt {D["REF_POS"][0]} {D["REF_POS"][1]}]}} }}')
    A(f'  if {{$pname eq "Value"}}          {{ catch {{$dp SetLocation [pt {D["VAL_POS"][0]} {D["VAL_POS"][1]}]}} }}')
    A('}')
    A('$lib ExplicitlyAddPackageDirName $PKGNAME')
    A('$lib ExplicitlyAddCellDirName    $PKGNAME')
    A('$lib ExplicitlyAddPartDirName    $PARTNAME')
    A('$lib SavePart $part; $lib SaveCell $cell; $lib SavePackage $pkg')
    A('$s MarkAllLibForSave $lib')
    A('set sv [$s SaveLib $lib]')
    A('puts "SaveLib -> $sv ; pins=$idx"')
    A('DboTclHelper_sDeleteSession $s')
    A('puts "BUILD_COMPLETE"')

    create_tcl = os.path.join(output_dir, f"create_{DEV}.tcl")
    with open(create_tcl, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[2/2] tcl 写出: {create_tcl}')

    # --- 运行摘要 ---
    print('类型分布:', dict(Counter(MASTER[b][1] for b in MASTER)))
    print(f'顶排 {len(flatten(TOP))} / 底排 {len(flatten(BOT))} / '
          f'左列 {len(flatten(LEFT))} / 右列 {len(flatten(RIGHT))}'
          + (f'  (已剔除 {sorted(dropped)})' if dropped else ''))
    print('WxH =', W, 'x', H, ' Y0 =', Y0, ' PITCH =', PITCH, ' layout =',
          'grouped' if GROUPED else 'continuous')
    # 打印每个分组的后缀效果（验证 R1）
    for side, groups in (('TOP', TOP), ('BOT', BOT), ('LEFT', LEFT), ('RIGHT', RIGHT)):
        for label, balls in groups:
            names = [NAME[b] for b in balls]
            print(f'  {side:5s} {label:8s} -> {names}')
    print(f'下一步: 运行 enlarge_olb.py {D["out_lib"]} {DEV} {W} {H}, '
          f'再用 tclsh84 跑 {create_tcl}')
    return create_tcl, gold_csv


if __name__ == "__main__":
    build(CONFIG)
