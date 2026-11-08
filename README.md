# exCADmple — HiM 风格的 Fusion 历史探索版

**独立实验分支：`fusion-him`，基于 `fusion` 创建。**

这是 [exCADmple](https://github.com/Scaffolder666/exCADmpleFusion) 的 Autodesk Fusion 版本。项目探索如何在自己的 CAD 设计过程中，探索并复用其他设计师在预设案例中表达的 **Design Reasoning（设计推理）**。

三个版本分别维护：[`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion) 是设计理由优先的左侧教程版；[`blender`](https://github.com/Scaffolder666/exCADmpleFusion/tree/blender) 是单视口九步动画版；本分支 [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him) 是操作历史优先的实验版。


## Blender 功能对齐进度（2026-11）

- **逐步几何**：当前三个 Phone Stand 步骤各有不同的累积 Mesh 快照；第一步有逐帧 Extrude 预览，第二、三步采用逐帧 Mesh Reveal 过渡（解释性动画，并非原生命令回放）。新增 `tests/test_him_playback_contract.py` 检查每一步有几何快照、组成不同，且具备按时间排序的字幕。**这仍不等于 Blender 九步完整的逐操作几何动画。**
- **字幕**：每步时间戳 `cues` 与播放时钟同步；用户可关闭字幕。
- **合成语音**：可选的 `Synthetic cue narration` 使用内嵌 WebView 的 `speechSynthesis` 朗读当前操作提示；有实际音视频资源时不启用。此功能不是 Blender 分支中打包的九段 WAV，Fusion WebView 的兼容性需要桌面实测。
- **仍待移植**：九步累积 Phone Stand 几何（包括 Bevel、Boolean、支撑肋、防滑垫和手机适配检查）、三维锚定 Ghost Pointer、内部 20 操作动画目录及对应 Fusion 端集成验证。**不要把当前三步演示视为与 Blender 完全功能对齐。**

## 这个版本有什么不同

白底左侧面板以**纵向建模历史卡片**为主，展示步骤名称、CAD 操作和前两个参数。选中一步后，下面显示操作细节、设计理由、媒体与关联几何。

- **Current step（默认）**：只播放当前操作，到结尾停止，便于逐项观察。
- **Full example**：按案例顺序自动播放到最后一步。
- **Replay step**：从当前步骤起点重新播放，保留当前播放范围选择。
- **关联几何与 Focus**：沿用 Fusion 版已有的手动关联和高亮机制。

参考 [History in Motion, SCF 2023](https://doi.org/10.1145/3623263.3623358) 的历史探索思路。此版本不是 HiM 复刻：没有从选中 Face/Edge 自动追溯特征依赖，也没有新增 Revolve、Fillet、Pattern 的原生参数动画。已有预计算 Extrude 与步骤快照继续工作。Reasoning 仍保留，因为 exCADmple 关注操作与设计理由的复用。

**切换版本时先停止另一个 Fusion 插件版本。** 两个分支共用插件入口与会话标识，不应同时运行。

本插件允许用户**在同一个 Fusion 工作空间中，一边探索参考案例，一边继续建立自己的模型**。参考案例使用独立的数据驱动时间轴，不会移动用户原生 Fusion Feature Timeline 的历史标记。

**当前仍是技术验证原型，不是完成的研究系统。** 它不会自动捕获或推断设计师的理由、真实执行原作者的 CAD 命令，也不能自动将视频转成结构化设计案例。

## 当前已实现的功能

- 从普通 JSON 或压缩的 `.excadmple` 文件载入结构化案例。
- 浏览步骤、自动播放、暂停、在步骤内拖动进度，以及前后跳转。
- 显示 CAD 工具、参数、带时间戳的操作提示和案例附带的文字 Reasoning。
- 当案例提供媒体文件时，按步骤播放操作视频或单独的音频。
- 如果案例缺少真实的逐步几何快照，可以显示附带的最终模型预览，并明确标注其**不是对应步骤的模型状态**。
- 通过 Fusion `Custom Graphics` 在三维画布中展示每个步骤的**只读参考几何**。案例播放独立于用户原生的 CAD 历史。
- 用户可以在同一个 Fusion 文档中创建和修改自己的 Sketch、Body、Feature；切换案例步骤**不会回滚用户的 Feature Timeline**。
- 文档保存前暂时清理参考图形，保存后恢复，避免把临时显示误留在文件里。

当前附带的 Phone Stand 是**说明性质的测试案例**：包含三个网格快照和示例推理文本，**没有真实设计师录制的语音或视频**；但可用于验证播放计时与操作提示。

## 在 Autodesk Fusion 中安装

1. 下载本仓库的 **`fusion-him` 分支 ZIP** 并解压。
2. 保持所有插件文件位于同一个 `exCADmpleFusion` 文件夹中，包括 `exCADmpleFusion.py` 和 `exCADmpleFusion.manifest`；**不要只安装 `ui` 文件夹**。
3. 打开 Fusion，新建或打开一个 **Design** 文档。
4. 进入 **Utilities → Scripts and Add-Ins → Add-Ins**，点击 **+**，选中整个 `exCADmpleFusion` 文件夹，并运行插件。
5. 左侧会出现 **exCADmple** Palette。切换案例步骤时，只读参考网格会更新，而用户原生建模记录保持不变。
6. 使用 **Import example** 导入自己的 `.json` 或 `.excadmple`。关闭 Palette 后，可以使用工具栏上的 **exCADmple Player** 按钮重新打开，或重启插件。

测试案例的参考几何有意放在文档原点右侧**约 14 cm** 的位置。这是显示用的参考对象，**不是可编辑的 Fusion Solid**。用户可以在同一文档中继续设计自己的模型。

**环境：** Fusion Desktop（Windows/macOS）、Fusion Python API；界面由 HTML/CSS/JavaScript 构成，不依赖服务器或外部前端库。

## Design Example 文件格式（v1）

一个案例是 JSON 对象，包含 `format: "excadmple"`、`version: 1`、`title` 和有序的 `steps` 数组。主要字段：

| 字段 | 作用 |
|---|---|
| `id`、`title`、`duration_ms` | 步骤标识、标题与播放时长 |
| `goal` | 该步骤的设计目的 |
| `geometry.meshes` | 只读三角网格快照；顶点单位为 **cm**，面采用三角形顶点索引 |
| `operation.tool`、`instruction`、`parameters` | 对应 CAD 功能、操作说明与参数 |
| `reasoning.text` | 案例作者提供的设计推理或解释 |
| `cues[]` | 步骤内部带时间戳的操作提示 |
| `media.audio`、`media.video` | 可选媒体文件的**相对路径** |

完整示例见 [`examples/phone_stand.json`](examples/phone_stand.json)。

便携的 `.excadmple` 文件本质上是 ZIP，包含 `manifest.json`（沿用相同 Schema）和通过相对路径引用的媒体文件。例如：

```text
phone-stand.excadmple  (ZIP)
├── manifest.json
├── audio/
│   └── step-2.m4a
└── video/
    └── step-2.mp4
```

对于真实 CAD 模型的演示，压缩包可包含 `source/Caster_Wheel.f3d` 和 `previews/final.png`。目前需要用户**手动**在 Fusion 中打开原始 F3D，再在播放器中导入对应案例包。如果没有逐步骤 Mesh，播放器只能展示最终预览与步骤信息，**不能宣称已经还原原作者的 Feature Sequence**。从源文件精确抽取真实步骤状态仍是后续工作。

操作视频用于展示原作者如何使用 Fusion；插件**不会移动真实系统鼠标，也不会自动点击 Fusion 工具栏**。三维画布中展示的是当前步骤的参考几何，而不是原作者的全部鼠标瞬间操作。媒体使用本地 File URI 播放，音视频编解码兼容性需要在具体系统上的 Fusion WebView 中测试。

**关于研究证据：** Reasoning 应尽可能来自设计师本人表达的意图，不能把未经验证的 AI 推断当成作者真实理由。当前案例数据需要预先制作；从录制视频中自动生成案例不属于这一阶段的范围。

## Step-to-Geometry Linking（步骤与几何关联）

插件允许用户把一个 exCADmple 设计步骤关联到当前 Fusion 文档的真实几何。对 Caster Wheel 等尚未导出完整逐步 Mesh 历史的模型尤其有用。

1. 在 Fusion 中打开源 `.f3d`。
2. 启动插件，并导入对应的 Example Package。
3. 在 exCADmple 面板中选择一个步骤。
4. 在 Fusion 画布或 Browser 中**仅选择一个** BRep Body、Face 或 Occurrence。操作前应处于正常 **Select** 状态，而不是正在执行 Sketch/Extrude 命令。
5. 展开 **Linked CAD geometry**，点击 **Link selected**。
6. 跳转其他步骤再返回：关联的对象会出现暂时的半透明蓝色高亮。关联 Face 时，目前高亮其**父级 Body**，不是只高亮单独 Face。
7. 点击 **Locate in Fusion** 可以对关联对象执行原生选择（包括单个 Face）；点击 **Unlink** 删除关联。

实现使用 `UserInterface.activeSelections`、`entityToken`、`Design.findEntityByToken` 和 `CustomGraphicsGroup.addBRepBody`。高亮本身不修改 Body 的外观、透明度、参数或原生 Timeline。只有用户主动点击 **Locate** 时才会更新当前 Fusion Selection；切换播放步骤不会自动选中对象。

**当前限制：**

- 几何关联只保存在**内存中**：停止/重启插件或导入其他案例后会丢失；不会自动写入 F3D、Example Package 或 GitHub。保存重开可能需要重新关联。
- `entityToken` 只在对应 Design 内解析，不适用于任意复制的模型。若因面分裂等变化出现多个匹配，插件会要求重新关联，而非猜测。
- Occurrence 高亮目前覆盖其中的 BRep Body，不覆盖 Mesh Body，也不会递归处理所有子级 Occurrence。
- Face 关联采用父 Body 高亮；精确 Face 选择需通过 **Locate**。Assembly Proxy Transform 仍需桌面验证。
- 用户必须手动判断当前几何和案例占位步骤之间的对应关系；**这不是从 F3D 恢复原作者建模历史或真实理由**。
- 真实模型被修改后，原有链接可能失效。这种关联适用于案例编排和检查，还不能视为跨文件稳定的引用格式。

**Caster Wheel 手动冒烟测试：** 打开 Caster Wheel F3D 及相应的预览型 `.excadmple`，将真实 Wheel Body 关联到一步；切换步骤并检查蓝色高亮；点击 **Locate** 确认原生选择；用 **Play** 检查是否只更新案例，而不改变 Fusion 历史标记；保存重开，确认没有遗留 Custom Graphics。不要把最终预览视为已经抽取的真实历史状态。

## Focus Mode（突出关联几何）

**Linked CAD geometry** 中包含 **Focus on linked geometry**，对于手动关联的源模型几何默认开启。

切换到具有有效关联的步骤时，播放器会：

1. 恢复上一次修改过的 Body 透明度；
2. 保持当前关联 Body（或关联 Face 的父 Body、关联 Component 的 Body）原有透明度；
3. 将无关、可写的原生 BRep／Mesh Body 调暗至 **24% Opacity**；
4. 对当前关联 BRep 绘制临时的低透明度蓝色高亮。

取消 **Focus on linked geometry** 后，恢复其他 Body 的透明度，仅保留蓝色高亮。

### 显示安全与恢复机制

参考 FuzzyCAD 的透明度管理方式，系统在修改任何 Body 的 Opacity 前记录其原值，不覆盖本来就更透明的对象，并在**步骤变化、案例替换、插件停止、文档失活以及 Fusion 保存前**尝试恢复原值。如果在 `documentSaving` 中恢复失败，会请求取消保存，避免静默保存被修改的显示状态。

不过，Fusion 的原生 Opacity Override 确实会暂时改变文档显示属性，**不是独立的后处理图层**。如果系统崩溃、Fusion 意外退出、插件卸载失败、其他 Add-in 冲突或 API 错误，仍可能需要手动恢复。完成桌面验证之前，**请在模型副本上测试**。

对于被选中 Component 共享的 Source Body，系统会保护这个原生来源，因而该来源的多个 Occurrence 可能同时保持不透明。当前不能对共享同一来源的多个 Instance 分别调暗；聚焦父级装配时，也会排除其嵌套子级 Occurrence。

Appearance Override、Active Component 可见性和外部链接模型等因素，可能让实际看到的透明度不同于 24%（参见 [Fusion BRepBody.opacity](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_BRepBody_opacity.htm)）。每个会话最多处理 **250 个背景原生 Body**。

### 在真实装配模型上测试 Focus

1. 复制一份 Caster Wheel F3D，**不要直接修改原文件**。
2. 选取一个 Wheel BRep Body，关联到某一步，保持 Focus 开启。
3. 确认 Wheel 清晰显示，周围 Fork/Mount 几何半透明。
4. 切换步骤，确认旧 Opacity 被恢复，再切换新的聚焦对象。
5. 取消 Focus，检查背景几何的数值 Opacity 是否准确恢复。
6. 再次开启 Focus，保存副本、关闭并重开，确认原始外观保持正常，没有残留高亮。
7. 若安装了其他会修改外观的 Add-in（如 FuzzyCAD），测试时先暂时关闭，避免多个系统同时管理 Opacity。

`tests/test_focus.py` 使用纯 Python 验证透明度恢复和失败处理，但真实画布渲染与文档生命周期还需要 Fusion 桌面测试。

## v0.5 — 画布内的 Extrude 动画（实验性）

某些案例步骤可以附带**预先计算、非破坏性**的三维 Extrude 动画。选择 Phone Stand 的第一步，然后点击 **Play** 或拖动步骤进度条：一个只读 `Custom Graphics` Mesh 会从 Sketch 平面逐渐增长为完整拉伸体；面板同步展示操作细节与 Reasoning。**Pause** 停止在当前参考形态，步骤结束时显示完整模型。

`animation` 数据独立于用户的原生 CAD Timeline：

```json
{
  "animation": {
    "type": "extrude",
    "profile": [[0,0,0],[10,0,0],[10,8,0],[0,8,0]],
    "direction_cm": [0,0,0.7],
    "cap_triangles": [[0,1,2],[0,2,3]],
    "context_meshes": []
  }
}
```

所有长度以 **cm** 表示，这是当前使用的 Fusion 内部长度单位。 `profile` 按周界顺序给出顶点，`cap_triangles` 通过顶点索引定义端面。动画会根据当前播放进度生成不同拉伸长度的三角棱柱。测试案例故意只使用简单凸四边形。

**技术边界：** 这是可视化的 Extrude Preview，**不是修改 Fusion 原生 `ExtrudeFeature` 的动画**。当前不支持 Join/Cut Boolean 更新、多个轮廓环／孔洞、Taper、弧线、Revolve、Fillet 或稳定的 Feature 来源追踪。除非案例包由真实源 Feature 与 Profile 元数据产生，否则不能认定预览动画与源模型的实际操作完全一致。

Timeline 事件约限制在每秒 **7 次 Custom Graphics 重绘请求**，并非视频帧率。Fusion 桌面性能尚未实测。渲染由 Fusion 本地 API 事件驱动，不修改用户原生几何、参数或 Timeline Marker。

先前的 Caster Wheel 案例包**没有抽取的 Feature 动画**，所以播放时仍只显示预览和步骤元数据。要准确播放真实 Caster Wheel 操作，后续 Importer 必须检查其 Fusion Feature History，提取对应轮廓、参数和操作前后的上下文；曲线轮廓或 Boolean 则需要比当前多边形拉伸更通用的网格策略。

### 与 History in Motion（HiM）的关系

Veuskens 等人在 SCF 2023 的 [*History in Motion*](https://doi.org/10.1145/3623263.3623358) 中展示了依据 Face／Edge 过滤相关 Feature、渐进改变 Extrude／Revolve／Fillet／Pattern 参数，以及对不适合参数动画的操作采用淡入淡出等方式。他们的原型使用**两个通过 WebSocket 相连的 Fusion 实例**，以满足当时 Fusion 原生 UI 中独立交互式 3D 视口的需求。

exCADmple 的这个 MVP 借鉴的是**动画呈现原则**，而不是原代码实现。它直接在同一个 Fusion Canvas 中，根据验证后的数据生成临时 Mesh，而不是通过第二个 Fusion 实例修改原生 Feature 参数。这保留了用户自己的 CAD 建模历史，同时将 Feature 依赖抽取与全面的操作复现留给未来工作。

## 代码结构

```text
exCADmpleFusion.py          Fusion 入口、HTML Bridge 与保存安全处理
exCADmpleFusion.manifest    Fusion Add-in 元数据
core/packages.py           案例包验证与安全 ZIP 读取
core/renderer.py           Fusion 画布中的临时只读 Mesh
ui/index.html              播放器界面
ui/player.css              界面样式
ui/player.js               独立的播放时间轴、媒体和提示
examples/phone_stand.json  三步骤参考几何与 Reasoning
tests/test_packages.py     纯 Python 案例包测试
```

播放只会改变参考 `Custom Graphics Group`，**不会调用 `Design.timeline.play()` 或修改 `markerPosition`**。用户原生 Feature Tree 仍完全属于用户。

## 测试方法

不启动 Fusion，也可以先检查 Python 数据解析与基础逻辑：

```bash
python -m unittest discover -s tests -v
```

**Fusion 桌面端手动集成测试：**

1. 新建设计文档，启动插件。
2. 在三个步骤之间跳转，确认 Canvas 中的参考 Mesh 随之变化。
3. 创建自己的 Sketch 与 Extrude，再次导航案例。
4. 检查自己的 Feature History 是否保持不变。
5. 保存、关闭、重开文档，检查是否留下临时图形。
6. 导入第二个案例，停止并重启插件，检查 Palette 与参考图形是否正确清理。

## 已知限制与下一步

- 演示包没有真实作者录制的会话，需要用户提供媒体素材来验证同步回放。
- CAD 操作与参数主要通过元数据／视频呈现，**不会在原生 Fusion 对话框中真实重演点击**。
- 基础播放主要按步骤更换参考几何；更平滑的步骤内变化仍依赖预先准备的动画元数据。
- `Custom Graphics` 在保存／重开、原生建模工具交互以及大型 Canvas 中的性能，**尚未在已安装的 Fusion 桌面版本上完整验证**。
- 媒体使用本地文件 URL；Fusion WebView 与系统解码器的兼容性需要真实环境测试。
- 当前主要面向单个 Active Document，不支持多文档之间的参考案例路由。
- 后续研究需要关注用户能否借鉴其他设计师的推理来支持自己的方案，而不只是准确模仿 CAD 操作。

## 官方 API 参考

- [Fusion Palette UI](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Palettes_UM.htm)
- [Fusion Custom Graphics](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomGraphics_UM.htm)
- [Fusion Add-In Manifest](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm)
- [Fusion Document Save Events](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_documentSaving.htm)
