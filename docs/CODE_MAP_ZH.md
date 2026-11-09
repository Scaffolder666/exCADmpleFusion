# exCADmple Fusion — 代码导航

## 分支职责

| Branch | 用途 | 修改原则 |
| --- | --- | --- |
| `demo/phone-stand` | 给导师展示的 Phone Stand 固定快照 | 不合并实验性真实模型修改 |
| `fusion-him` | 独立参考 Fusion 窗口，真实 F3D + JSON，原生 HiM 动画 | 主要测试与开发分支 |
| `fusion` | 同一 Fusion viewport 内的 overlay 方案 | 与 HiM 独立验证 |
| `blender` | Blender 原型 | 不与 Fusion 实现混用 |

## 入口与数据流

```text
exCADmpleFusion.py                 Fusion Add-in 入口
  ├─ core/tutorial/example_pair.py         配对 JSON + F3D；生成教程步骤
  ├─ core/tutorial/packages.py             读取、验证教程包
  ├─ core/playback/him_reference.py        参考窗口、原生模型状态、Timeline 和几何
  │    ├─ core/tutorial/reference_plan.py  Step ↔ Feature 映射
  │    ├─ core/playback/him_motion.py      数值参数插值
  │    ├─ core/playback/him_fusion.py      Fusion API 适配
  │    ├─ core/playback/him_wireframe.py   BRep ghost wireframe
  │    └─ core/playback/him_filter.py      几何选择历史过滤
  └─ ui/reference/index.html + player.js + style.css     HiM 参考窗口的控制和语音/动画同步
       └─ ui/reference/frame_clock.js   等待 Fusion 帧完成后的自适应调度
```

**注意：** `ui/overlay/player.js` + `ui/overlay/index.html` 是 overlay（版本 B）的播放器，**不是** HiM 参考窗口。修改 HiM 播放/语音时优先检查 `ui/reference/player.js`，不要只改 `player.js`。

## 示例与真实模型

- `examples/phone_stand.json`：可展示的 toy example，不要求加载真实 F3D。
- `tests/fixtures/real_fusion/fusion.f3d` + `fusion_example.json`：真实模型验收文件。
- `tools/fusion_native_demo/`：从 Fusion 原生 Timeline 生成验证教程的辅助脚本。
- `docs/QUICKSTART_REAL_F3D_ZH.md`：从安装到导入的中文步骤。
- `docs/HIM_NATIVE_PARITY.md`：对照论文机制与尚未验证的功能。

## 运行测试

```bash
python -m unittest discover -s tests -v
node --check ui/reference/player.js
node --check ui/overlay/player.js
node tests/test_him_frame_clock.js
node tests/test_reference_scrubbing.js
```

测试覆盖逻辑但**不替代** Fusion Desktop 中的真实 CAD kernel 重算、窗口通信和语音验收。

## 后续修改约定

1. UI 与播放状态：`ui/reference/player.js`；CAD 逻辑：`core/playback/him_reference.py`，避免互相复制控制状态。
2. 模型参数动画：`core/playback/him_motion.py`，不要为不支持的 Feature 伪造几何增长。
3. 新真实模型先走 JSON + F3D 配对流程，不要改写 Phone Stand 示例。
4. 保持原始 `.f3d` 不变，动画只作用于临时参考副本。
5. 改动时增加相应测试，优先小范围修复，不做跨分支大重构。
