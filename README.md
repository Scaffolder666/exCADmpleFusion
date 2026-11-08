# exCADmple — Autodesk Fusion 插件 · 版本 A（History in Motion 式独立参考视口）


> **真实模型测试基准（2026-11-08）：** 后续原生 HiM 验收优先使用研究者提供的 `fusion.f3d`（324,089 bytes，SHA-256 以 [REAL_FUSION_MODEL_TEST.md](docs/REAL_FUSION_MODEL_TEST.md) 为准），而不是 Phone Stand 手工示例。测试模型不公开提交到仓库。通过 `tools/build_native_validation.py` 将真实 Fusion Timeline 提取结果与原始 `.f3d` 组成技术验证包。详见 [真实模型测试步骤](docs/REAL_FUSION_MODEL_TEST.md)。本段说明只改变测试基准，不改变现有播放器行为。


**Supporting Design Reasoning Through Shared CAD Models** · 分支 `fusion-him`

> 本分支是**版本 A**：教程在第二个 Fusion 窗口里、在设计师 `.f3d` 的副本上播放（按 *History in Motion* 的做法）；用户在第一个 Fusion 窗口里做自己的设计。代码与 [`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion)（版本 B）相同，只有 `config.json` 的 `"layout": "reference"` 和插件随 Fusion 启动不同。改动在 `fusion` 上进行，再合并到本分支。

在自己的 Fusion 里播放别的设计师录下来的设计教程：可以播放整个教程，也可以重播某一步、跳到下一步。每一步有模型怎么变化、用了哪些工具、鼠标轨迹，以及设计师当时说的话（think-aloud），可以听原声或用电子音朗读，同时显示文字。用户可以一边看，一边在同一个 Fusion 里做自己的设计。

项目概况见 [`main`](https://github.com/Scaffolder666/exCADmpleFusion)；Blender 版本见 [`blender`](https://github.com/Scaffolder666/exCADmpleFusion/tree/blender)。

## 两个界面版本（用于比较）

两个版本播放同样的教程，功能相同，只是教程放的位置不同。两个分支共用同一份代码，由 `config.json` 的 `layout` 选择。

| | 版本 A：独立参考视口（`fusion-him`，`"layout": "reference"`） | 版本 B：视口内 Overlay（`fusion`，`"layout": "overlay"`） |
|---|---|---|
| 教程在哪里播放 | 按 *History in Motion* 的做法，在**第二个 Fusion 窗口**里打开设计师 `.f3d` 的副本播放；用户在第一个 Fusion 窗口里建模 | 在用户自己的 **Fusion 画布**里，参考模型显示在用户模型旁边 |
| 看到的模型 | 设计师真实的参数化模型（副本），按 HiM 的方式展示：时间轴回滚到当前特征，参数从约 0 实时增长到实际值（Fusion 当场重算，不存帧），其他 Body 半透明；用户可以在那个窗口里随时旋转、查看 | 提取时记录的每个特征完成后的模型，显示在用户画布里，可以随画布一起旋转查看 |
| 控制面板 | 参考窗口右侧：播放／暂停／重播／前进／后退，纵向步骤列表，当前步骤展开显示工具和设计师说的话 | 浮在画布上的紧凑面板（可收起为只剩步骤条），画布左上角显示步骤标题和当前这句话 |
| 额外 | 在参考模型上选中面、边或顶点，只播放做出它的那些步骤（HiM 的过滤方法）；后退时倒放当前步骤 | — |

说明：版本 A 需要教程包里带设计师的 `.f3d`；附带的两个手工示例没有，所以在版本 A 里只显示记录的模型，也不能按几何选择。Fusion 原生画布不允许叠加可交互的 HTML，所以版本 B 的"Overlay"是浮动面板加画布内的 Custom Graphics（模型、指针、文字）。

## 目标交互与 HiM 验证标准

**设计原则：** exCADmple 向设计师呈现原作者的建模过程、操作与其本人表达的设计理由；系统**不需要理解用户当前的设计目标，也不替用户推理或推荐正确答案**。用户自行判断借鉴哪些步骤，并能随时继续编辑自己的 CAD 模型。

**版本 A（`fusion-him`）的目标流程：**

1. 用户在第一个 Fusion 窗口正常打开自己的设计文件。
2. 点击 **Load Example**，选择包含原设计师参数化 `.f3d` 的 `.excadmple` 案例包。
3. 打开独立的 Fusion 参考窗口，在**原设计师 CAD 模型的副本**上查看和旋转模型；第一个窗口仍用于用户自己的建模。
4. 按原始 Fusion Feature Timeline 顺序播放，或跳转、重播单个步骤。支持的 Feature 使用 **HiM 式真实参数驱动动画**：临时改变参数，由 Fusion 重新计算几何，而不是只播放预渲染视频或几何快照。无适用参数的 Feature 可以使用明确标注的淡入效果；Sketch 可以通过时间轴状态呈现。
5. 每步同步显示使用的工具、与几何的关键交互（例如选中 Profile、拖动 Manipulator 的方向或位置）、原设计师的语音和文字。**不要求记录与建模无关的鼠标运动。**
6. 用户随时回到第一个窗口继续建模，参考窗口不得修改或保存用户的模型。

**版本 B（`fusion`）** 以同一 Fusion Canvas 内的参考几何和教程 Overlay 呈现相同的设计过程信息；两个版本先分别实现，再决定论文采用哪个。两者底层动画机制目前不同，不应声称已经完全等价。

**完成判定（尚待 Fusion Desktop 实测）：** 使用一个真实录制的参数化 `.f3d` 案例，验证导入、步骤与 Feature 精确对应、Extrude/Fillet 等参数动画、跳转/暂停/恢复、语音文字同步、独立窗口连接、用户持续建模以及关闭后原模型不被修改。若 Feature 映射不明确，应报告未匹配，不能猜测或播放其他操作。当前录制器仅捕获工具启动和离散几何选择位置，**还不能还原真实 Manipulator 拖拽路径**；这一能力需单独验证或补充录屏标注。

## 播放

- **整个教程**连续播放，或**只播这一步**；每一步可以重播；上一步／下一步；0.5×–2× 速度。
- **声音**：播放这一步对应的那段原声（录音或录屏的声音）；没有录音时可以用电子音朗读文字稿。
- **文字**：这一步设计师说的每一句话，当前这句高亮；点某一句可以跳到那里。
- **模型和指针**：参考模型随步骤变化，鼠标轨迹显示为橙色的 Ghost Pointer（不会移动真实鼠标）。
- **关联几何**（可选）：可以把某一步关联到自己模型里的 Body／Face，切换到这一步时高亮它，并把其他 Body 暂时调暗。

## 教程文件和制作工具

教程就是录下来的东西：步骤、每一步说了什么、用了哪些工具、模型怎么变、鼠标轨迹。规范见 [`docs/EXAMPLE_FORMAT.md`](docs/EXAMPLE_FORMAT.md)。制作一个教程：

1. **录制**：设计师打开自己的设计，点工具栏 **exCADmple: Record tutorial**，同时开始录屏（带麦克风），边建模边说。插件记录用到的工具、每个特征出现的时间、选中的位置（作为鼠标轨迹）。结束时点 **Stop recording**，保存 `*.session.json`。
2. **提取**：在 Fusion 里打开完成的 `.f3d`，点教程面板底部的 **Extract tutorial draft…**，得到每个特征完成后的模型（`*.extract.json`）。
3. **转写**：把录音转成带时间的文字稿。可以用任意工具导出 `.srt`，或在本地运行 `python tools/transcribe.py session.mp4 -o transcript.srt`（需要 `pip install faster-whisper`）。
4. **切分步骤（AI）**：`python tools/author.py draft.extract.json transcript.srt --session tutorial.session.json --video session.mp4 --id phone-stand --title "Phone Stand" -o annotation.json`。Claude 根据特征出现的时间、用到的工具和设计师说的话，把录制切成步骤并起标题（尽量用设计师自己的话）；它不写任何推理。结果会自动检查，不合格时、加 `--no-ai`、或没有 API 凭据时，改用按特征的规则切分。需要 `pip install anthropic` 和 `ANTHROPIC_API_KEY`（或 `ant auth login`）。
5. **人工检查**：在浏览器里打开 `ui/author.html`，载入 `annotation.json`、文字稿、录屏（可选：提取草稿）。对着视频调整每一步的标题、起止时间和包含的特征，可以拆分或合并步骤，然后导出。
6. **合成**：`python tools/build_package.py draft.extract.json annotation.json transcript.srt --media session.mp4 --source Design.f3d -o phone-stand.excadmple`

附带的 `examples/phone_stand.json`（九步）和 `examples/tablet_stand.json` 是手工编写的示例，不是真实录制。由 `python tools/build_examples.py` 生成。

## 安装

1. 下载本分支 ZIP 并解压，保持整个 `exCADmpleFusion` 文件夹完整。
2. Fusion 中打开或新建一个 **Design**。
3. **Utilities → Scripts and Add-Ins → Add-Ins**，点 **+**，选中文件夹并运行。
4. 版本 B：教程面板浮在画布上，示例自动打开；**Import** 打开别的教程。版本 A：工具栏点 **exCADmple Reference window** 打开第二个 Fusion（需要在 Add-Ins 里勾选 **Run on Startup**，该分支默认已开启）；如果没有自动启动，手动再开一个 Fusion 运行插件即可，它会自动连接。

## 不会改动用户的模型

- 版本 B 的参考模型、指针和文字都是临时 Custom Graphics，不进入用户的时间轴；保存前清除、保存后恢复。
- 版本 A 在第二个窗口里打开的是 `.f3d` 的副本，从不保存；动画只作用于这个副本（不看当前活动文档是谁），副本不是活动文档时不做任何修改。临时改过的参数在步骤结束、切换步骤、停止、关闭、保存前以及某一帧出错时写回原表达式；暂停时保持在中间状态。
- 关联几何时调暗的透明度会在切换步骤、保存前、切换文档和停止插件时恢复；保存前恢复失败会取消保存。

## 版本 A：HiM 原生动画的状态

**参数驱动**（临时改 ModelParameter，由 Fusion 重算；只用下表的参数路径，没有“任意长度参数”的兜底；参数不存在（例如 Extrude 的 To Object 范围）或为 0 时改用视觉效果）：

| Feature | 动画的参数 |
|---|---|
| Extrude | `extentOne.distance`、`extentTwo.distance` |
| Revolve | `extentDefinition.angle`／`angleOne`／`angleTwo` |
| Fillet | 恒定半径 `radius`；变半径 `startRadius`／`endRadius`；弦长 `chordLength` |
| Chamfer | `distance`、`distanceOne`、`distanceTwo`（角度不动画） |
| Hole | `extentDefinition.distance`、`holeDiameter` |
| Circular／Rectangular Pattern | `totalAngle`；`distanceOne`／`distanceTwo` |
| Shell、Sweep、Offset Faces、Thicken、Draft、Thread、Coil | 见 `core/him_motion.py` 的 `FEATURES` |

**视觉回退**（高亮的结果 Body 从小到大、从透明到不透明出现，其他 Body 和结果本身临时调暗）：Mirror、Combine、Split Body、Split Face、Loft、Move，以及 Base/Copy-Paste/Import 等；参数动画中 Fusion 拒绝某个值或特征报错时，这一步也改用视觉效果并在面板标明原因。Sketch 和构造平面只按时间轴状态显示。其他 Feature 只滚动时间轴显示结果。

**步骤与时间轴的对应**：按记录的时间轴 index + 名称（+ 类型）匹配；index 变了时只接受唯一的同名同类型特征；重名、类型不符、一个特征被两步占用都报告为 “not found in the model”，不会动画别的操作。

**指针**：录制器只记录工具启动和离散的选择位置，没有 Manipulator 拖拽路径；面板在每一步写明“只有记录的选择”或“没有记录指针”，不会补造鼠标轨迹。

| | 已实现 | 单元测试（模拟 `adsk`） | Fusion Desktop 实测 |
|---|---|---|---|
| 步骤 ↔ 时间轴映射（重名、类型、占用、index 偏移） | ✓ | ✓ | 未测 |
| 参数从约 0 增长到原值、最后一帧等于原值 | ✓ | ✓ | 未测 |
| 结束／切换步骤／停止／关闭／出错时恢复参数、透明度、叠加图形 | ✓ | ✓ | 未测 |
| 时间轴回滚与恢复 | ✓ | ✓ | 未测 |
| 视觉回退及清理；参数被拒绝时回退 | ✓ | ✓ | 未测 |
| 只修改参考副本 | ✓ | ✓ | 未测 |
| HiM 几何过滤 | ✓ | ✓ | 未测 |
| Fusion 是否真的按参数重算、各 Feature 的 API 路径是否正确、帧率 | — | 无法用单元测试证明 | 未测 |
| 两个 Fusion 同时运行并连接 | ✓ | 连接协议 ✓ | 未测 |

**最终验收待 Fusion Desktop 实测。** 验收模型和步骤：`tools/fusion_demo`（在 Fusion 里运行，生成 Sketch → Extrude → Fillet → Sketch → Extrude → 构造平面 → Mirror 的真实 `.f3d` 和教程包），按 [`docs/FUSION_DESKTOP_TEST.md`](docs/FUSION_DESKTOP_TEST.md) 逐项检查。该脚本本身也尚未在 Fusion 里运行过。

## 空间引导（这一步改了哪里）

- **记录的模型**（没有 `.f3d`，例如附带的 Phone Stand）：把这一步的模型与上一步的模型按几何比较：与上一步完全相同的网格（顶点、三角形顺序不同也算相同，带容差）不变；其余网格里，落在上一步模型表面上的三角形不变（重新三角化不算改动），其余三角形就是这一步新增或修改的，用青色画出，其余部分照常灰色。第一步整个模型都是新的。只删除了几何的步骤不标记任何东西。播放中每一帧同样比较（超过 6000 个三角形时不逐帧比较）；暂停时保持；切换步骤、换教程、关闭时清除。
- **设计师的 `.f3d`**：青色画特征自己报告的面（`Feature.faces`，用临时 BRep 复制后绘制）；没有面时才画整个结果 Body；蓝色画从 API 读到的输入草图轮廓和边。步骤结束或选中某一步时保持，下一帧、切换步骤、停止和关闭时清除。
- 教程包没有记录实体引用，所以不使用；找不到对应关系时不标记。颜色没有设置项。高亮都是不可选的 Custom Graphics，不改动模型。

## 测试

```bash
python -m unittest discover -s tests -v
node --check ui/player.js && node --check ui/reference.js
```

尚未在 Fusion 桌面端实测。单元测试通过不等于 Fusion API 已验证；版本 A 的验收步骤见 [`docs/FUSION_DESKTOP_TEST.md`](docs/FUSION_DESKTOP_TEST.md)。

## 代码结构

```text
exCADmpleFusion.py        入口：教程面板、播放、保存安全；版本 A 的两个窗口
config.json               选择界面版本（overlay = B，reference = A）
core/packages.py          教程包读取与校验
core/animation.py         模型状态动画
core/renderer.py          画布中的参考模型、Ghost Pointer、文字
core/pointer.py           鼠标轨迹
core/link.py              版本 A：两个 Fusion 之间的本机连接
core/him_reference.py     版本 A：在设计师模型副本上播放（HiM 参数动画、按几何过滤）
core/reference_plan.py    版本 A：步骤与时间轴特征的对应
core/him_filter.py, him_motion.py, him_fusion.py   History in Motion 的过滤算法与参数动画
core/extract_fusion.py    从 .f3d 提取教程草稿
core/authoring.py, transcript.py   合成教程包、读取文字稿
core/spatial.py, focus.py, geometry_links.py      关联几何
core/step_changes.py      空间引导：比较相邻两步的记录模型，找出这一步新增或修改的三角形（青色）
ui/index.html, player.*   版本 B 的面板
ui/reference.*            版本 A 的控制面板
core/session_log.py, session_recorder.py   制作：录制时记录工具、特征时间、选中位置
core/ai_segment.py        制作：把录制切成步骤（Claude 提议 + 规则兜底 + 检查）
ui/author.html            制作：在浏览器里对着视频检查、调整步骤
tools/fusion_demo/        Fusion 脚本：生成版本 A 的验收模型和教程包（tools/demo_tutorial.py）
tools/                    author.py（切分步骤）、transcribe.py（本地转写）、build_package.py（合成）、build_examples.py（示例）
```

*History in Motion*：Veuskens et al., SCF 2023（[DOI](https://doi.org/10.1145/3623263.3623358)）。
