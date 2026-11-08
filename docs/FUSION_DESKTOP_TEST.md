# 版本 A：Fusion Desktop 验收步骤（HiM 原生参数动画）

单元测试只用模拟的 `adsk` 接口检查插件自己的逻辑（参数选择、进度、恢复、映射、回退、清理）。**它们不能证明 Fusion 真的按参数重算了几何。** 下面的步骤需要在 Autodesk Fusion 桌面端手动完成；全部通过之前，版本 A 的 HiM 动画不算验收。

记录方式：每一项写 通过 / 失败 / 备注，以及 Fusion 版本号、操作系统。

## 0. 准备

1. 下载 `fusion-him` 分支，保持 `exCADmpleFusion` 文件夹完整。
2. Fusion：**Utilities → Scripts and Add-Ins → Add-Ins → +**，选中文件夹，勾选 **Run on Startup**，运行。
3. 生成验收模型：**Scripts → +**，选中 `tools/fusion_demo`，运行 `fusion_demo`。
   - 预期：弹窗显示写出的 `~/exCADmple-validation/him-validation.excadmple`，时间轴为
     `Sketch1 (Sketch), Extrude1 (ExtrudeFeature), Fillet1 (FilletFeature), Sketch2 (Sketch), Extrude2 (ExtrudeFeature), Plane1 (ConstructionPlane), Mirror1 (MirrorFeature)`（名称可能因语言不同）。
   - 同一文件夹里还有 `HiMValidation.f3d`、`draft.extract.json`、`annotation.json`、`transcript.json`。
   - 注意：这个教程的“设计师说的话”是为验收写的示例文字，不是真实 think-aloud；没有录音、没有指针数据。
   - 若脚本失败（例如 Fillet 或 Mirror 的 API 参数不同），记下报错；也可以手动建一个同样时间轴的模型，保存为 `.f3d`，用面板底部 **Extract tutorial draft…** 提取，再用
     `python tools/build_package.py draft.extract.json annotation.json transcript.json --source HiMValidation.f3d -o him-validation.excadmple`
     合成（`annotation.json` 用脚本写出的那份或按 `docs/EXAMPLE_FORMAT.md` 手写，特征用时间轴 index）。

## 1. 两个窗口

| # | 操作 | 预期 |
|---|---|---|
| 1.1 | 第一个 Fusion 里打开或新建自己的设计 | 正常建模，无教程面板以外的变化 |
| 1.2 | 工具栏 **exCADmple Reference window** | 启动第二个 Fusion（或手动再开一个并运行插件），两边显示已连接 |
| 1.3 | 在参考窗口载入 `him-validation.excadmple` | 打开 `.f3d` 的副本（新文档），面板显示 “Playing on the designer's model HiMValidation.f3d”，没有 “not found in the model” |
| 1.4 | 看每一步卡片的 Animation 行 | base: `Extrude1 · parameter animation: d1`（参数名可能不同）；round: `Fillet1 · parameter animation`；post: `Extrude2 · parameter animation`；mirror: `Plane1 · timeline state`、`Mirror1 · visual fade` |

## 2. 参数动画（真实重算）

| # | 操作 | 预期 |
|---|---|---|
| 2.1 | 选 base，播放 | 时间轴停在 Extrude1 之后；拉伸高度从接近 0 连续长到 1 cm；Fusion 每帧重算（不是图片） |
| 2.2 | round 播放 | 圆角半径从接近 0 长到 0.5 cm；其他 Body 半透明（“Other bodies transparent” 打开时）；所选边高亮 |
| 2.3 | post 播放 | 圆柱从顶面长出到 2 cm，与底座合并 |
| 2.4 | 每步结束后，在参考窗口打开 **Modify → Change Parameters** | 每个参数的表达式与原值完全相同（`1 cm`、`0.5 cm`、`2 cm`），没有残留的数值 |
| 2.5 | 播放中途暂停 | 模型停在中间状态；再播放继续 |
| 2.6 | 播放中途切到别的步骤、按后退、按重播 | 之前的参数立即恢复；新步骤从头开始；后退时当前步骤倒放 |
| 2.7 | 播放中途关闭参考窗口的教程或停止插件 | 不提示保存；重新打开 `HiMValidation.f3d` 原文件，参数与时间轴未变 |
| 2.8 | 播放中旋转、缩放视图；按 Fit | 动画继续，视图可操作 |

## 3. 视觉回退

| # | 操作 | 预期 |
|---|---|---|
| 3.1 | mirror 播放 | 时间轴停在 Mirror1 之后；镜像出的结果以高亮色从小到大、从透明到不透明出现；卡片显示 visual fade |
| 3.2 | mirror 结束或切换步骤 | 高亮叠加图形消失，所有 Body 透明度恢复原值 |
| 3.3 | （可选）把某个参数改成会失败的值再播放 | 卡片显示 `visual fallback (...)`，参数恢复，不出现报错对话框 |

## 4. 映射和过滤

| # | 操作 | 预期 |
|---|---|---|
| 4.1 | 在参考模型上选中圆角面 | 面板只列出 base 和 round（HiM 过滤） |
| 4.2 | 手工编辑 `manifest.json`，把某步 `source_features` 的 name 改成不存在的名字后重新载入 | 面板列出 “not found in the model: …”，该步只按时间轴显示，不动画别的特征 |
| 4.3 | 把两个特征改成同名后重新提取 | 只要 index 对得上就各自映射；对不上时报告“share this name”，不猜测 |

## 5. 用户模型不受影响

| # | 操作 | 预期 |
|---|---|---|
| 5.1 | 播放时在第一个窗口继续建模、保存 | 用户模型、时间轴、参数、透明度都不变 |
| 5.2 | 参考窗口里切到另一个文档后继续播放 | 不动画（参考副本不是活动文档时插件不改任何东西）；切回后继续 |

## 6. 其他功能仍在

声音／电子音朗读、文字稿高亮和点击跳转、工具列表、步骤列表、上一步／下一步、速度、Load Example、录制按钮（第一个窗口）都与之前一样。版本 B（`fusion` 分支）不在本次验收范围内。

## 7. 空间引导（附带的 Phone Stand，没有 `.f3d`）

| # | 操作 | 预期 |
|---|---|---|
| 7.1 | 新建一个空 Design，运行插件，载入附带的 Phone Stand | 显示第一步的模型，整个底座为青色 |
| 7.2 | 点第 3 步 “Prevent the phone from sliding” | 只有底座前缘的小挡边（约 x 0.5–9.5 cm、y 0.4–1.0 cm、z 0.7–1.7 cm）是青色，底座和背板保持灰色；挡边与底座接触的底面不着色 |
| 7.3 | 播放第 3 步，中途暂停 | 挡边长到一半，长出的部分为青色，暂停后保持 |
| 7.4 | 旋转视图；点击青色区域 | 高亮正常显示、无闪烁（z-fighting）；不能被选中，Fusion 选择不受影响 |
| 7.5 | 切到第 4 步、后退到第 2 步、重播第 3 步 | 第 4 步只有圆角为青色；第 2 步只有背板；重播开始时挡边还没有青色，随后长出 |
| 7.6 | 换另一个教程、关闭教程、停止插件 | 画布上不留任何青色或灰色的参考图形 |
