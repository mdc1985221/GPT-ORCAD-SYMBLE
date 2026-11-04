"""Calm desktop workbench: navy navigation, white cards, a large drawing area."""
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import assistant_core as core

BG = '#F3F5F9'
INK = '#16243B'
MUTED = '#8290A5'
BLUE = '#4263EB'
NAV = '#17243B'


def build_ui(app):
    ctk.set_appearance_mode('light')
    ctk.set_default_color_theme('blue')
    app.geometry('1420x900')
    app.minsize(1240,800)
    app.configure(bg=BG)
    font = lambda size=13, weight='normal': ctk.CTkFont(family='Microsoft YaHei UI', size=size, weight=weight)
    app.editable_controls = []
    app.actions = []
    style = ttk.Style(app)
    style.theme_use('clam')
    style.configure('Treeview', background='white', fieldbackground='white', foreground=INK,
                    font=('Microsoft YaHei UI',10), rowheight=34, borderwidth=0, relief='flat')
    style.configure('Treeview.Heading', background='#F5F7FC', foreground='#6C7A91',
                    font=('Microsoft YaHei UI',9), padding=(6,10), borderwidth=0, relief='flat')
    style.map('Treeview', background=[('selected','#E9EEFF')], foreground=[('selected',BLUE)])
    style.map('Treeview.Heading', background=[('active','#EEF2F8')])
    style.configure('TNotebook', background='white', borderwidth=0, tabmargins=0)
    style.configure('TNotebook.Tab', background='white', foreground=MUTED, padding=(20,12),
                    font=('Microsoft YaHei UI',10), borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected','#EEF2FF')], foreground=[('selected',BLUE)])

    nav = ctk.CTkFrame(app,width=192,corner_radius=0,fg_color=NAV)
    nav.pack(side='left', fill='y')
    nav.pack_propagate(False)
    mark = ctk.CTkFrame(nav,width=42,height=42,corner_radius=13,fg_color=BLUE)
    mark.pack(anchor='w',padx=24,pady=(28,14))
    ctk.CTkLabel(mark,text='S',font=font(25,'bold'),text_color='white').place(relx=.5,rely=.5,anchor='center')
    ctk.CTkLabel(nav,text='Symbol Studio',text_color='white',font=font(20,'bold')).pack(anchor='w',padx=24)
    ctk.CTkLabel(nav,text='OrCAD 符号工作台',text_color='#91A0BA',font=font(11)).pack(anchor='w',padx=24,pady=(3,26))
    def nav_button(title,action,primary=False):
        button=ctk.CTkButton(nav,text=title,command=action,anchor='w',height=42,width=152,
            fg_color=BLUE if primary else 'transparent',hover_color='#2B3C59',
            text_color='white' if primary else '#C4D0E3',corner_radius=9,font=font(12))
        button.pack(padx=20,pady=4,fill='x')
        app.actions.append(button)
        return button
    nav_button('＋  导入规格书 / CSV',app.pick_source,True)
    nav_button('▧  参考截图布局',app.pick_reference)
    nav_button('▦  多 PART 管理',app.manage_parts)
    ctk.CTkFrame(nav,height=1,fg_color='#30415C').pack(fill='x',padx=24,pady=20)
    ctk.CTkLabel(nav,text='项目',text_color='#788CA9',font=font(10)).pack(anchor='w',padx=28,pady=(0,7))
    nav_button('新建项目',app.new)
    nav_button('打开项目',app.open_project)
    nav_button('继续上次',app.resume)
    nav_button('示例体验',app.load_demo)
    footer=ctk.CTkFrame(nav,fg_color='transparent')
    footer.pack(side='bottom',fill='x',padx=20,pady=20)
    ctk.CTkButton(footer,text='环境设置',command=app.settings,height=34,
        fg_color='#253650',hover_color='#304561',font=font(11)).pack(fill='x')
    ctk.CTkLabel(footer,text='本地处理  ·  10 MIL 格点',font=font(10),text_color='#7F92AF').pack(pady=(14,0))

    work=ctk.CTkFrame(app,fg_color=BG,corner_radius=0)
    work.pack(side='left',fill='both',expand=True)
    header=ctk.CTkFrame(work,fg_color='transparent')
    header.pack(fill='x',padx=28,pady=(22,16))
    heading=ctk.CTkFrame(header,fg_color='transparent')
    heading.pack(side='left')
    ctk.CTkLabel(heading,text='器件符号',font=font(25,'bold'),text_color=INK).pack(anchor='w')
    ctk.CTkLabel(heading,text='从资料到符号，让每一个引脚都有依据。',font=font(11),text_color=MUTED).pack(anchor='w',pady=(4,0))
    save=ctk.CTkButton(header,text='保存项目',command=app.save,width=100,height=36,
        fg_color='white',text_color=INK,border_width=1,border_color='#DDE3EE',hover_color='#E9EEFA',font=font(12))
    save.pack(side='right')
    app.actions.append(save)
    ctk.CTkLabel(header,text='01 导入    /    02 排布与核对    /    03 生成',font=font(10),text_color=MUTED).pack(side='right',padx=22)

    metadata=ctk.CTkFrame(work,fg_color='white',corner_radius=14,border_width=1,border_color='#E5EAF2')
    metadata.pack(fill='x',padx=28,pady=(0,16))
    source_row=ctk.CTkFrame(metadata,fg_color='transparent')
    source_row.pack(fill='x',padx=20,pady=(14,2))
    ctk.CTkLabel(source_row,text='资料',text_color=BLUE,font=font(10,'bold')).pack(side='left')
    ctk.CTkLabel(source_row,textvariable=app.source_text,text_color=MUTED,font=font(10),anchor='w').pack(side='left',padx=12)
    fields=ctk.CTkFrame(metadata,fg_color='transparent')
    fields.pack(fill='x',padx=20,pady=(5,18))
    for column,(label,var,width) in enumerate([('器件名称',app.device,190),('PCB 封装名称',app.footprint,190),('预期脚数',app.expected,90)]):
        container=ctk.CTkFrame(fields,fg_color='transparent')
        container.pack(side='left',padx=(0,18))
        ctk.CTkLabel(container,text=label,text_color='#6C7A91',font=font(10)).pack(anchor='w',pady=(0,5))
        entry=ctk.CTkEntry(container,textvariable=var,width=width,height=36,corner_radius=7,
                          fg_color='#FAFBFE',border_color='#E1E6F0',text_color=INK,font=font(12))
        entry.pack()
        app.editable_controls.append((entry,'normal'))
    container=ctk.CTkFrame(fields,fg_color='transparent')
    container.pack(side='left')
    ctk.CTkLabel(container,text='布局规则',text_color='#6C7A91',font=font(10)).pack(anchor='w',pady=(0,5))
    combo=ctk.CTkComboBox(container,variable=app.profile,values=['SENSOR 功能分组','普通 IC · 逆时针'],
        state='readonly',width=190,height=36,corner_radius=7,fg_color='#FAFBFE',border_color='#E1E6F0',
        button_color='#E9EEFA',button_hover_color='#DDE5F8',text_color=INK,font=font(11),command=lambda v:app.relayout())
    combo.pack()
    app.editable_controls.append((combo,'readonly'))

    body=ctk.CTkFrame(work,fg_color='transparent')
    body.pack(fill='both',expand=True,padx=28)
    left=ctk.CTkFrame(body,fg_color='white',corner_radius=14,border_width=1,border_color='#E5EAF2',width=390)
    left.pack(side='left',fill='both',expand=False,padx=(0,16))
    left.pack_propagate(False)
    table_header=ctk.CTkFrame(left,fg_color='transparent')
    table_header.pack(fill='x',padx=16,pady=(16,10))
    ctk.CTkLabel(table_header,text='引脚清单',text_color=INK,font=font(14,'bold')).pack(side='left')
    ctk.CTkLabel(table_header,textvariable=app.summary,text_color=MUTED,font=font(10)).pack(side='right')
    filterrow=ctk.CTkFrame(left,fg_color='transparent')
    filterrow.pack(fill='x',padx=16,pady=(0,12))
    app.part_choice=tk.StringVar(value='A')
    app.part_selector=ctk.CTkComboBox(filterrow,variable=app.part_choice,values=['A'],width=175,height=30,
        state='readonly',font=font(10),fg_color='#F5F7FC',border_width=0,
        button_color='#E7ECF8',button_hover_color='#DCE4F7',text_color=INK,command=app.change_part)
    app.part_selector.pack(side='left')
    app.editable_controls.append((app.part_selector,'readonly'))
    ctk.CTkCheckBox(filterrow,text='只看疑点',variable=app.only_issues,command=app.refresh,
        font=font(10),checkbox_width=16,checkbox_height=16,corner_radius=4,width=80).pack(side='right')
    table_frame=ctk.CTkFrame(left,fg_color='white',corner_radius=0)
    table_frame.pack(fill='both',expand=True,padx=10)
    app.tree=ttk.Treeview(table_frame,columns=('id','name','type','side'),show='headings',selectmode='browse')
    for key,label,width in [('id','脚号',56),('name','名称',150),('type','类型',53),('side','位置',53)]:
        app.tree.heading(key,text=label)
        app.tree.column(key,width=width,minwidth=40,stretch=key=='name')
    app.tree.pack(side='left',fill='both',expand=True)
    bar=ctk.CTkScrollbar(table_frame,command=app.tree.yview,width=10)
    bar.pack(side='right',fill='y')
    app.tree.configure(yscrollcommand=bar.set)
    app.tree.tag_configure('issue',background='#FFF6E8',foreground='#A5681D')
    app.tree.bind('<<TreeviewSelect>>',app.select_pin)
    app.tree.bind('<Double-1>',lambda e:app.edit_pin())
    controls=ctk.CTkFrame(left,fg_color='transparent')
    controls.pack(fill='x',padx=12,pady=14)
    for title,action in [('编辑',app.edit_pin),('添加',app.add_pin),('移除',app.remove_pin),('撤销',app.undo),('重排',app.relayout)]:
        button=ctk.CTkButton(controls,text=title,command=action,width=60,height=30,corner_radius=6,
            fg_color='#F1F4FB',text_color='#53647F',hover_color='#E6ECF9',font=font(10))
        button.pack(side='left',padx=3)
        app.actions.append(button)

    right=ctk.CTkFrame(body,fg_color='white',corner_radius=14,border_width=1,border_color='#E5EAF2')
    right.pack(side='left',fill='both',expand=True)
    tabs=ttk.Notebook(right)
    app.tabs=tabs
    tabs.pack(fill='both',expand=True,padx=12,pady=(10,6))
    preview=tk.Frame(tabs,bg='white')
    review=tk.Frame(tabs,bg='white')
    tabs.add(preview,text='符号画布')
    tabs.add(review,text='来源与核对')
    toolbar=ctk.CTkFrame(preview,fg_color='transparent')
    toolbar.pack(fill='x',padx=10,pady=5)
    ctk.CTkButton(toolbar,text='适应窗口',command=app.fit_preview,width=85,height=28,
        fg_color='#EEF2FF',text_color=BLUE).pack(side='right')
    app.canvas=tk.Canvas(preview,bg='white',highlightthickness=0)
    app.canvas.pack(fill='both',expand=True)
    app.canvas.bind('<Configure>',lambda e:app.draw())
    app.canvas.bind('<ButtonPress-1>',app.canvas_press)
    app.canvas.bind('<ButtonRelease-1>',app.canvas_release)
    app.canvas.bind('<MouseWheel>',app.zoom_preview)
    app.canvas.bind('<ButtonPress-3>',app.pan_preview_start)
    app.canvas.bind('<B3-Motion>',app.pan_preview)
    ctk.CTkLabel(preview,text='滚轮缩放 · 右键拖动画布 · 左键拖动引脚 · Ctrl+Z 撤销',text_color=MUTED,font=font(10)).pack(pady=(0,10))
    ctk.CTkLabel(review,text='只确认需要你判断的地方',font=font(16,'bold'),text_color=INK).pack(anchor='w',padx=18,pady=(18,8))
    app.issue_list=tk.Listbox(review,height=7,bg='#F7F9FD',fg='#8B632B',selectbackground='#FFF0D6',
        selectforeground=INK,relief='flat',highlightthickness=0,font=('Microsoft YaHei UI',10),activestyle='none')
    app.issue_list.pack(fill='x',padx=18,pady=8)
    app.issue_list.bind('<<ListboxSelect>>',app.select_issue)
    app.confirm=ctk.CTkButton(review,text='已核对，确认此项',command=app.confirm_issue,height=32,width=150,
                             fg_color=BLUE,font=font(11))
    app.confirm.pack(anchor='w',padx=18,pady=6)
    ctk.CTkLabel(review,text='所选引脚的来源',font=font(11,'bold'),text_color=INK).pack(anchor='w',padx=18,pady=(16,6))
    app.source_box=tk.Text(review,wrap='word',bg='#F7F9FD',fg='#53647F',relief='flat',
        font=('Microsoft YaHei UI',10),height=8,padx=12,pady=12,state='disabled')
    app.source_box.pack(fill='both',expand=True,padx=18)
    ctk.CTkButton(review,text='查看规格书原页',command=app.open_source,fg_color='#EEF2FF',text_color=BLUE,
        font=font(11),height=30).pack(anchor='w',padx=18,pady=12)

    bottom=ctk.CTkFrame(work,fg_color='transparent')
    bottom.pack(fill='x',padx=28,pady=(14,20))
    statusbox=ctk.CTkFrame(bottom,fg_color='transparent')
    statusbox.pack(side='left',fill='x',expand=True)
    app.review_summary=tk.StringVar()
    ctk.CTkLabel(statusbox,textvariable=app.review_summary,text_color='#A36D27',font=font(10),anchor='w').pack(anchor='w')
    ctk.CTkLabel(statusbox,textvariable=app.status,text_color=MUTED,font=font(10),wraplength=430,anchor='w').pack(anchor='w',pady=(3,0))
    app.progress=ctk.CTkProgressBar(bottom,mode='indeterminate',width=60,height=3)
    app.progress.set(0)
    app.progress.pack(side='left',padx=8)
    app.preview_button=ctk.CTkButton(bottom,text='导出预览',command=app.export_preview,width=90,height=38,
        fg_color='white',text_color=INK,border_width=1,border_color='#DEE4EE',hover_color='#E9EEFA',font=font(11))
    app.preview_button.pack(side='left',padx=5)
    app.build_button=ctk.CTkButton(bottom,text='生成并验证 OLB  →',command=app.build,width=166,height=40,
        fg_color=BLUE,hover_color='#3150D9',corner_radius=9,font=font(12,'bold'))
    app.build_button.pack(side='left',padx=5)
    app.output_button=ctk.CTkButton(bottom,text='成品目录',command=app.open_output,width=85,height=38,
        fg_color='#E7EDFF',text_color=BLUE,hover_color='#DCE5FF',font=font(11))
    app.output_button.pack(side='left',padx=(5,0))
