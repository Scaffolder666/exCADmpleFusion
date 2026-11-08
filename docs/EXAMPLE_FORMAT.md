# exCADmple 案例文件规范（v2）

一个 Design Example 来自一次真实的设计过程：设计师在 Fusion 中建模，**边建模边说出自己的想法**（think-aloud），同时录屏、录音。案例文件把这次过程整理成 exCADmple 可以播放的形式。

## 原则

1. **每个字段都对应界面上的一样东西**；用不上的不放。
2. **标明来源**：*提取*（脚本从 `.f3d` 读出）、*录制*（录音、录屏、文字稿）、*标注*（研究者整理）。
3. **不编造**：推理只来自设计师说过的话；没有说到的决策、适用范围和依赖都留空。AI 推断不能作为推理来源。
4. **自动部分与人工部分分开存放**：重新提取 `.f3d` 不会覆盖研究者的标注。

## 制作流程

```text
设计师 .f3d ──(Fusion: Extract example draft)──► draft.extract.json   （提取）
录音 / 录屏 ──(任意转写工具)──────────────────► transcript.srt|.vtt|.json （录制）
研究者 ──────────────────────────────────────► annotation.json        （标注）

python tools/build_package.py draft.extract.json annotation.json transcript.srt \
       --media session.m4a --media session.mp4 -o phone-stand.excadmple
```

## 1. 提取草稿 `*.extract.json`（自动，不手改）

在 Fusion 中打开设计师的 `.f3d`，在 exCADmple 面板中点 **Extract example draft…**。脚本逐个滚动时间轴：

| 字段 | 内容 |
|---|---|
| `source` | 文件名、提取时间、单位（cm）、时间轴项目数 |
| `meshes` | 网格库：`{id: {vertices, triangles}}`；相同的 Body 网格只存一次 |
| `features[]` | 每个时间轴项目：`index`、`name`、`kind`（如 `ExtrudeFeature`）、`suppressed` |
| `features[].parameters` | 该特征的参数：名称、表达式、值、单位 |
| `features[].inputs` | 它用到的草图和更早的特征（`sketches`、`features` 的 index），用于推导依赖 |
| `features[].state` | 这个项目完成后，模型中所有可见 Body 的网格 id |

## 2. 文字稿（录制）

录音的转写结果，任何工具都可以，支持 `.srt`、`.vtt` 或 JSON：

```json
[{"start_ms": 0, "end_ms": 4200, "text": "I start with a wide base so it won't tip over."}]
```

时间以整段录音为准。

## 3. 标注 `annotation.json`（研究者编写）

```json
{
  "format": "excadmple-annotation", "version": 1,
  "id": "phone-stand", "title": "Phone Stand",
  "designer": "P03", "date": "2026-11-10",
  "brief": {
    "goal": "A desk stand for watching videos during lunch",
    "users": "Office workers with 6–7 inch phones",
    "constraints": ["Print without supports", "Under 40 g of PLA"]
  },
  "recording": {"audio": "session.m4a", "video": "session.mp4"},
  "steps": [
    {
      "id": "base", "title": "Establish the footprint",
      "features": ["Sketch1", "Extrude1"],
      "recording": {"start_ms": 0, "end_ms": 45000},
      "summary": "A wide, deep base first, so the stand will not tip when the screen is tapped.",
      "decision": { "...": "可选，见下" },
      "scope": {"kind": "goal_specific", "note": "Depth sized for a 7-inch phone"},
      "depends_on": []
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `title`、`designer`、`date` | ✅ | `designer` 可以是匿名编号 |
| `brief.goal` | ✅ | 设计师自己说的设计目标。用户据此判断案例中的选择是否适合自己的目标 |
| `brief.users`、`brief.constraints` | 可选 | 设计师说出的使用者和约束 |
| `recording.audio` / `video` | 可选 | 整段录音或录屏；每一步按自己的时间段播放其中一段 |
| `steps[].features` | ✅ | 这一步包含的时间轴项目（名称或 index），必须按时间轴顺序、不能重叠 |
| `steps[].recording` | ✅ | 这一步在录制中的起止时间（ms） |
| `steps[].summary` | ✅ | 从这一段文字稿中整理出的一两句 Why，只能概括设计师说过的内容 |
| `steps[].decision` | 可选 | 设计师明确提到的问题、考虑过的选项及其取舍、最终选择 |
| `steps[].scope` | 可选 | `general`（通用做法）或 `goal_specific`（只适合原设计师的目标），附一句说明 |
| `steps[].depends_on` | 可选 | 设计师说到的依赖：这一步建立在哪些步骤的选择之上 |

`decision` 的结构：

```json
{
  "topic": "viewing_angle",
  "question": "How steep should the phone lean?",
  "criteria": ["Eye level at a desk", "Glare"],
  "options": [
    {"label": "Shallow", "value": "55 deg", "note": "Reflects ceiling lights"},
    {"label": "Medium", "value": "65 deg", "note": "Readable from a chair", "chosen": true}
  ],
  "parameter": {"name": "Angle from desk", "value": "65 deg", "kind": "angle"},
  "applies_to": {"features": ["ExtrudeFeature"], "tags": ["angle", "tilt"]}
}
```

`topic` 相同的决策会在不同案例之间并排比较。

## 4. 输出：案例包 `*.excadmple`（version 2）

`build_package.py` 生成一个 ZIP：`manifest.json` 加上媒体文件。

**案例层面**：`format: "excadmple"`、`version: 2`、`id`、`title`、`designer`、`date`、`brief`，以及：

| 字段 | 内容 |
|---|---|
| `provenance.geometry` | `extracted`（从 `.f3d` 提取）或 `authored`（手工制作的示例） |
| `provenance.reasoning` | `think_aloud`（边建模边说）或 `illustrative`（示例文字） |
| `provenance.source_file` | 原 `.f3d` 文件名 |

**每一步**：

| 字段 | 来自 | 播放器中的用途 |
|---|---|---|
| `title`、`duration_ms` | 标注 | 时间轴 |
| `geometry.meshes` | 提取：这一步最后一个特征完成后的状态 | 参考模型 |
| `animation: {type: "snapshots", states: [...]}` | 提取：这一步之前的状态，加上每个特征完成后的状态 | 模型如何演变 |
| `operation.tool`、`operation.parameters` | 提取 | How |
| `source_features` | 提取 | 对应 `.f3d` 中的哪些特征 |
| `cues` | 文字稿中落在这一步时间段内的句子 | 同步文字 |
| `media.audio` / `media.video` + `media.offset_ms` | 录制 | 同步语音 / 录屏 |
| `reasoning: {text, source: "think_aloud"}` | 标注的 `summary` | Why |
| `decision`、`scope`、`depends_on` | 标注（可选） | 帮用户判断保留还是重新考虑 |
| `depends_on_derived` | 由特征之间的输入关系推导 | 提示改动可能牵连的步骤（标为"推导"，与设计师说出的依赖区分） |
| `pointer` | 可选（将来由记录插件生成） | Ghost Pointer |

version 1 的包仍然可以读取。附带的 Phone Stand 与 Tablet Stand 是 `provenance.geometry: authored`、`provenance.reasoning: illustrative` 的手工示例。
