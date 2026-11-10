# Authoring tool — Fusion Desktop test

**Status: not yet run in Fusion Desktop.** `tests/test_authoring_draft.py` and
`tests/test_authoring_fusion.py` run on a stubbed Fusion API. They check the
grouping, the edits, the WAV file, the attributes written on Save and that the
player reads them back. They cannot show what Fusion itself does.

## Check first

1. **Microphone in a Fusion panel.** The panel records with `getUserMedia`
   (Web Audio, saved as 16 kHz WAV). Fusion may not let a palette use the
   microphone. If it does not, the panel says "Microphone not available (…)".
   Please report the exact text. Modeling is still recorded; import a
   recording made with another app instead.
2. **Attributes in an exported .f3d.** The tutorial is stored as attributes
   (group `exCADmple`, `tutorial-count`, `tutorial-0` …) on the Design and the
   `.f3d` is exported with `createFusionArchiveExportOptions`. Check that a
   learner who imports that `.f3d` gets the tutorial (step 7 below).

## Procedure

1. Install this branch (`authoring-tool`), `config.json` `"layout": "reference"`, restart Fusion.
2. Create a new Design. Toolbar → **exCADmple: Author tutorial**.
   - **Expected:** the "exCADmple · Author" panel opens, floating.
3. Press **Record** (keep "Record my voice" on). Allow the microphone if asked.
   Model: Sketch → Extrude → Fillet → Sketch → Extrude, talking while you work.
   Press **Stop**.
   - **Expected:** "Recorded N new features…". The steps appear: each sketch is
     together with the feature made from it. Under each step, what you said in
     that time.
   - `~/exCADmple-tutorials/<design>-<time>/` holds `voice.wav` and `session.json`.
4. Press ▶ on a step.
   - **Expected:** you hear only that step's part of the recording.
5. **Transcribe** (needs `pip install faster-whisper` in the Python that
   `config.json` `"python"` names, or `python3` on PATH), or **Import…** an `.srt`.
   - **Expected:** sentences appear under the steps they were said in.
6. Edit:
   - **⤓ merge into one step** between Extrude1 and Fillet1 → one step with three operations.
   - **✂** inside it → two steps again.
   - **↓ next** on a step's last sentence → the sentence moves to the next step.
   - Type a title and a "Why" text; **Use what I said** brings the spoken text back.
7. **Preview**.
   - **Expected:** the player loads the tutorial; your Design stays active; the
     merged step plays its operations one after another, with its slice of the
     recording and its text.
8. **Save into .f3d…** → choose a folder.
   - **Expected:** `<name>.f3d` and `<name>.wav` in that folder.
   - In a new Fusion session, the player's **+ Import** → choose that `.f3d`.
     **Expected:** the same steps, titles, texts and audio as in step 7.
9. Close and reopen your Design (saved after step 8), open the authoring panel.
   - **Expected:** "Continued the tutorial saved in this design…" and your grouping.
10. Stop the add-in.
   - **Expected:** the panel closes; your design's geometry and Timeline are unchanged.

## Diagnostic log

`logs/latest.log` records "recording started", "recording stopped" (feature
count, length, audio file), "saved", panel script errors and tracebacks.
Please send it after the test.
