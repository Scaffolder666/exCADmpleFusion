# exCADmple — Native Blender Interactive Tutorial

这是一套基于 **Blender 原生 Modeling Operators** 的交互式教程 Add-on。它不是另一套 Extrude、Bevel、Inset 的自研建模算法。

## 你要求的界面分工

- **Blender 3D Viewport（只有一个）**：师傅 Reference Geometry、选取区域、原生 Operation 的逐帧结果、Tool/快捷键提示、数值输入、Why/Design Reasoning；学生的真实模型也在同一个 Viewport，自由选取、建模和 Undo。
- **N 面板 > exCADmple**：只有 Play / Pause / Previous / Next / Repeat / Reset / Explore / Hide、Timeline、Speed、Import（加载教程）。没有教学文字或视频窗口。
- **Expert 不占学生的 Scene/Undo**：播放过程只读编译后的网格数据，使用 `POST_VIEW`/`POST_PIXEL` GPU Draw Handler 绘制。不会在学生正在操作的 Blender 场景运行师傅的 `bpy.ops`。

## 关键架构：真的调用 Blender 现有工具

`lesson.json` 人工指定工具、几何选择、参数和设计理由，不需要恢复历史，也不需要录制器。

首次点击 **Play** 时，Add-on 使用当前安装的 Blender 二进制程序启动独立后台进程：

```
Blender (当前用户界面 · 学生持续建模)
  ├─ Viewport + Play 控制器（原生 Blender）
  └─ Background Blender（隔离的临时进程）
       ├─ 原生 bpy.ops.mesh.extrude_region_move()
       ├─ 原生 bpy.ops.mesh.bevel()
       ├─ 原生 bpy.ops.mesh.inset()
       └─ 原生 bpy.ops.mesh.extrude_region_move()
             ↓ 逐次执行后导出真实网格状态
           Native Operation Snapshots JSON（缓存）
             ↓
  Viewport GPU 回放 + Tool/Selection/Parameter/Reasoning
```

**它不是在学生操作的 Edit Mode 偷偷调用师傅的 Blender 命令，也不是 Python 自己重新计算 Extrude 几何。** 对每个教程步骤，由独立 Blender 进程实际调用官方 `bpy.ops`；它生成的几何状态在原来的 Viewport 重放。这样用户可以一边观看一边使用自己的真实 Blender 工具。

## 现有完整示例：Phone Stand

默认的四个连续操作都是 Blender 内置工具：

1. **Extrude Region** `E`：选中 Base 后侧顶面并向上拉伸 2.4 Blender units。
2. **Bevel Edges** `Ctrl+B`：在背板顶部选择 Edge 并设置 0.08、4 segments。
3. **Inset Faces** `I`：在前侧顶面 Inset 0.18，定义前挡唇。
4. **Extrude Region** `E`：选中前挡唇的 Face 拉伸 0.38。

每一步都依次展示 Tool、Select、Operate（真实 Blender 结果在 3D 中变化）、Parameter 和 Why。Why 是**人工编写的示例说明**，不冒充 CAD 文件推断出的真实设计意图。

## 安装和使用（Blender 4.2+）

1. 下载 `exCADmple_Blender_Native_Tutorial.zip`。
2. Blender → **Edit → Preferences → Add-ons → Install from Disk**（旧版插件选项名称可能略有差异），选择该 ZIP；启用 **exCADmple: Native Blender Interactive Tutorial**。
3. 禁用旧的 `exCADmple: Virtual Expert` 或旧 `In-Viewport Operation Tutorial` 插件，避免 N 面板名字重复。
4. 在任意 Blender 3D Viewport 按 **N → exCADmple → Play**。第一次会自动启动一个后台 Blender 进程，调用真正的原生工具，缓存结果。后面重复播放直接读取缓存。
5. 按 **F3** 搜索 `exCADmple: Frame Learner and Expert`，手动将两个模型位置一起纳入视野（教程默认**不移动学生相机**）。
6. 按 **F3** 搜索 `exCADmple: Create Editable Practice Base`，显式创建属于你的学习模型（这一步才会创建场景对象、进入你的 Undo）。
7. 选中自己的练习模型，按 Tab 进入 Edit Mode，按主键盘 `3` 切换 Face Select，选中后侧小顶面，按 `E`，输入 `2.4`。其他 Inset、Bevel 同理使用 Blender 原生命令。
8. 教程运行时，你可以自由 Orbit、Zoom、选择、编辑、撤销。点击 Pause/Repeat/Next 或直接拖动时间轴不会修改你的模型。

默认示例是教学用人工编排教程，不要求任何历史恢复或操作录制。也可以在 N 面板点击 Import，选择遵守 `lesson.json` 结构的其他原生操作教程。当前原生工具调用有显式 allowlist，禁止任意 Python 执行。

## 技术验证

**已经执行**：

```bash
python -m unittest discover -s tests -v
python -m compileall -q src/native_tutorial
```

**真实 Blender 验证命令**：

```bash
blender --background --factory-startup \
  --python tests/blender_live_test.py
```

本会话的执行环境没有 Blender 二进制，因此**不能声称已经通过实际 bpy.ops、GPU 窗口或 Undo 实机测试**。第一次播放会自动尝试编译，编译失败则在 Play 面板显示错误，并将后台日志保存到用户 Blender Config 的 `excadmple/native_tutorial/` 目录。这个限制不是功能设计的阶段，而是交付的实机验证状态。

## 文件

- `src/native_tutorial/__init__.py`：Blender Add-on、Viewport GPU Renderer、Playback Controls、隔离后台编译与缓存。
- `src/native_tutorial/native_compiler.py`：真正执行 Blender 原生 `bpy.ops`，为操作生成多个采样点；一次仅修改后台场景。
- `src/native_tutorial/compiler_cli.py`：后台 Blender 启动入口。
- `src/native_tutorial/engine.py`：安全教程结构、播放调度、原生结果的可视化处理。
- `src/native_tutorial/starter.py`：一个可直接用于 Blender 内置工具的真实拓扑练习底座。
- `src/native_tutorial/lesson.json`：四个连贯的 Blender 原生操作及人工设计解释。
- `tests/test_native_tutorial.py`：不依赖 Blender 的代码/结构/时间轴/输入安全单元测试。
- `tests/blender_live_test.py`：只在 Blender 中运行的真实 `bpy.ops` 验证。

目前工具支持 `mesh.extrude_region_move`、`mesh.bevel`、`mesh.inset`、`transform.translate`、`transform.rotate`、`transform.resize`、`mesh.subdivide`。这代表支持已有 Blender Operator 的参数化教学描述，不是额外实现七种自研建模工具。
