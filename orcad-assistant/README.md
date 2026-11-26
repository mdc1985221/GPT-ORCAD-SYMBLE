# OrCAD / Allegro 器件符号与 PCB 封装助手

当前使用 **Python + HTML Web 界面**。完整功能、安装、授权及限制请查看[上一级 README](../README.md)，版本变更见[CHANGELOG](../CHANGELOG.md)。

## 启动

安装本目录 `requirements.txt` 中的依赖后，在本目录运行：

```powershell
python web_app.py
```

也可以双击上一级目录的 `启动符号助手.cmd`。打开 <http://127.0.0.1:8765/>，保持服务窗口运行。`app.py` 为早期桌面界面，不是当前推荐入口。GitHub提供源码；本机另有已同步的桌面EXE，运行数据保存在各自workspace，更新时必须保留。

## 当前功能

- 导入 PDF 文字层、引脚 CSV 或项目 JSON，生成默认四侧符号布局，支持多 PART。
- 按 10 MIL 格点拖动 PIN、框选批量移动、调整外框和撤销；可使用截图辅助布局。
- 对受支持的 CSP/BGA 参数进行预览与确认，联合生成 OLB 和 Allegro DRA / PSM / PAD，独立回读验证编号、位置、单位和尺寸。
- 本地开发版提供分类器件库：验证后自动入库，搜索、预览、载入编辑和复制 Capture / psmpath / padpath。
- 设计用下载仅保留已生成的 OLB / PSM / PAD / STEP，可选 DRA；单独生成符号时只下载 OLB。诊断资料与设计用下载分开。
- 常用贴片库首批22套规则：电阻7、电容7、电感4、二极管4；原厂PDF版本哈希、机械尺寸和推荐铜焊盘分别留档。仅阻容中间写0402/0603等实际封装代号，隐藏PIN NAME、保留脚号，使用Short。详见[首批说明](../常用贴片器件库-首批22套说明.md)。

原生生成需要安装并配置本机 Cadence OrCAD / Allegro。当前重点验证 Sensor 的 CSP/BGA 场景；分类不代表已经支持所有器件类型的自动建模。3D 可选安装 `requirements-model3d.txt`，支持简化本体与焊球的 STEP 生成及 Web 旋转预览；总高与球高需确认。外部 STEP 导入和 Cadence 自动模型绑定尚未实现，详见上一级 README。

## 本地数据与验证

项目、导入资料、生成结果及分类库保存在 `workspace/`，不提交 Git。升级前先保存项目并停止服务，保留此目录。已放入设计的旧器件不会随 Web 修改自动更新。

```powershell
python -m unittest discover -s tests -v
```

当前源码117项单元测试通过，已完成真实 OLB + PCB + STEP 联合生成、自动入库和浏览器预览/下载流程验证。首批22套另逐套完成OLB回读、PCB毫米/mil板内放置、STEP重导入和桌面版预览；自动回读不能替代目标设计的 DRC、网表与制造审核。


## TPS543620 RPY0014A 异形 QFN

新增已核对的 TI 指定版本适配：独立多边形铜/阻焊/锡膏、SSM/PAD 原生生成、14脚OLB和独立器件端子STEP。Web导入匹配PDF后显示异形焊盘页；改变规格书版本需重新核对，不是任意QFN通用识别。多窗口原生焊盘当前明确阻止生成，后续扩展。

依赖 `shapely>=2,<3`。异形PAD依赖SSM，必须同时提供padpath和包含PSM/SSM的psmpath；下载器件库会自动保留所需SSM。STEP使用器件端子机械图，与PCB推荐焊盘轮廓分开；圆端及顶面标记的外观近似见样例验收报告。

新功能在源码Web版本及独立验证工作区中实现，本机2026.11.26桌面EXE已同步；仓库不包含本机EXE、规格书归档与已生成库。

## 重建常用贴片参考库

在仓库根目录执行：

```powershell
python orcad-assistant/build_standard_smd_library.py --list
python orcad-assistant/build_standard_smd_library.py --device R0402_CRCW
```

第二条会下载匹配原厂版本的PDF，调用本机Cadence和可选CadQuery环境完成符号、PCB和STEP验证，再写入本地分类库。已有PDF可通过`--datasheets`指定文件夹；省略`--device`生成首批22套。它是已核对系列的生成规则，不会将任意同尺寸器件自动等同。工艺预设与未标注3D外观近似仍须核对。
