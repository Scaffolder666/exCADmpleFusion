# exCADmple Recorder

在 Fusion 中边建模边说出设计理由。录制结束后可试听整段语音或单个操作对应的片段，也可以在本机转写，然后检查文字和建模操作的匹配情况。

## 安装

1. 保留整个仓库。Fusion 的「脚本和附加模块」里点 **+**，选仓库内的 **`exCADmpleRecorder` 子文件夹**。该文件夹内有同名的 `.py` 和 `.manifest`。
2. 运行 **exCADmpleRecorder**。在「设计 → 实用程序 → 附加模块」区域打开 **exCADmple · 语音录制**。
3. 在启用设计历史记录的设计中点 **录制语音与建模**。如果系统询问，允许 Fusion 使用麦克风。新建一个草图，完成一次拉伸，再点 **停止并保存**。

如果 Fusion 面板无法访问麦克风，可在其他应用同步录制 WAV。插件里选 **仅记录建模**，完成后导入该 WAV。偏移表示音频相对于建模记录何时开始，比如语音早两秒则填 `-2`。

## 本机转写

在 macOS 的「终端」执行一次：

```bash
python3 -m venv "$HOME/.venvs/excadmple-recorder"
"$HOME/.venvs/excadmple-recorder/bin/python" -m pip install faster-whisper
```

Windows PowerShell 对应命令：

```powershell
py -m venv "$HOME/.venvs/excadmple-recorder"
& "$HOME/.venvs/excadmple-recorder/Scripts/python.exe" -m pip install faster-whisper
```

录制结束后选中文、English 或自动识别，再点 **转写**。首次运行需联网下载 Whisper small 模型，音频由本机 CPU 处理。失败时查看该会话的 `transcription.log`。

## 记录格式与回放

每次录制保存在 `~/Documents/exCADmpleRecordings/` 下的独立目录。保留 `session.json` 和 `voice.wav` 可在插件中重新打开会话。JSON 的 `operations` 记录操作的 Timeline 索引、名称、类型、检测时间、音频区间和归属转写。音频从录制起点对齐，外部 WAV 可用 `audio.offset_ms` 调整。跨界的转写句按重叠时长分配，无法匹配的句子显示在列表下方。

播放整段会高亮当前区间，点击 **播放此段** 可试听单个操作。回放用于核对语音和建模记录，几何体保持当前状态。记录器捕获命令结束时检测到的新增时间轴项目。草图中每笔线条、对既有特征的参数修改，以及同一条指令内部各子动作的精确时间不会单独记录。录音起点和操作边界有估算成分，建议先用两三个建模操作做实机试录。
