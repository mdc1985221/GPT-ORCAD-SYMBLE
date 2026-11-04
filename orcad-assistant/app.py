"""OrCAD 符号助手 — local desktop application."""
import argparse
import copy
import json
import os
import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import assistant_core as core
import build_pipeline

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
RES = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
STATE = BASE / 'workspace'
BLUE, INK, MUTED, BG = '#2563eb', '#1e293b', '#64748b', '#f1f5f9'


class Assistant(tk.Tk):
    def __init__(self, project_path=None, demo=False):
        super().__init__()
        self.title('OrCAD 符号助手 · 从规格书到可用符号')
        self.geometry('1280x850')
        self.minsize(1080, 720)
        self.configure(bg=BG)
        self.project = core.new_project()
        self.project_path = None
        self.history = []
        self.events = queue.Queue()
        self.busy = False
        self.selected = None
        self.active_part = 'A'
        self.issue_records = []
        self.drawn_pins = {}
        self.preview_zoom = 1.0
        self.preview_offset = (0.0, 0.0)
        self.env = core.DEFAULT_ENV.copy()
        try:
            self.env.update(json.loads((STATE / 'environment.json').read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        self.device = tk.StringVar()
        self.footprint = tk.StringVar()
        self.expected = tk.StringVar()
        self.profile = tk.StringVar(value='SENSOR 功能分组')
        self.only_issues = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='先导入资料，也可以打开示例体验完整流程')
        self.source_text = tk.StringVar(value='点击导入 PDF / CSV；截图可用于调整当前 PART')
        self.summary = tk.StringVar(value='还没有引脚')
        self._build_ui()
        for variable in (self.device, self.footprint, self.expected):
            variable.trace_add('write', self.metadata_changed)
        self.protocol('WM_DELETE_WINDOW', self.close_app)
        self.bind('<Control-s>', lambda e: self.save())
        self.bind('<Control-z>', lambda e: self.undo())
        self.after(100, self.poll)
        # Do not subclass Tk's native window procedure: focus/window switching
        # must remain owned by Tk. File selection remains available in the sidebar.
        if project_path:
            self.open_project(project_path)
        elif demo:
            self.load_demo()
        self.refresh()

    def _build_ui(self):
        from modern_ui import build_ui
        build_ui(self)

    def snapshot(self):
        self.history.append(copy.deepcopy(self.project))
        self.history = self.history[-30:]

    def changed(self):
        self.project['generated'] = None
        try:
            core.atomic_json(STATE / 'last-session.json', self.project)
            self.status.set('修改已自动保存')
        except OSError as exc:
            self.status.set('自动保存失败，请另存项目：' + str(exc))
        self.refresh()

    def metadata_changed(self, *args):
        if getattr(self, '_loading', False) or self.busy:
            return
        self.project['device'] = self.device.get().strip()
        self.project['footprint'] = self.footprint.get().strip()
        value = self.expected.get().strip()
        self.project['expected_count'] = int(value) if value.isdigit() and int(value) > 0 else None
        if value and (not value.isdigit() or int(value) <= 0):
            self.status.set('预期脚数请输入正整数，或留空')
            self.build_button.configure(state='disabled')
            return
        self.changed()

    def sync_fields(self):
        self._loading = True
        self.device.set(self.project['device'])
        self.footprint.set(self.project['footprint'])
        self.expected.set(str(self.project.get('expected_count') or ''))
        self.profile.set('SENSOR 功能分组' if self.project['profile'] == 'sensor' else '普通 IC · 逆时针')
        self.source_text.set(' · '.join(Path(s['path']).name for s in self.project.get('sources', [])) or '点击导入 PDF / CSV；截图可用于调整当前 PART')
        self._loading = False

    def refresh(self):
        if not hasattr(self, 'tree'):
            return
        pending = core.issues(self.project)
        choices = core.part_ids(self.project)
        if self.active_part not in choices:
            self.active_part = choices[0]
        counts = {key:sum(p.get('part','A')==key for p in self.project['pins']) for key in choices}
        labels = [f'{key} · {self.project.get("parts",{}).get(key,"单元")} ({counts[key]})' for key in choices]
        self.part_selector.configure(values=labels)
        self.part_choice.set(labels[choices.index(self.active_part)])
        bad = {x['pin'] for x in pending if x['pin']}
        self.tree.delete(*self.tree.get_children())
        for i, pin in enumerate(self.project['pins']):
            if pin.get('part','A') != self.active_part:
                continue
            if self.only_issues.get() and pin['id'] not in bad:
                continue
            self.tree.insert('', 'end', iid=str(i), values=(pin['id'], pin['name'], pin['type'] or '待定', core.SIDE_LABELS.get(pin['side'], '待定')), tags=('issue',) if pin['id'] in bad else ())
        self.summary.set(f'{counts[self.active_part]} / 共 {len(self.project["pins"])} 脚')
        self.issue_records = pending
        self.issue_list.delete(0, 'end')
        for issue in pending:
            self.issue_list.insert('end', ('需修正 · ' if issue['blocking'] else '需确认 · ') + issue['text'])
        self.review_summary.set(f'还有 {len(pending)} 项待核对 · 在「来源与核对」查看' if pending else '当前检查通过 · 可以生成并验证')
        if not self.project['pins']:
            self.review_summary.set('先导入资料或打开示例，系统会自动生成默认布局')
        expected_text = self.expected.get().strip()
        invalid_count = bool(expected_text and (not expected_text.isdigit() or int(expected_text) <= 0))
        self.build_button.configure(state='disabled' if self.busy or pending or invalid_count or not self.project['device'] or not self.project['footprint'] else 'normal')
        self.output_button.configure(state='normal' if self.project.get('generated') else 'disabled')
        self.draw()

    def preview_data(self):
        project = copy.deepcopy(self.project)
        project['device'] = project['device'] or 'DEVICE'
        project['footprint'] = project['footprint'] or '未设置'
        project['expected_count'] = None
        # Display unresolved pins without assigning an electrical type to the project.
        for pin in project['pins']:
            if pin['type'] not in core.TYPES:
                pin['type'] = 'ANA'
        if len(core.part_ids(project)) > 1:
            return next((cfg,pins) for part,cfg,pins in core.section_layouts(project,self.env) if part==self.active_part)
        return core.layout(project, self.env)

    def change_part(self, value):
        if not self.busy:
            self.active_part = value.split(' · ')[0]
            self.selected = None
            self.refresh()

    def fit_preview(self):
        self.preview_zoom = 1.0
        self.preview_offset = (0.0, 0.0)
        self.draw()

    def zoom_preview(self, event):
        if not self.drawn_pins or getattr(self, 'drag_start', None):
            return 'break'
        delta = getattr(event, 'delta', 0)
        if not delta:
            return 'break'
        old = self.preview_zoom
        self.preview_zoom = max(0.4, min(8.0, old * 1.2 ** (1 if delta > 0 else -1)))
        ratio = self.preview_zoom / old
        cx, cy = self.canvas.winfo_width()/2, self.canvas.winfo_height()/2
        dx, dy = self.preview_offset
        self.preview_offset = (event.x-cx-(event.x-cx-dx)*ratio,
                               event.y-cy-(event.y-cy-dy)*ratio)
        self.draw()
        return 'break'

    def pan_preview_start(self, event):
        self.pan_start = (event.x, event.y, self.preview_offset)

    def pan_preview(self, event):
        if getattr(self, 'pan_start', None):
            x, y, (dx, dy) = self.pan_start
            self.preview_offset = (dx+event.x-x, dy+event.y-y)
            self.draw()

    def draw(self):
        if not hasattr(self, 'canvas'):
            return
        canvas = self.canvas
        canvas.delete('all')
        self.drawn_pins = {}
        cw, ch = max(canvas.winfo_width(), 200), max(canvas.winfo_height(), 200)
        if not self.project['pins']:
            canvas.create_text(cw / 2, ch / 2 - 25, text='点击左侧导入规格书', fill=INK, font=('Microsoft YaHei UI', 21, 'bold'))
            canvas.create_text(cw / 2, ch / 2 + 20, text='或点击「示例体验」，先看看生成效果', fill=MUTED, font=('Microsoft YaHei UI', 11))
            return
        try:
            cfg, pins = self.preview_data()
        except Exception as exc:
            canvas.create_text(cw/2, ch/2, text='先修正引脚数据，再显示预览\n' + str(exc), fill='#b45309', width=cw-60, font=('Microsoft YaHei UI', 11))
            return
        scale = min((cw-150) / cfg['W'], (ch-130) / cfg['H']) * self.preview_zoom
        dx, dy = self.preview_offset
        ox, oy = (cw-cfg['W']*scale)/2+dx, (ch-cfg['H']*scale)/2+dy
        self.transform = (ox, oy, scale, cfg)
        x1, y1 = ox+cfg['W']*scale, oy+cfg['H']*scale
        canvas.create_rectangle(ox, oy, x1, y1, fill='#f8fafc', outline='#94a3b8', width=2)
        for pid, name, typ, x, y, hx, hy in pins:
            sx, sy, ex, ey = ox+x*scale, oy+y*scale, ox+hx*scale, oy+hy*scale
            selected = self.selected is not None and self.selected < len(self.project['pins']) and self.project['pins'][self.selected]['id'] == pid
            color = '#f97316' if selected else BLUE
            canvas.create_line(sx, sy, ex, ey, fill=color, width=3 if selected else 1.5)
            font_size = max(6, min(24, int(scale * 5.5)))
            if x == hx:
                text_y = sy + 6 if y == 0 else sy - 6
                canvas.create_text(sx, text_y, text=name, anchor='e' if y == 0 else 'w', angle=90, fill=INK, font=('Consolas', font_size))
                canvas.create_text(ex, ey + (-8 if y == 0 else 8), text=pid, fill=MUTED, font=('Consolas', max(6, font_size-1)))
            else:
                canvas.create_text(sx + (6 if x == 0 else -6), sy, text=name, anchor='w' if x == 0 else 'e', fill=INK, font=('Consolas', font_size))
                canvas.create_text((sx+ex)/2, ey-7, text=pid, fill=MUTED, font=('Consolas', max(6, font_size-1)))
            self.drawn_pins[pid] = (sx, sy)
        canvas.create_text(ox+cfg['W']*scale/2, oy+cfg['H']*scale/2-13, text=self.project['device'] or 'DEVICE', fill=INK, font=('Consolas', 13, 'bold'))
        canvas.create_text(ox+cfg['W']*scale/2, oy+cfg['H']*scale/2+12, text=f'{len(pins)} pins · {cfg["PITCH"]} MIL', fill=MUTED, font=('Consolas', 10))
        canvas.create_text(cw-12, ch-12, anchor='se', text='布局示意 · 非 Capture 实际渲染', fill=MUTED, font=('Microsoft YaHei UI', 8))

    def select_pin(self, event=None):
        selection = self.tree.selection()
        if selection:
            self.selected = int(selection[0])
            self.show_source()
            self.draw()

    def show_source(self):
        if self.selected is None or self.selected >= len(self.project['pins']):
            return
        pin = self.project['pins'][self.selected]
        text = f'{pin["id"]} · {pin["name"]}\n分组：{pin["group"]}\n来源：{pin.get("source", "手工输入")}\n页码：{pin.get("page") or "—"}\n\n原文：\n{pin.get("raw", "手工输入")}\n'
        for conflict in pin.get('conflicts', []):
            text += '\n其他定义：' + json.dumps(conflict, ensure_ascii=False)
        self.source_box.configure(state='normal')
        self.source_box.delete('1.0', 'end')
        self.source_box.insert('1.0', text)
        self.source_box.configure(state='disabled')

    def canvas_press(self, event):
        self.drag_start = None
        if self.busy or not self.drawn_pins:
            return
        pid, point = min(self.drawn_pins.items(), key=lambda item: (item[1][0]-event.x)**2+(item[1][1]-event.y)**2)
        if (point[0]-event.x)**2+(point[1]-event.y)**2 > 26**2:
            return
        self.selected = next(i for i, p in enumerate(self.project['pins']) if p['id'] == pid)
        if self.tree.exists(str(self.selected)):
            self.tree.selection_set(str(self.selected))
            self.tree.see(str(self.selected))
        self.drag_start = (event.x, event.y)
        self.show_source()
        self.draw()

    def canvas_release(self, event):
        if not getattr(self, 'drag_start', None) or self.busy:
            return
        start = self.drag_start
        self.drag_start = None
        if abs(event.x-start[0])+abs(event.y-start[1]) < 8:
            return
        ox, oy, scale, cfg = self.transform
        x, y = (event.x-ox)/scale, (event.y-oy)/scale
        side = min({'LEFT': abs(x), 'RIGHT': abs(x-cfg['W']), 'TOP': abs(y), 'BOT': abs(y-cfg['H'])}, key=lambda s: {'LEFT': abs(x), 'RIGHT': abs(x-cfg['W']), 'TOP': abs(y), 'BOT': abs(y-cfg['H'])}[s])
        self.snapshot()
        pin = self.project['pins'].pop(self.selected)
        pin['side'] = side
        # Insert before nearest greater axis coordinate; keep manual order stable.
        target = next((i for i, p in enumerate(self.project['pins']) if p['side'] == side and p['id'] in self.drawn_pins and self.drawn_pins[p['id']][0 if side in ('TOP', 'BOT') else 1] > (event.x if side in ('TOP', 'BOT') else event.y)), len(self.project['pins']))
        self.project['pins'].insert(target, pin)
        self.selected = target
        self.changed()

    def edit_pin(self, index=None):
        if self.busy:
            return
        index = self.selected if index is None else index
        if index is None or index >= len(self.project['pins']):
            return
        pin = self.project['pins'][index]
        dialog = tk.Toplevel(self)
        dialog.title('编辑引脚 · 修改后立即更新预览')
        dialog.transient(self)
        dialog.grab_set()
        fields = {}
        for row, (key, label) in enumerate([('id', '脚号'), ('name', '名称'), ('type', '电气类型'), ('side', '位置'), ('group', '功能分组'), ('part','所属 PART')]):
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=15, pady=8)
            variable = tk.StringVar(value=pin.get(key,'A' if key=='part' else ''))
            fields[key] = variable
            choices = core.TYPES if key == 'type' else core.SIDES if key == 'side' else list(self.project.get('parts',{'A':'主单元'})) if key=='part' else None
            control = ttk.Combobox(dialog, textvariable=variable, values=choices, state='readonly') if choices else ttk.Entry(dialog, textvariable=variable)
            control.grid(row=row, column=1, padx=15, pady=8)
        def commit():
            data = {k: v.get().strip() for k, v in fields.items()}
            data['id'] = data['id'].upper()
            if not core.PIN_RE.fullmatch(data['id']) or not data['name'] or data['type'] not in core.TYPES or data['side'] not in core.SIDES:
                messagebox.showerror('请补全', '请填写正确脚号、名称、类型和位置', parent=dialog)
                return
            if any(p['id'] == data['id'] for i, p in enumerate(self.project['pins']) if i != index):
                messagebox.showerror('脚号重复', '这个脚号已存在', parent=dialog)
                return
            self.snapshot()
            pin.update(data)
            self.changed()
            dialog.destroy()
        ttk.Button(dialog, text='保存修改', command=commit).grid(row=6, columnspan=2, pady=14)

    def add_pin(self):
        if self.busy:
            return
        self.snapshot()
        ids = {p['id'] for p in self.project['pins']}
        pid = str(next(i for i in range(1, 100000) if str(i) not in ids))
        self.project['pins'].append(dict(id=pid, name='NEW_PIN', type='IO', side='LEFT', group='信号', confidence=1.0, conflicts=[],part=self.active_part))
        self.selected = len(self.project['pins'])-1
        self.changed()
        self.edit_pin()

    def remove_pin(self):
        if self.busy or self.selected is None or self.selected >= len(self.project['pins']):
            return
        self.snapshot()
        self.project['pins'].pop(self.selected)
        self.selected = None
        self.changed()
        self.status.set('已移除引脚，可按 Ctrl+Z 撤销')

    def undo(self):
        if not self.busy and self.history:
            self.project = self.history.pop()
            self.selected = None
            self.sync_fields()
            self.changed()

    def relayout(self):
        if self.busy:
            return
        self.snapshot()
        self.project['profile'] = 'sensor' if self.profile.get().startswith('SENSOR') else 'simple'
        core.auto_layout(self.project)
        self.selected = None
        self.changed()

    def select_issue(self, event=None):
        selection = self.issue_list.curselection()
        if selection:
            issue = self.issue_records[selection[0]]
            self.confirm.configure(state='disabled' if issue['blocking'] else 'normal')
            if issue['pin']:
                self.selected = next((i for i, p in enumerate(self.project['pins']) if p['id'] == issue['pin']), None)
                self.show_source()
                self.draw()

    def confirm_issue(self):
        if self.busy:
            return
        selection = self.issue_list.curselection()
        if selection:
            issue = self.issue_records[selection[0]]
            if not issue['blocking']:
                self.snapshot()
                self.project['reviewed'].append(issue['key'])
                self.changed()

    def pick_source(self):
        path = filedialog.askopenfilename(filetypes=[('规格书 / 引脚表', '*.pdf *.csv'), ('所有文件', '*.*')])
        if path:
            self.import_source(path)

    def drop_files(self, paths):
        if self.busy:
            self.status.set('当前任务完成后再导入资料')
            return
        if len(paths) != 1:
            messagebox.showinfo('一次导入一个项目', '请先拖入一份 PDF、CSV 或项目 JSON。')
            return
        if Path(paths[0]).suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.webp'):
            self.import_reference(paths[0])
        elif Path(paths[0]).suffix.lower() == '.json':
            self.open_project(paths[0])
        else:
            self.import_source(paths[0])

    def import_source(self, path):
        if Path(path).suffix.lower() not in ('.pdf', '.csv'):
            messagebox.showinfo('支持的资料', '请导入 PDF 规格书、CSV 引脚表或项目 JSON。截图自动识别将在后续版本加入。')
            return
        def work(progress):
            try:
                pins = core.extract_pdf(path, progress) if Path(path).suffix.lower() == '.pdf' else core.import_csv(path)
            except Exception as exc:
                try:
                    core.atomic_json(STATE / 'last-import-error.json', {
                        'source': str(Path(path).resolve()), 'error': str(exc),
                    })
                except OSError:
                    pass
                raise
            project = core.new_project()
            device = Path(path).stem.split('_ballmap')[0]
            if '_' in device and not device.isascii():
                device = device.split('_')[0]
            project.update(pins=pins, sources=[core.source_record(path)], device=device if len(device) < 81 and all(c.isascii() and (c.isalnum() or c in '_.-') for c in device) else '')
            project['parts'] = {key:'导入单元' for key in dict.fromkeys(p.get('part','A') for p in pins)}
            core.auto_layout(project)
            return project
        def complete(project):
            self.snapshot()
            self.project = project
            self.project_path = None
            self.selected = None
            self.sync_fields()
            self.changed()
            self.status.set(f'已导入 {len(project["pins"])} 个引脚，请核对封装名和待核对事项')
            if len(project['parts']) == 1:
                self.update_idletasks()
                if messagebox.askyesno(
                    '默认布局已生成',
                    f'已生成 {len(project["pins"])} 个引脚的单 PART 布局。\n\n是否需要拆成多个 PART？\n选择“是”可设置拆分方式；选择“否”保留当前布局，稍后也可在“多 PART 管理”中调整。',
                    parent=self,
                ):
                    self.manage_parts()
        self.background(work, complete)

    def load_demo(self):
        if self.busy:
            return
        path = RES / 'examples' / 'GC4693_ballmap.csv'
        if not path.exists():
            messagebox.showerror('示例缺失', str(path))
            return
        self.snapshot()
        self.project = core.new_project()
        self.project.update(device='GC4693', footprint='CSP35', expected_count=35, pins=core.import_csv(path), sources=[core.source_record(path)])
        core.auto_layout(self.project)
        self.project_path = None
        self.selected = None
        self.sync_fields()
        self.changed()
        self.status.set('已载入 GC4693 示例，可以拖动引脚，或直接生成验证')

    def new(self):
        if self.busy:
            return
        self.snapshot()
        self.project = core.new_project()
        self.project_path = None
        self.selected = None
        self.sync_fields()
        self.changed()

    def save(self):
        if self.busy:
            return
        path = self.project_path or filedialog.asksaveasfilename(defaultextension='.json', initialfile=(self.project['device'] or 'symbol') + '.json', filetypes=[('符号项目', '*.json')])
        if path:
            try:
                core.atomic_json(path, self.project)
                self.project_path = path
                self.status.set('项目已保存：' + str(path))
            except Exception as exc:
                messagebox.showerror('保存失败', str(exc))

    def open_project(self, path=None):
        if self.busy:
            return
        path = path or filedialog.askopenfilename(filetypes=[('符号项目', '*.json')])
        if path:
            try:
                project = core.load_project(path)
                self.snapshot()
                self.project = project
                self.project_path = path
                self.selected = None
                self.sync_fields()
                self.refresh()
                core.atomic_json(STATE / 'last-session.json', self.project)
                self.status.set('已打开项目：' + str(path))
            except Exception as exc:
                messagebox.showerror('无法打开项目', str(exc))

    def resume(self):
        path = STATE / 'last-session.json'
        if path.exists():
            self.open_project(str(path))
            self.project_path = None
        else:
            self.status.set('还没有上次项目，先导入资料即可自动保存')

    def background(self, work, complete):
        if self.busy:
            return
        self.busy = True
        for button in self.actions + [self.build_button, self.preview_button]:
            button.configure(state='disabled')
        for widget, state in self.editable_controls:
            widget.configure(state='disabled')
        self.progress.start()
        def runner():
            try:
                result = work(lambda msg: self.events.put(('progress', msg)))
                self.events.put(('complete', (complete, result)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=runner, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'progress':
                    self.status.set(payload)
                else:
                    self.busy = False
                    self.progress.stop()
                    for button in self.actions + [self.preview_button]:
                        button.configure(state='normal')
                    for widget, state in self.editable_controls:
                        widget.configure(state=state)
                    if kind == 'complete':
                        callback, result = payload
                        callback(result)
                    else:
                        self.status.set('没有完成，已保留原项目和上次成品')
                        messagebox.showerror('需要处理的问题', payload)
                    self.refresh()
        except queue.Empty:
            pass
        except Exception as exc:
            self.busy=False
            self.progress.stop()
            self.status.set('界面操作未完成，可重试；项目自动保存记录仍保留')
            core.atomic_json(STATE / 'last-error.json',{'error':str(exc)})
            messagebox.showerror('操作未完成',str(exc))
        self.after(100, self.poll)

    def build(self):
        if self.busy:
            return
        if core.issues(self.project):
            self.status.set('请先处理「来源与待核对」中的事项')
            return
        project, env = copy.deepcopy(self.project), self.env.copy()
        def complete(result):
            # Metadata may have been typed while worker ran. Never associate stale output.
            if self.device.get().strip() != project['device'] or self.footprint.get().strip() != project['footprint'] or self.expected.get().strip() != str(project.get('expected_count') or ''):
                self.metadata_changed()
                self.status.set('构建成功；资料已变动，成品仍保存在：' + result['directory'])
                return
            self.project['generated'] = result
            core.atomic_json(STATE / 'last-session.json', self.project)
            self.refresh()
            self.status.set(f'已验证可用 · {result["report"]["pins"]} 个引脚 · {result["report"].get("parts",1)} PART · 成品已保存')
        self.background(lambda progress: build_pipeline.build(project, env, STATE / 'output', progress), complete)

    def export_preview(self):
        try:
            cfg, pins = self.preview_data()
            path = filedialog.asksaveasfilename(defaultextension='.svg', initialfile=cfg['device']+'.svg', filetypes=[('符号预览', '*.svg')])
            if path:
                core.export_svg(cfg, pins, path)
                self.status.set('预览已导出：' + path)
        except Exception as exc:
            messagebox.showerror('暂时无法预览', str(exc))

    def open_output(self):
        result = self.project.get('generated')
        if result and Path(result['directory']).exists():
            os.startfile(result['directory'])

    def open_source(self):
        if self.selected is None:
            return
        pin = self.project['pins'][self.selected]
        path = Path(pin.get('source', ''))
        if path.is_file():
            if path.suffix.lower() == '.pdf' and pin.get('page'):
                # Render just the relevant page locally, with the table highlighted.
                def work(progress):
                    import fitz
                    progress('正在打开规格书原页…')
                    destination = STATE / 'source-pages'
                    destination.mkdir(parents=True, exist_ok=True)
                    target = destination / f'{core.source_record(path)["sha256"][:10]}-{pin["page"]}.png'
                    with fitz.open(str(path)) as doc:
                        page = doc[pin['page']-1]
                        if pin.get('bbox'):
                            annotation = page.add_rect_annot(fitz.Rect(pin['bbox']))
                            annotation.set_colors(stroke=(1, 0.45, 0))
                            annotation.update()
                        page.get_pixmap(dpi=120).save(str(target))
                    return str(target)
                self.background(work, lambda target: os.startfile(target))
            else:
                os.startfile(str(path))
        else:
            messagebox.showinfo('来源不在此电脑', '原资料路径不可用，请将原资料复制到原位置或重新导入。原文仍保存在项目中。')

    def settings(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self)
        dialog.title('环境设置 · 配置一次，以后自动使用')
        dialog.transient(self)
        dialog.grab_set()
        variables = {}
        for row, (key, label) in enumerate([('tclsh', 'OrCAD Tcl 程序'), ('dll', 'OrCAD 数据库组件'), ('bin', '依赖目录'), ('src_lib', '矩形源库'), ('src_part', '源库器件名')]):
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=12, pady=8, sticky='e')
            variable = tk.StringVar(value=self.env[key])
            variables[key] = variable
            ttk.Entry(dialog, textvariable=variable, width=58).grid(row=row, column=1, padx=12, pady=8)
            if key != 'src_part':
                def browse(k=key, v=variable):
                    path = filedialog.askdirectory(parent=dialog) if k == 'bin' else filedialog.askopenfilename(parent=dialog)
                    if path:
                        v.set(path)
                ttk.Button(dialog, text='浏览', command=browse).grid(row=row, column=2, padx=8)
        feedback = tk.StringVar()
        ttk.Label(dialog, textvariable=feedback, wraplength=600).grid(row=5, columnspan=3, padx=12, pady=8)
        def save_env():
            candidate = {k: v.get().strip() for k, v in variables.items()}
            errors = build_pipeline.check_environment(candidate)
            if errors:
                feedback.set('\n'.join(errors))
                return
            try:
                core.atomic_json(STATE / 'environment.json', candidate)
                self.env = candidate
                self.status.set('环境路径已检查并保存；构建时将进一步验证 OrCAD 加载与回读')
                dialog.destroy()
            except OSError as exc:
                feedback.set(str(exc))
        ttk.Button(dialog, text='检查并保存', style='Primary.TButton', command=save_env).grid(row=6, columnspan=3, pady=12)

    def pick_reference(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title='选择单个 PART 的清晰截图',filetypes=[('符号截图','*.png *.jpg *.jpeg *.bmp *.webp')])
        if path:
            self.import_reference(path)

    def import_reference(self, path):
        if not self.project['pins']:
            messagebox.showinfo('先导入引脚', '先导入规格书或 CSV，再用截图调整布局。截图不替代引脚编号和名称。')
            return
        from reference_layout import analyze, apply
        part = self.active_part
        pins = copy.deepcopy([p for p in self.project['pins'] if p.get('part','A')==part])
        def complete(result):
            import customtkinter as ctk
            from PIL import Image, ImageOps
            dialog=ctk.CTkToplevel(self)
            dialog.title('截图布局 · 先预览匹配结果')
            dialog.geometry('700x640')
            dialog.transient(self)
            dialog.grab_set()
            ctk.CTkLabel(dialog,text=f'PART {part} · 已匹配 {result["matched"]} / {len(pins)} 脚',font=('Microsoft YaHei UI',20,'bold')).pack(padx=24,pady=(22,8),anchor='w')
            image=ImageOps.exif_transpose(Image.open(path))
            image.thumbnail((640,390))
            displayed=ctk.CTkImage(light_image=image,dark_image=image,size=image.size)
            ctk.CTkLabel(dialog,text='',image=displayed).pack(padx=20,pady=10,expand=True)
            ctk.CTkLabel(dialog,text=result['note']+'\n不确定的匹配不会自动应用。',wraplength=620,justify='left',text_color='#718096').pack(padx=24,pady=12)
            def commit():
                self.snapshot()
                apply(self.project,result,part)
                self.changed()
                self.tabs.select(1)
                self.status.set(f'截图布局已应用：{result["matched"]} 个引脚；请检查预览后确认截图事项')
                dialog.destroy()
            ctk.CTkButton(dialog,text='应用到当前 PART',command=commit,height=40,fg_color='#4263EB').pack(pady=(0,22))
        self.background(lambda progress: analyze(path,pins,progress),complete)

    def manage_parts(self):
        if self.busy or not self.project['pins']:
            self.status.set('先导入引脚，再管理 PART')
            return
        import customtkinter as ctk
        dialog=ctk.CTkToplevel(self)
        dialog.title('多 PART · 一个器件，多个功能单元')
        dialog.geometry('520x410')
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog,text='把复杂器件拆成清晰的功能块',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w',padx=26,pady=(26,12))
        ctk.CTkLabel(dialog,text='按电源、控制、高速接口自动拆分；差分对保持相邻。\n所有 PART 共用一个 package，脚号完整且不重复。',justify='left',text_color='#718096').pack(anchor='w',padx=26,pady=(0,20))
        maximum=tk.StringVar(value='64')
        ctk.CTkLabel(dialog,text='每个 PART 建议最多引脚数').pack(anchor='w',padx=26)
        ctk.CTkEntry(dialog,textvariable=maximum,width=120,height=36).pack(anchor='w',padx=26,pady=8)
        def split():
            try:
                candidate=copy.deepcopy(self.project)
                core.split_parts(candidate,int(maximum.get()))
                self.snapshot()
                self.project=candidate
                self.active_part=core.part_ids(candidate)[0]
                self.changed()
                self.status.set(f'已拆分为 {len(core.part_ids(candidate))} 个 PART；可在引脚编辑中手动更改单元')
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror('请检查设置',str(exc),parent=dialog)
        ctk.CTkButton(dialog,text='按功能自动拆分',command=split,fg_color='#4263EB',height=38).pack(anchor='w',padx=26,pady=10)
        def merge():
            self.snapshot()
            for pin in self.project['pins']:
                pin['part']='A'
            self.project['parts']={'A':'主单元'}
            self.active_part='A'
            self.changed()
            dialog.destroy()
        def add_part():
            self.snapshot()
            keys=self.project.setdefault('parts',{'A':'主单元'})
            key=next((chr(i) for i in range(65,91) if chr(i) not in keys),None)
            if key:
                keys[key]='自定义单元'
                self.changed()
                dialog.destroy()
                self.status.set(f'已添加 PART {key}；双击引脚，把所属 PART 改为 {key}')
        buttons=ctk.CTkFrame(dialog,fg_color='transparent')
        buttons.pack(fill='x',padx=26,pady=10)
        ctk.CTkButton(buttons,text='新增空白 PART',command=add_part,width=160,fg_color='#E9EEFA',text_color='#4263EB').pack(side='left',padx=(0,10))
        ctk.CTkButton(buttons,text='合并为一个 PART',command=merge,width=160,fg_color='#E9EEFA',text_color='#4263EB').pack(side='left')

    def close_app(self):
        if self.busy:
            messagebox.showinfo('正在处理', '当前任务正在后台执行，完成后即可关闭。')
            return
        try:
            core.atomic_json(STATE / 'last-session.json', self.project)
        except OSError:
            if not messagebox.askyesno('未能自动保存', '自动保存失败，仍要关闭吗？'):
                return
        self.destroy()


if __name__ == '__main__':
    import faulthandler
    STATE.mkdir(parents=True, exist_ok=True)
    crash_log = (STATE / 'crash.log').open('a', encoding='utf-8')
    faulthandler.enable(file=crash_log)
    parser = argparse.ArgumentParser()
    parser.add_argument('--project')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--selftest-report', help=argparse.SUPPRESS)
    parser.add_argument('--selftest-build', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.selftest_report:
        import gui_selftest
        try:
            gui_selftest.run(args.selftest_report, args.selftest_build)
        except Exception:
            sys.exit(1)
    else:
        Assistant(args.project, args.demo).mainloop()
