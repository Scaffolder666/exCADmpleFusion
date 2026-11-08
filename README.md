# exCADmple — Autodesk Fusion 插件

**Supporting Design Reasoning Through Shared CAD Models** · 固定开发分支 `fusion`

用户在自己的 Fusion 工作空间中探索其他设计师的设计过程与推理：通过交互式时间轴播放整个过程或重访单个步骤；每一步展示模型如何演变、原设计师如何执行 CAD 操作，并同步播放解释设计选择的语音与文字。用户可以完整跟随，也可以在同一工作空间里发展自己的设计时有选择地借鉴个别步骤——学习**怎么建模**，也学习**怎么设计**。

项目概况见 [`main`](https://github.com/Scaffolder666/exCADmpleFusion)；Blender 版本见 [`blender`](https://github.com/Scaffolder666/exCADmpleFusion/tree/blender)。

## 两个界面版本（用于比较）

两个版本**功能相同**：相同的案例、推理内容和播放能力（整个过程／单步、速度、字幕、语音、决策、多案例、Reasoning Reuse 面板、案例提取）。区别只在**界面如何组织**，以及用户如何在参考案例和自己的建模之间切换。两个分支共用同一份代码，由 `config.json` 的 `layout` 选择：

| | 版本 A：独立参考视口（`fusion-him` 分支，`"layout": "reference"`） | 版本 B：视口内 Overlay（本分支，`"layout": "overlay"`） |
|---|---|---|
| 参考案例在哪里播放 | 单独窗口中的**交互式 3D 参考视口**（可旋转、平移、缩放）；Fusion 画布里只有用户自己的模型 | 直接在 **Fusion 画布**中，作为只读的 Custom Graphics，放在用户模型旁边 |
| 教程信息 | 窗口右侧的**纵向历史面板**（参考 *History in Motion*）：彩色胶囊步骤，当前步骤展开显示 Why、决策、How、同步字幕 | 浮在画布上的紧凑面板（可收起为只剩步骤条），以及固定在画布左上角的 HUD 文字：步骤标题、Why、当前字幕 |
| 按几何探索历史 | 在参考视口里**点击案例模型**的某处 → 找出制作或改变这里的步骤（比较每一步前后的几何），从最新的开始播放；**Show more** 往前追依赖步骤；其余几何半透明，最终模型以淡影显示 | 选择步骤后在画布中查看；按几何探索通过右侧 Reasoning Reuse 面板（作用于用户自己的模型） |
| 后退 | 倒放当前步骤（HiM 的做法） | 跳到上一步 |

技术说明：Fusion 不允许在原生画布上叠加可交互的 HTML。版本 B 用"浮动 Palette + 画布内的 Custom Graphics（参考模型、Ghost Pointer、HUD 文字）"尽量接近 Overlay；HUD 只能显示，不能点击。版本 A 的参考视口用打包在插件内的 three.js（`ui/vendor/`，MIT 许可）在 Palette 中渲染，不需要网络。

研究上可以比较：独立视口是否更利于专注理解参考设计；同一视口是否更利于把参考信息与自己的设计联系起来；两种界面如何影响用户在看教程和继续建模之间的切换。

## 界面（两个版本共有的部分）

插件打开教程窗口和右侧 Reasoning Reuse 面板，用户的模型留在 Fusion 画布中。下面以版本 B 为例；版本 A 的教程内容相同，只是排在参考视口右侧的纵向历史中。

### 教程

- **案例**：标题、**原设计师的设计目标**（为谁、在什么约束下）、来源说明；可同时打开多个案例并切换，各自记住进度。
- **当前步骤**：
  1. **Why this decision?**：设计师边建模边说出的推理摘要，标明来源（*Think-aloud while modeling* 或 *Illustrative*）；下面是与录音同步的文字稿（可开合成朗读）。
  2. **The decision**（设计师说到时）：问题、考虑过的因素、各选项及取舍、最终选择；这个选择是**通用做法**还是**只适合原设计师的目标**；它建立在哪些步骤之上（设计师说出的，与从 CAD 时间轴推导出的，分开显示）。
  3. **How it was modeled**：工具与参数（取自原 `.f3d`）、录屏片段。
- **底部步骤条**：横向步骤编号、前后跳转、播放／暂停、步骤内进度；**Whole process** 连续播放整个过程，**This step only** 只重访当前步骤；0.5×–2× 速度。
- **画布中**：参考模型随步骤演变（放在用户模型旁边，只读、不可选中）；有记录时显示 Ghost Pointer（橙色虚拟指针，从不移动真实鼠标）。

### 右侧：Reasoning Reuse

- **From my model**：在**自己的**模型上选中面、边或顶点 → 只读地找出生成它的特征（*History in Motion* 的过滤算法，分析后恢复时间轴标记）→ 列出所有打开的案例中相关的决策，说明为什么推荐（特征类型、名称中的作者标签、参数类型），并把**用户自己的参数值**与案例的选项并列（只作参考，不判断对错）。**Watch in example** 跳到案例中对应的步骤播放。
- **Across examples**：同一个设计问题在不同案例中的回答并排比较。
- **History in Motion · inspect**（默认关闭）：论文中的原位参数动画，勾选后才会临时修改用户模型的参数，结束后恢复。

## 案例从哪里来

每个案例来自一次**真实的设计过程**：设计师在 Fusion 中建模，**边建模边说**（think-aloud），同时录屏、录音。完整规范见 [`docs/EXAMPLE_FORMAT.md`](docs/EXAMPLE_FORMAT.md)；标注工具的设计见 [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) 分支。

| 步骤 | 工具 | 产出 |
|---|---|---|
| 1. 录制 | Fusion + 任意录屏软件 | 设计师的 `.f3d`、录屏、录音 |
| 2. 提取 | 教程窗口底部的 **Extract example draft…**：逐项回滚时间轴，记录每个特征之后的几何、参数，以及它使用的草图和特征 | `*.extract.json` |
| 3. 转写 | 任意转写工具 | 带时间戳的文字稿（`.srt` / `.vtt` / `.json`） |
| 4. 标注 | **案例标注工具**：边看录像边切分步骤、勾选对应特征、整理推理摘要；可选填写决策、适用范围、依赖 | `annotation.json` |
| 5. 合成 | `python tools/build_package.py draft.extract.json annotation.json transcript.srt --media session.m4a -o example.excadmple` | `.excadmple` 案例包 |

原则：推理只来自设计师说过的话，工具不生成推理；设计目标必填；自动提取的数据与研究者的标注分开保存，重新提取不会覆盖标注。

案例包是 ZIP：`manifest.json`（format `excadmple`，version 2）加上录音／录屏。每一步包含：几何状态序列（`snapshots`：这一步之前、以及每个特征之后的模型）、操作与参数、对应的 `.f3d` 特征、文字稿片段、录制时间切片（`media.offset_ms`）、推理摘要，以及可选的决策、适用范围和依赖。version 1 的旧包仍可读取。

### 附带示例

`examples/phone_stand.json`（九步）与 `examples/tablet_stand.json`（对照案例）是**人工编写的示例**（`provenance: authored / illustrative`），用于演示交互：几何、Ghost Pointer 与推理都不是真实录制，界面中标为 *Illustrative*。由 `python tools/build_examples.py` 生成。

## 安装

1. 下载本分支 ZIP 并解压，保持整个 `exCADmpleFusion` 文件夹完整（含 `exCADmpleFusion.py` 与 `exCADmpleFusion.manifest`）。
2. Fusion 中打开或新建一个 **Design**。
3. **Utilities → Scripts and Add-Ins → Add-Ins**，点 **+**，选中整个文件夹并运行。
4. 出现教程窗口（版本 B 浮在画布上；版本 A 为带参考视口的独立窗口）和右侧 Reasoning Reuse；示例自动打开。**Import** 打开 `.excadmple` / `.json` 案例包。关闭面板后可从工具栏的 **exCADmple Player** / **Reasoning Reuse** 按钮重新打开。

环境：Fusion Desktop（Windows／macOS），Fusion Python API；界面为本地 HTML/CSS/JS，无服务器、无外部前端库。

## 用户模型的安全边界

- 参考模型与 Ghost Pointer 是临时 **Custom Graphics**：不是可编辑的 Solid，不进入用户的时间轴；保存前清除、保存后恢复。播放案例**不会**调用 `timeline.play()` 或移动用户的时间轴标记。
- Reuse 面板的特征分析会临时回滚时间轴，结束（包括出错）后恢复原标记位置。
- **Linked CAD geometry / Focus Mode**（可选）：把案例步骤关联到当前文档中的 Body／Face／Occurrence，切换步骤时高亮并把无关 Body 暂时调暗到 24%。修改透明度前记录原值，并在切换步骤、替换案例、停止插件、切换文档以及**保存前**恢复；保存前恢复失败会取消保存。崩溃或其他插件同时修改外观时，可能需要手动恢复，请在模型副本上测试。
- **HiM inspect** 默认关闭；开启后修改的参数表达式在每个特征播放后、选中新几何时、保存前、切换文档和停止插件时恢复。Fusion 可能记录撤销步骤。

## 测试

```bash
python -m unittest discover -s tests -v     # 纯 Python 与模拟 Fusion 接口
node --check ui/player.js && node --check ui/him.js
```

**桌面端冒烟测试**（尚未完成，需要真实 Fusion）：

1. 启动插件，切换 Phone Stand 与 Tablet Stand，确认各自进度保留；播放第 4、5、8 步，确认几何逐步变化、Ghost Pointer 移动。
2. 自己建一个带 Fillet 的零件，选中圆角面，确认右侧出现相关决策与参数对照；点 **Watch in example** 跳转播放。
3. 确认未开启 inspect 时，自己的参数与时间轴不变；保存、关闭、重开，确认没有残留图形。
4. 用一个真实 `.f3d` 运行 **Extract example draft…**，检查装配体坐标与耗时；用 `tools/build_package.py` 合成后导入播放。

## 代码结构

```text
exCADmpleFusion.py        入口：两个面板、HTML 桥接、选择事件、保存安全、动画计时
core/packages.py          案例包校验与安全读取（v1 / v2）
core/animation.py         几何动画（snapshots、extrude、transition、pattern 等）
core/renderer.py          画布中的临时参考几何与 Ghost Pointer
core/pointer.py           Ghost Pointer 路径校验与采样
core/library.py           多案例与各自进度
core/reuse.py             决策匹配、参数对照、跨案例比较
core/reuse_fusion.py      Reuse 面板与 Fusion 的连接
core/him_filter.py        HiM 特征过滤算法（纯 Python）
core/him_motion.py        HiM 动画模型（20 种特征、计时、播放状态）
core/him_fusion.py        HiM 的 Fusion 适配与 inspect 动画
core/extract_fusion.py    从 .f3d 提取案例草稿
core/authoring.py         草稿 + 标注 + 文字稿 → 案例包
core/transcript.py        读取 .srt / .vtt / .json 文字稿
core/spatial.py, focus.py, geometry_links.py   关联几何与 Focus Mode
config.json               选择界面版本（overlay = B，reference = A）
ui/index.html|player.*    版本 B 的教程面板
ui/reference.*            版本 A 的 HiM 风格窗口（参考视口 + 纵向历史）
ui/shared/viewer.js       版本 A 的 3D 参考视口（three.js）
ui/shared/animation.js    几何动画的 JS 版本（与 core/animation.py 一致，有测试保证）
ui/shared/history_filter.js  版本 A 的按几何过滤历史
ui/vendor/                three.js r147（MIT）
ui/him.*                  右侧 Reasoning Reuse
tools/build_package.py    合成案例包
tools/build_examples.py   生成附带示例
docs/EXAMPLE_FORMAT.md    案例文件规范
```

## 已知限制

- 尚未在 Fusion 桌面端完成人工测试；提取尚未用真实 `.f3d` 验证。
- 录屏、录音使用本地文件 URL 播放，编解码兼容性取决于 Fusion WebView。
- 匹配用户特征与案例决策采用透明的规则（特征类型、作者标签、参数类型），不做语义理解。
- 参考几何为网格；`snapshots` 只显示录制到的状态，不在状态之间编造过渡。
- 主要面向单个活动文档。

## 参考

- *History in Motion*，Veuskens et al., SCF 2023（[DOI](https://doi.org/10.1145/3623263.3623358)）：按几何过滤特征与建模历史动画的思路来源。
- Fusion API：[Palettes](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Palettes_UM.htm) · [Custom Graphics](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomGraphics_UM.htm) · [Document events](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_documentSaving.htm)
