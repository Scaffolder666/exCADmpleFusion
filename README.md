# exCADmple

**通过共享 CAD 模型支持设计推理的复用（Supporting Design Reasoning Reuse Through Shared CAD Models）**

exCADmple 是一个人机交互（HCI）研究原型，探索设计师如何在**进行自己的三维设计时，参考他人的建模过程、操作和设计决策**。

一个完成的 CAD 模型告诉我们「**做出了什么**」，传统教程通常侧重「**怎样复现**」。exCADmple 希望进一步呈现「**为什么这样设计**」：将其他设计师的 Design Reasoning 与三维建模过程联系起来，让用户能够直接在自己的 CAD 工作环境中探索和借鉴。

## 研究目标与使用流程

系统围绕**用户自己的设计过程**组织，而不是要求用户线性地完成某个教程：

1. **继续自己的设计**：用户在正常的 CAD／三维建模视口里创建和修改模型。
2. **打开一个 Design Example（设计案例）**：将预先准备的参考模型加载到同一个建模空间，放在用户模型旁边。
3. **探索案例的设计过程**：观察几何如何逐步变化、使用了哪些 CAD 功能与参数、虚拟指示点如何表示选择和拖动，并同步听取设计师对决策的解释。
4. **回到自己的设计**：用户可以借鉴某个操作、调整一项设计决策，或选择与案例不同的方案，无须退出建模环境。
5. **再参考其他案例**：随着设计问题的变化，加载新的 Example，必要时重新访问之前看过的案例。

**用户自己的模型始终是主线；Design Examples 是可以在设计过程中反复查阅的参考资料，而不是必须照着完成的作业。**

### 三个学习层次

| 层次 | 用户能够了解什么 |
|---|---|
| **Why — Design Reasoning（为什么）** | 设计目的、约束、权衡、替代方案，以及做出决策的原因 |
| **What — CAD Functions（用了什么）** | 用到了哪些建模功能、操作和参数 |
| **How — Modeling Interactions（怎么操作）** | 几何如何变化、选中了什么、如何拖动以及怎样执行 Extrude 等操作 |

这三个层次都与**同一个 Design Example 的建模步骤**同步关联。

## 核心交互设想

- **单个 3D Viewport**：不拆分为 Rhino 式多视口，也不另开独立教程窗口。
- **参考模型与用户模型共存**：两者位于同一个三维工作空间，参考几何单独管理并避免被误选中。
- **视口内的 HiM 风格播放器**：包含步骤卡片、播放／暂停、跳转、进度控制、操作信息和简短的设计推理说明。
- **Ghost Pointer（虚拟操作指示点）**：以点、短轨迹和点击反馈展示案例中的操作；**不会移动或接管用户真实的鼠标**。
- **同步内容**：参考模型的几何变化、操作提示、语音、字幕和 Reasoning 随案例播放呈现，用户仍可进行自己的设计。
- **多案例探索（计划中）**：用户可切换不同的 Design Examples，返回之前的案例，并保留自己模型的状态。

## 当前 Proof of Concept

目前最完整的技术原型是基于 **Blender 4.5** 的预设 **Phone Stand（手机支架）九步骤案例**。它演示了累积式几何变化、预设 Ghost Pointer、步骤级设计理由、字幕以及合成语音。

| 步骤 | 建模过程 | 对应的设计考虑 |
|---|---|---|
| 1. Establish the Footprint | Sketch / Extrude 底座 | 稳定性与底座面积 |
| 2. Choose a Viewing Angle | 建立并倾斜支撑背板 | 观看角度与使用情境 |
| 3. Add a Retaining Lip | Sketch / Extrude 前挡板 | 防止手机滑落 |
| 4. Round Base Edges | Bevel / Fillet | 接触舒适性与有效支撑面积 |
| 5. Charging Cable Passage | Boolean Cut | 充电线通道与手机固定 |
| 6. Reinforce Back Support | 添加一对支撑肋 | 结构刚度与材料用量 |
| 7. Add Anti-Slip Pads | 四个防滑垫 | 摩擦力与底座大小 |
| 8. Lighten Back Support | Boolean Cut 背板开孔 | 减重与结构强度 |
| 9. Check Phone Fit | 临时手机模型进行装配检查 | 尺寸、倾角与间隙 |

**重要说明：** 这是**人工编排的合成示例**，不是某位设计师真实 CAD 会话的录制。语音为合成旁白，部分动画是操作的可视化重演，而非真实的原生 CAD 命令回放。系统目前也**不能**从完成的模型自动推断真实设计意图。

## 两个固定开发分支

目前只维护两个长期开发分支。今后的功能和修复会**直接提交到对应分支**，不再层层创建功能分支。

| 分支 | 内容 | 当前状态 |
|---|---|---|
| **[`blender`](https://github.com/Scaffolder666/exCADmpleFusion/tree/blender)** | [Blender 安装及技术说明](https://github.com/Scaffolder666/exCADmpleFusion/blob/blender/blender/README.md) | 单视口播放器、Ghost Pointer、九步 Phone Stand 和合成旁白；Blender 无界面自动化测试通过，桌面 GPU/UI 交互仍待验证 |
| **[`fusion`](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion)** | [Autodesk Fusion 原型与安装说明](https://github.com/Scaffolder666/exCADmpleFusion/blob/fusion/README.md) | 较早的 Fusion 技术原型，在原生 Fusion 建模空间中展示只读参考模型 |

默认的 `main` 分支用于展示**项目概况**，目前**不包含可运行的完整插件**。下载与试用时，请切换到相应的开发分支。

### 尚未完成的重要功能

Blender 原型目前只有**一个**预设 Phone Stand 案例，还不能在多个独立的 Design Examples 之间切换，也不能为每个案例单独保存播放进度。案例播放暂时共用 Blender 的 Scene 时间轴和 FPS；这些都是后续需要解决的问题，**不是当前已经实现的能力**。

当前阶段暂不处理任意 CAD 文件的历史自动还原、视频自动转换为教程、或面向用户的完整 CAD 命令目录。先用少量经过编排的案例研究 Design Reasoning Reuse。

## 如何试用

- [Blender 分支](https://github.com/Scaffolder666/exCADmpleFusion/tree/blender)：参照 [Blender 安装与测试说明](https://github.com/Scaffolder666/exCADmpleFusion/blob/blender/blender/README.md)。
- [Fusion 分支](https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion)：参照 [Fusion 原型说明](https://github.com/Scaffolder666/exCADmpleFusion/blob/fusion/README.md)。

## 研究启发

三维建模历史动画和纵向步骤播放界面受到 *History in Motion（HiM）* 的启发（[ACM DOI: 10.1145/3623263.3623358](https://doi.org/10.1145/3623263.3623358)）。

exCADmple 关注的不是单纯检查一个 CAD 模型的历史，而是：**当用户正在设计自己的产品时，如何通过探索多个案例的建模过程及设计师表达的推理，支持设计知识与 Design Reasoning 的复用。**

---

**研究原型，持续开发中。** 当前目标是用预先制作的案例验证交互方式，而不是提供可直接用于生产的 CAD 教程平台。
