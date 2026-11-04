"""Application-owned Tk smoke test, no operating-system input automation."""
import copy
import json
import tempfile
import time
import sys
from pathlib import Path
from types import SimpleNamespace


def run(report_path, perform_build=False):
    import app
    import assistant_core as core
    report_path = Path(report_path).resolve()
    checks = []
    root = None
    native_errors = []
    old_unraisable = sys.unraisablehook
    sys.unraisablehook = lambda detail: native_errors.append(str(detail.exc_value))
    dialogs = []
    old_showerror = app.messagebox.showerror
    old_askyesno = app.messagebox.askyesno
    app.messagebox.askyesno = lambda *args, **kwargs: False
    app.messagebox.showerror = lambda title, message, **kwargs: dialogs.append(str(message))
    try:
        with tempfile.TemporaryDirectory() as temporary:
            app.STATE = Path(temporary) / 'workspace'
            root = app.Assistant(demo=True)
            callback_errors = []
            root.report_callback_exception = lambda *args: callback_errors.append(str(args[1]))
            root.update()
            fixture = report_path.parent / 'fixture.pdf'
            if fixture.exists():
                root.import_source(str(fixture))
                deadline = time.monotonic() + 55
                while root.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
                assert not root.busy and len(root.project['pins']) == 3, f'PDF import: busy={root.busy}, pins={len(root.project["pins"])}, status={root.status.get()}, callbacks={callback_errors}, errors={dialogs}'
                assert len(core.issues(root.project)) == 1
                root.issue_list.selection_set(0)
                root.confirm_issue()
                assert not core.issues(root.project)
                checks.append('后台 PDF 抽取 / 来源记录 / 核对确认')
                root.load_demo()
                root.update()
            assert len(root.project['pins']) == 35
            assert len(root.drawn_pins) == 35
            assert root.canvas.winfo_width() > 400 and root.canvas.winfo_height() > 250
            assert root.build_button.cget('state') != 'disabled'
            checks.append('示例加载 / 35 脚预览 / 构建可用')
            assert not getattr(root, '_drop_callback', None)
            checks.append('稳定模式：未安装原生窗口过程钩子')
            initial = copy.deepcopy(root.project)
            anchor_x, anchor_y = 210, 160
            ox, oy, scale, _ = root.transform
            before = ((anchor_x-ox)/scale, (anchor_y-oy)/scale)
            root.zoom_preview(SimpleNamespace(x=anchor_x,y=anchor_y,delta=120))
            ox, oy, scale, _ = root.transform
            after = ((anchor_x-ox)/scale, (anchor_y-oy)/scale)
            assert all(abs(a-b)<1e-8 for a,b in zip(before,after))
            assert root.preview_zoom>1 and root.project==initial
            root.pan_preview_start(SimpleNamespace(x=100,y=100))
            root.pan_preview(SimpleNamespace(x=140,y=130))
            root.fit_preview()
            assert root.preview_zoom==1 and root.preview_offset==(0,0)
            checks.append('鼠标锚点缩放 / 画布平移 / 适应窗口，不修改项目')
            pid = root.project['pins'][0]['id']
            x, y = root.drawn_pins[pid]
            root.canvas_press(SimpleNamespace(x=x, y=y))
            ox, oy, scale, cfg = root.transform
            root.canvas_release(SimpleNamespace(x=ox+cfg['W']*scale, y=oy+cfg['H']*scale/2))
            assert next(p for p in root.project['pins'] if p['id']==pid)['side'] == 'RIGHT'
            root.undo()
            assert root.project['pins'] == initial['pins']
            checks.append('拖动换边 / 撤销恢复')
            root.expected.set('36')
            assert root.build_button.cget('state') == 'disabled'
            assert len(root.drawn_pins) == 35
            root.expected.set('35')
            assert root.build_button.cget('state') != 'disabled'
            checks.append('脚数不一致阻断构建，预览保留')
            path = Path(temporary) / 'symbol.json'
            root.project_path = str(path)
            root.save()
            assert core.load_project(path)['pins'] == root.project['pins']
            root.new()
            root.open_project(str(path))
            root.update()
            assert len(root.project['pins']) == 35
            checks.append('项目保存 / 新建 / 重开')
            root.selected = 0
            root.show_source()
            assert root.project['pins'][0]['id'] in root.source_box.get('1.0', 'end')
            checks.append('所选引脚来源定位')
            if perform_build:
                root.build_button.invoke()
                assert root.busy
                deadline = time.monotonic() + 40
                while root.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
                assert not root.busy and root.project.get('generated'), root.status.get()
                assert root.project['generated']['report']['status'] == 'PASS'
                checks.append('GUI 后台真实构建 / 消息队列 / 独立回读通过')
            core.split_parts(root.project,16)
            root.refresh()
            root.change_part('D · 高速接口 (10)')
            root.update()
            assert len(root.drawn_pins)==10
            assert len(root.tree.get_children())==10
            checks.append('多 PART 分配 / 画布切换 / 清单过滤')
            if perform_build:
                root.project['generated']=None
                root.build_button.invoke()
                deadline=time.monotonic()+40
                while root.busy and time.monotonic()<deadline:
                    root.update()
                    time.sleep(.02)
                assert root.project.get('generated') and root.project['generated']['report']['parts']==4
                checks.append('GUI 四 PART 真实构建 / 共享 package 回读')
            root.destroy()
            root = None
            assert not callback_errors, callback_errors
            assert not native_errors, native_errors
            assert not dialogs, dialogs
            report = dict(status='PASS', checks=checks, visual_review='未完成：桌面检查连接不可用')
    except Exception as exc:
        import traceback
        import threading
        stacks = {thread.name: ''.join(traceback.format_stack(sys._current_frames()[thread.ident])) for thread in threading.enumerate() if thread.ident in sys._current_frames()}
        report = dict(status='FAILED', error=str(exc), checks=checks, dialogs=dialogs, stacks=stacks)
        raise
    finally:
        if root:
            root.destroy()
        sys.unraisablehook = old_unraisable
        app.messagebox.showerror = old_showerror
        app.messagebox.askyesno = old_askyesno
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else 'validation-output/gui-smoke.json', '--build' in sys.argv)
