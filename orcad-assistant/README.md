# OrCAD / Allegro 器件符号与 PCB 封装助手

当前使用 **Python + HTML Web 界面**。完整功能、安装、授权及限制请查看[上一级 README](../README.md)，版本变更见[CHANGELOG](../CHANGELOG.md)。

## 启动

安装本目录 `requirements.txt` 中的依赖后，在本目录运行：

```powershell
python web_app.py
```

也可以双击上一级目录的 `启动符号助手.cmd`。打开 <http://127.0.0.1:8765/>，保持服务窗口运行。`app.py` 为早期桌面界面，不是当前推荐入口；本次发布更新 Python/Web 源码，旧 EXE 不包含新增功能。

## 当前功能

- 导入 PDF 文字层、引脚 CSV 或项目 JSON，生成默认四侧符号布局，支持多 PART。
- 按 10 MIL 格点拖动 PIN、框选批量移动、调整外框和撤销；可使用截图辅助布局。
- 对受支持的 CSP/BGA 参数进行预览与确认，联合生成 OLB 和 Allegro DRA / PSM / PAD，独立回读验证编号、位置、单位和尺寸。
- 本地开发版提供分类器件库：验证后自动入库，搜索、预览、载入编辑和复制 Capture / psmpath / padpath。
- 设计用下载仅保留已生成的 OLB / PSM / PAD / SSM / STEP，可选 DRA；单独生成符号时只下载 OLB。诊断资料与设计用下载分开。

原生生成需要安装并配置本机 Cadence OrCAD / Allegro。当前重点验证 Sensor 的 CSP/BGA 场景；分类不代表已经支持所有器件类型的自动建模。3D 可选安装 `requirements-model3d.txt`，支持简化本体与焊球的 STEP 生成及 Web 旋转预览；总高与球高需确认。外部 STEP 导入和 Cadence 自动模型绑定尚未实现，详见上一级 README。

## 本地数据与验证

项目、导入资料、生成结果及分类库保存在 `workspace/`，不提交 Git。升级前先保存项目并停止服务，保留此目录。已放入设计的旧器件不会随 Web 修改自动更新。

```powershell
python -m unittest discover -s tests -v
```

本地开发版共 96 项自动回归测试，并已完成真实 OLB + PCB + STEP 联合生成、自动入库和浏览器预览/下载流程验证。自动回读不能替代目标设计的 DRC、网表与制造审核。


## TPS543620 RPY0014A 异形 QFN

新增已核对的 TI 指定版本适配：独立多边形铜/阻焊/锡膏、SSM/PAD 原生生成、14脚OLB和独立器件端子STEP。Web导入匹配PDF后显示异形焊盘页；改变规格书版本需重新核对，不是任意QFN通用识别。多窗口原生焊盘当前明确阻止生成，后续扩展。

依赖 `shapely>=2,<3`。异形PAD依赖SSM，必须同时提供padpath和包含PSM/SSM的psmpath；下载器件库会自动保留所需SSM。STEP使用器件端子机械图，与PCB推荐焊盘轮廓分开；圆端及顶面标记的外观近似见样例验收报告。

新功能在源码Web版本及独立验证工作区中实现；2026.11.18旧EXE尚不包含本次新增模块。
