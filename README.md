# exCADmple

**Supporting Design Reasoning Through Shared CAD Models**

设计师通过分享 CAD 模型和教程来交流与复用设计。共享的模型提供了最终几何和建模步骤，却很少说明设计师**为什么**做出这些决定；CAD 教程通常带用户一步步复现模型，较少关注决策背后的推理。因此，想在他人设计基础上继续工作的用户，可能明白模型是怎么建出来的，却难以根据**自己的设计目标**判断哪些选择应该保留、哪些应该重新考虑。

**exCADmple** 让用户直接在自己的 CAD 工作空间中探索他人的设计过程与推理。通过交互式时间轴，用户可以播放整个设计过程，也可以重访单个步骤。每一步展示模型如何演变、原设计师如何执行相应的 CAD 操作，并同步播放解释设计选择的语音与文字。用户可以完整跟随案例，也可以在同一工作空间中发展自己的设计时，有选择地借鉴个别步骤——用原设计师的推理辅助自己的决定，而不受示范做法的约束。exCADmple 支持用户学习的不只是**怎么建模**，还有**怎么设计**。

![界面概念示意图：同一视口中的参考模型与用户模型、Ghost Pointer 和教程播放器](docs/preview.svg)

*示意图，非软件实拍。* [交互式浏览器预览](https://html-preview.github.io/?url=https://github.com/Scaffolder666/exCADmpleFusion/blob/blender/docs/preview.html)（第三方 HTML Preview 服务；不含真实建模功能）。

## 用户如何使用

1. **在自己的 CAD 工作空间中设计**：用户的模型始终是主线。
2. **打开一个或多个设计案例**：参考模型放在用户模型旁边，只读、不可选中，不改动用户的模型与时间轴。
3. **探索设计过程**：播放整个过程或重访某一步，同时看到：
   - **How**：模型如何演变；原设计师执行了哪些 CAD 操作、参数是多少（录屏片段或 Ghost Pointer）；
   - **Why**：设计师边建模边说出的推理（同步语音与文字稿）；
   - **The decision**（若设计师说到）：当时的问题、考虑过的选项与最终选择；这个选择是通用做法，还是只适合原设计师的目标；它建立在哪些步骤之上。
4. **回到自己的设计**：借鉴、改编，或根据自己的目标做出不同选择。
5. **对照其他案例**：同一个设计问题，不同设计师可能给出不同答案。

## 案例从哪里来

每个案例都来自一次**真实的设计过程**，研究者用案例制作工具把它整理成可播放的案例包（规范：[EXAMPLE_FORMAT.md](https://github.com/Scaffolder666/exCADmpleFusion/blob/fusion/docs/EXAMPLE_FORMAT.md)）：

| 步骤 | 做法 | 来源性质 |
|---|---|---|
| 1. 录制 | 设计师在 Fusion 中完成设计，**边建模边说**（think-aloud），同时录屏、录音 | 录制 |
| 2. 提取 | exCADmple 插件逐项回滚 `.f3d` 时间轴，导出每个特征之后的几何、参数及特征间的依赖 | 自动提取 |
| 3. 转写 | 录音转为带时间戳的文字稿 | 录制 |
| 4. 标注 | 在**案例标注工具**中边看录像边切分步骤、对应特征、整理推理摘要；设计师说到的决策、适用范围与依赖可选填写 | 研究者标注 |
| 5. 合成 | 生成 `.excadmple` 案例包，Fusion 与 Blender 都能播放 | 自动 |

原则：推理只来自设计师说过的话，工具不生成推理；设计目标（brief）必填，让用户知道原设计师是为谁、在什么约束下做出这些选择；自动提取的数据与研究者的标注分开保存。标注工具的设计见 [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) 分支。

## 分支

为了决定论文采用哪种界面，Fusion 上做了**两个功能相同、界面组织不同**的版本：

| 分支 | 职责 |
|---|---|
| `main` | 本页：项目介绍与共同研究目标 |
| [`fusion-him`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him) | **版本 A：独立参考视口**（参考 *History in Motion*）。参考案例在单独窗口的交互式 3D 视口中播放，右侧是纵向历史；点击案例模型可找出制作这部分的步骤并播放。用户在 Fusion 原生画布中继续建模 |
| [`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion) | **版本 B：Fusion 视口内 Overlay**。参考模型与用户模型同在 Fusion 画布中；教程以浮在画布上的紧凑面板和固定在画布角落的 HUD 文字呈现。[说明](https://github.com/Scaffolder666/exCADmpleFusion/blob/fusion/README.md) |
| [`blender`](https://github.com/Scaffolder666/exCADmpleFusion/tree/blender) | Blender 原生 Overlay 原型：单视口 GPU 教程栏、独立的案例播放时钟、多案例切换，读取同一种案例包。[说明](https://github.com/Scaffolder666/exCADmpleFusion/blob/blender/blender/README.md) |
| [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan) | 所有版本共用的真实案例制作流程（标注工具） |

两个 Fusion 版本使用相同的案例、相同的推理内容和相同的播放能力，共用同一份代码，只由 `config.json` 中的 `layout` 区分。可以比较：

- 独立视口是否更容易专注理解参考设计；
- 同一视口是否更容易把参考信息与自己的设计联系起来；
- 两种界面如何影响用户在看教程和继续建模之间的切换。

技术上，Fusion 原生画布不允许插件叠加可交互的 HTML，所以版本 B 用浮动面板加画布内的 Custom Graphics（参考模型、Ghost Pointer、HUD 文字）尽量接近 Overlay；Blender 则可以直接在视口中绘制并接收点击。

## 当前状态

- 附带两个**人工编写的示例**（九步 Phone Stand、对照用 Tablet Stand），用于演示交互；它们的几何与推理不是真实录制，界面中标为 *Illustrative*。
- 真实案例的完整流程（录制 → 提取 → 标注 → 播放）已有格式与工具，尚待第一个真实案例验证。
- 两个插件都通过了自动化测试（Fusion 端为纯 Python 与模拟接口测试；Blender 端在真实 Blender 4.5 中运行），但尚未完成桌面端的人工交互测试。

## 研究启发

建模历史动画与按几何过滤特征的思路来自 *History in Motion*（Veuskens et al., SCF 2023，[DOI](https://doi.org/10.1145/3623263.3623358)）。exCADmple 关注的不是检查一个模型的历史，而是**用户在设计自己的产品时，如何借鉴他人表达的设计推理**。

---

研究原型，持续开发中。
