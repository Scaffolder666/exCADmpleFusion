# exCADmple Recorder

Record a voice message for each modeling step in Autodesk Fusion. Sent messages appear below their steps, where you can play them or generate a transcript.

## Install

Keep this directory inside the repository so the recorder can find `tools/transcribe.py`.

On macOS, run the following command once from the repository root. It builds the local microphone helper using Apple's Command Line Tools.

```bash
bash exCADmpleRecorder/install-mac-audio.sh
```

If Command Line Tools are missing, run `xcode-select --install`, wait for installation to finish, then rerun the setup command. On first use, allow **exCADmple Microphone** to access the microphone. Windows uses the microphone from Fusion's panel and does not require this helper.

In Fusion, open **Scripts and Add-Ins**, add the **exCADmpleRecorder** subfolder, and run the add-in. In the **Design** workspace, open **Utilities → Add-Ins → exCADmple Voice Recorder**.

## Record and play messages

1. Open a parametric design with design history enabled.
2. Click **Start Recording** and wait for the voice bar to show **Recording**. Explain your design decision as you complete one modeling step, such as finishing a sketch or creating an extrusion.
3. Click **Send Voice Message** to save the recording. Click its green **Play** button to listen in Fusion. To listen before sending, click **Stop and Preview**.
4. Click **Record Next** to repeat, or **End Session** when finished.

If there is one modeling step without audio, the recorder links the message to it. If there are multiple eligible steps, choose one or select **Link a Step Later**. If Fusion has not detected a step yet, the message is saved under **Unlinked Voice Messages**. It can be played immediately and linked with **Link to Step** once an eligible step appears. The recorder detects new features in the Fusion Timeline.

## Transcribe locally

Install the dependency once. On macOS, run the following in Terminal:

```bash
python3 -m venv "$HOME/.venvs/excadmple-recorder"
"$HOME/.venvs/excadmple-recorder/bin/python" -m pip install faster-whisper
```

On Windows, use PowerShell:

```powershell
py -m venv "$HOME/.venvs/excadmple-recorder"
& "$HOME/.venvs/excadmple-recorder/Scripts/python.exe" -m pip install faster-whisper
```

Choose **Auto-detect**, **Chinese**, or **English**, then click **Transcribe** beside a saved voice message. The first run downloads the Whisper small model. Transcription runs locally on the CPU. If it fails, check the matching `transcript-*.log` file in the session folder.

## Reopen a session

Each session is saved under `~/Documents/exCADmpleRecordings/`. The folder path also appears below the design name in the panel. Each sent message has its own WAV file. `session.json` stores the modeling steps, audio references, and transcripts.

Use **Open Session** and select the original `session.json` to restore the messages and their step associations. Keep the WAV files in the same folder. **Import Voice Message** imports a single WAV as an unlinked message. Older full-length recordings can still be opened, and the **Track Modeling Only** workflow supports importing a separate recording.
