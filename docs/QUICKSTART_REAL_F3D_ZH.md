# 真实 Fusion .f3d + JSON：从零开始测试 HiM

## 两条路径

- **演示**：`demo/phone-stand` 是从 2026-11-08 的 `fusion-him` 状态创建的固定快照，保留 Phone Stand toy example；不在此分支继续开发真实模型。
- **真实测试**：使用 `fusion-him`，未导入外部案例时仍可使用原有 Phone Stand demo；导入真实 JSON 后切换到对应的原生模型。

## 1. 下载和安装插件

1. 打开 https://github.com/Scaffolder666/exCADmpleFusion/tree/fusion-him ，点击 Code → Download ZIP，解压完整仓库；不要只下载 Python 入口。
2. 关闭 Fusion。若之前安装过旧版，停止旧 Add-in 并用本分支完整文件替换，避免同名旧插件同时运行。
3. 打开 Fusion → **Utilities → Scripts and Add-Ins → Add-Ins → +**，选择解压的整个 `exCADmpleFusion` 文件夹，运行插件。需要时勾选 **Run on Startup**。
4. `fusion-him` 是独立参考窗口布局：在工具栏点击 **exCADmple Reference window**；如果没有第二个窗口，按仓库 README 的说明在第二个 Fusion 实例中运行 Add-in。参考窗口右侧才是 `ui/reference.js` 控制面板。

## 2. 准备测试文件（仓库已经提供）

仓库 `tests/fixtures/real_fusion/` 下已有：

```text
MyRealTest/
  fusion.f3d
  fusion_example.json
```

把两个文件**一起**复制到本地任意普通文件夹，例如 `Documents/exCADmple/MyRealTest/`。文件名必须与 JSON 中 `"model": "fusion.f3d"` 对应。不要改动原始 `.f3d`；JSON 带有 `model_sha256` 校验，换模型后必须重新生成匹配的 JSON/校验值。

默认 `fusion_example.json` 的 `auto_generate: true`：它会读取真实 Fusion Timeline，自动生成步骤。它不包含原作者真实语音；自动解释是模拟测试文本，不能用于证明真实设计推理。

## 3. 在 Fusion 里加载

1. 启动最新 `fusion-him` 插件并打开 **reference** 参考窗口。
2. 在该窗口的 exCADmple 面板点击 **+ Import**。
3. **选择 `fusion_example.json`，不要选 `fusion.f3d`**。
4. 插件应该自动查找同目录的 `fusion.f3d`，在未保存的参考文档副本中导入模型并读取 Timeline。
5. 第一次导入后，同目录应该出现 `fusion_example.generated.json`；以后可以编辑它的 `transcript`、`duration_ms` 等，再用 **+ Import** 导入生成的 JSON。
6. 点击 **Play**，检查当前 Feature 的原生参数动画和右侧文字。注意：有些 Feature（如 Mirror/Combine）设计上会直接出现最终几何，并不模拟数值增长。

## 4. 测试哪些行为

- **加载**：模型显示为完整实心几何；步骤数与真实 Timeline 对应；失败时记录错误文本。
- **Extrude / Fillet 等**：播放时参数确实变化、Fusion 实时重算，而不是 Mesh 快照；背景是前序几何线框，当前修改部分高亮。
- **Mirror / Combine**：立即显示实际几何，语音/Transcript 继续；不要错误地缩放整个 Body。
- **音频**：如果使用自己的语音录音，在 JSON 同目录放 `step.wav` 并为步骤添加 `"audio": "step.wav"`；检查动画先结束时不应切下一步。没有真实录音的默认 JSON **不能**验证完整录音同步。
- **操作**：Pause、Resume、Replay、Next/Previous、拖动整体 Progress、Fit/Auto Focus、0.5–2× Speed。
- **安全**：结束/切换后恢复模型参数、透明度和完整视图；原始 `fusion.f3d` 不应被覆盖。

## 5. 自己换一个 .f3d 怎么办？

把自己的 `MyDesign.f3d` 和以下 JSON 放在同一目录（不需要手工填写 Timeline）：

```json
{
  "format": "excadmple-pair",
  "version": 1,
  "title": "My real Fusion test",
  "model": "MyDesign.f3d",
  "auto_generate": true,
  "step_duration_ms": 8000,
  "steps": []
}
```

然后按第 3 节导入 JSON。确保 `.f3d` 包含 Fusion 可读取的参数化 Timeline；没有建模历史的导入 Mesh/STEP 不等于可重建的 HiM 教程。

## 6. 出错时收集信息

记录 Fusion 版本和操作系统、导入文件名、失败的 Feature/步骤名称、面板 Status 原文、截图或短录屏。真实 Fusion Desktop 内核重算仍需实机验收；仓库自动化测试不能替代。

相关详细文档：`docs/JSON_F3D_PAIR.md`、`docs/HIM_NATIVE_PARITY.md`、`docs/REAL_FUSION_MODEL_TEST.md`。
