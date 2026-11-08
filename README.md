# exCADmple — Autodesk Fusion 插件

**Supporting Design Reasoning Through Shared CAD Models** · 固定开发分支 `fusion`

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

## 播放

- **整个教程**连续播放，或**只播这一步**；每一步可以重播；上一步／下一步；0.5×–2× 速度。
- **声音**：播放这一步对应的那段原声（录音或录屏的声音）；没有录音时可以用电子音朗读文字稿。
- **文字**：这一步设计师说的每一句话，当前这句高亮；点某一句可以跳到那里。
- **模型和指针**：参考模型随步骤变化，鼠标轨迹显示为橙色的 Ghost Pointer（不会移动真实鼠标）。
- **关联几何**（可选）：可以把某一步关联到自己模型里的 Body／Face，切换到这一步时高亮它，并把其他 Body 暂时调暗。

## 教程文件

教程就是录下来的东西：步骤、每一步说了什么、用了哪些工具、模型怎么变、鼠标轨迹。规范见 [`docs/EXAMPLE_FORMAT.md`](docs/EXAMPLE_FORMAT.md)。

1. **录制**：设计师在 Fusion 里建模，边做边说，同时录屏。
2. **提取**：在 Fusion 里打开设计师的 `.f3d`，点教程面板底部的 **Extract tutorial draft…**，记录时间轴上每个特征完成后的模型（每个特征一份）。
3. **转写**：把录音转成带时间的文字稿（`.srt` 等）。
4. **切分步骤**：用标注工具（见 [`authoring-plan`](https://github.com/Scaffolder666/exCADmpleFusion/tree/authoring-plan)）标出每一步的标题、时间段和对应的特征。
5. **合成**：`python tools/build_package.py draft.extract.json annotation.json transcript.srt --media session.mp4 --source Design.f3d -o tutorial.excadmple`

附带的 `examples/phone_stand.json`（九步）和 `examples/tablet_stand.json` 是手工编写的示例，不是真实录制。由 `python tools/build_examples.py` 生成。

## 安装

1. 下载本分支 ZIP 并解压，保持整个 `exCADmpleFusion` 文件夹完整。
2. Fusion 中打开或新建一个 **Design**。
3. **Utilities → Scripts and Add-Ins → Add-Ins**，点 **+**，选中文件夹并运行。
4. 版本 B：教程面板浮在画布上，示例自动打开；**Import** 打开别的教程。版本 A：工具栏点 **exCADmple Reference window** 打开第二个 Fusion（需要在 Add-Ins 里勾选 **Run on Startup**，该分支默认已开启）；如果没有自动启动，手动再开一个 Fusion 运行插件即可，它会自动连接。

## 不会改动用户的模型

- 版本 B 的参考模型、指针和文字都是临时 Custom Graphics，不进入用户的时间轴；保存前清除、保存后恢复。
- 版本 A 在第二个窗口里打开的是 `.f3d` 的副本，从不保存；改过的参数在每一步之后恢复。
- 关联几何时调暗的透明度会在切换步骤、保存前、切换文档和停止插件时恢复；保存前恢复失败会取消保存。

## 测试

```bash
python -m unittest discover -s tests -v
node --check ui/player.js && node --check ui/reference.js
```

尚未在 Fusion 桌面端实测。需要确认：两个版本的面板显示、画布左上角文字（版本 B）、两个 Fusion 能否同时运行并连接（版本 A）、用真实 `.f3d` 提取并播放。

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
ui/index.html, player.*   版本 B 的面板
ui/reference.*            版本 A 的控制面板
tools/                    build_package.py（合成）、build_examples.py（示例）
```

*History in Motion*：Veuskens et al., SCF 2023（[DOI](https://doi.org/10.1145/3623263.3623358)）。
