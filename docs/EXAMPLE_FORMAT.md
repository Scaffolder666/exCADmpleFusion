# exCADmple 教程文件

一个教程就是一次录下来的设计过程：设计师在 Fusion 中建模，边做边说（think-aloud），同时录屏、录音。教程文件只保存录下来的东西：

- 有哪些步骤；
- 每一步：设计师说了什么、用了哪些工具、模型怎么变的，以及鼠标轨迹（可选）。

## 制作

```text
设计师建模 + 录屏 ──(Fusion: exCADmple: Record tutorial)──► tutorial.session.json  工具、特征出现时间、选中位置
完成的 .f3d       ──(Fusion: Extract tutorial draft…)──────► draft.extract.json     每个特征完成后的模型
录音              ──(任意转写工具 / tools/transcribe.py)────► transcript.srt         说了什么，带时间
以上三份          ──(tools/author.py，AI 提议)─────────────► annotation.json        步骤怎么切分
研究者            ──(ui/author.html 检查、调整)────────────► annotation.json

python tools/build_package.py draft.extract.json annotation.json transcript.srt \
       --media session.mp4 --source Design.f3d -o tutorial.excadmple
```

### annotation.json

```json
{
  "format": "excadmple-annotation", "version": 1,
  "id": "phone-stand", "title": "Phone Stand",
  "recording": {"video": "session.mp4"},
  "steps": [
    {"id": "base", "title": "Establish the footprint",
     "features": ["Sketch1", "Extrude1"],
     "recording": {"start_ms": 0, "end_ms": 45000}}
  ]
}
```

每一步：标题、它包含的时间轴特征（名称或 index，按顺序、不重叠）、它在录制中的起止时间。可选：`tools`（默认取这些特征的类型）和 `pointer`（鼠标轨迹）。

### 文字稿

`.srt`、`.vtt` 或 JSON：`[{"start_ms": 0, "end_ms": 4200, "text": "I start with a wide base."}]`，时间以整段录音为准。

### 提取草稿

对每个时间轴特征，提取工具把时间轴回滚到它之后，记录此时的模型（`state`）、它的参数和它用到的草图与特征。每个特征只记一份模型；相同的网格只存一次（`meshes` 网格库，按 id 引用）。

## 教程包 `*.excadmple`

ZIP：`manifest.json`，加上录音／录屏（`media/`）和设计师的 `.f3d`（`source/`，版本 A 用它播放）。

```json
{
  "format": "excadmple", "version": 2,
  "id": "phone-stand", "title": "Phone Stand",
  "source_model": "source/Design.f3d",
  "meshes": {"mesh-id": {"vertices": [], "triangles": []}},
  "steps": [{
    "id": "base", "title": "Establish the footprint", "duration_ms": 45000,
    "tools": ["Sketch", "Extrude"],
    "cues": [{"at_ms": 1000, "label": "I start with a wide base."}],
    "media": {"video": "media/session.mp4", "offset_ms": 0},
    "geometry": {"meshes": ["mesh-id", "…"]},
    "animation": {"type": "snapshots", "states": [["…这一步之前…"], ["…每个特征完成后…"]]},
    "source_features": [{"index": 1, "name": "Extrude1", "kind": "ExtrudeFeature"}],
    "pointer": [{"at_ms": 1500, "xyz": [0, 0, 0], "event": "click"}]
  }]
}
```

| 字段 | 来自 | 播放时 |
|---|---|---|
| `title` | 标注 | 步骤标题 |
| `cues` | 文字稿中落在这一步时间段里的句子 | 设计师说的话，与声音同步；没有录音时可用电子音朗读 |
| `media` + `offset_ms` | 录制 | 播放这一步对应的那一段录音／录屏 |
| `tools` | 提取（或标注） | 用了哪些工具 |
| `geometry`、`animation` | 提取 | 版本 B 和 Blender：这一步前后的模型，用户可以旋转查看 |
| `source_features` + `source_model` | 提取 | 版本 A：在设计师的模型上按 HiM 的方式播放 |
| `pointer` | 记录（可选） | 鼠标轨迹（Ghost Pointer） |

version 1 的旧包仍可读取。附带的 Phone Stand 与 Tablet Stand 是手工编写的示例，不是真实录制。
