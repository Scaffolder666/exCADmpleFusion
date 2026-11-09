# Same viewport, two independent histories — Fusion Desktop test

**Status: not yet run in Fusion Desktop.** The automated tests
(`tests/test_same_viewport.py`) use a stubbed Fusion API. They check which
document is active, which Timeline and parameters are changed, where the
graphics are drawn and that they are removed. They cannot show what Fusion
itself does.

## How it works

| | Reference model | Your model |
|---|---|---|
| Document | An unsaved copy of the tutorial's `.f3d`, opened as its own document tab | Your Design (stays the active document) |
| History | The `.f3d`'s real Feature Timeline; exCADmple rolls it and animates its parameters (HiM) | Fusion's own Timeline; only your operations |
| Shown in your viewport as | Custom Graphics: temporary copies of the reference bodies, plus the HiM highlights, moved beside your model | Your normal bodies |
| Editable / selectable | No | Yes |
| Saved | Never | Normally |

No reference feature is ever added to your Timeline. Selecting your own
geometry never triggers tutorial filtering.

## Check first: background recompute

The main unknown is whether Fusion recomputes the reference copy while it is
**not** the active document. That covers moving its Timeline marker and
changing its parameter values.

- If it does, the reference grows smoothly in your viewport while you stay in your Design.
- If it does not, the reference shown beside your model will not change during an animation, or the panel will report an error. Please report exactly what you see; nothing falls back silently.

## Procedure

1. Install this branch, then restart Fusion completely.
2. Create a new Design. Add one small body of your own (Sketch → Extrude).
3. Load a JSON + `.f3d` tutorial, for example `tests/fixtures/real_fusion/` or the `tools/fusion_demo` model (Sketch → Extrude → Fillet → Mirror).
   - **Expected:** a new tab holds the reference copy, but **your Design stays active**.
   - The reference model appears to the right of your body.
   - Your Timeline shows only your own features.
4. Press Play.
   - **Expected:** feature-by-feature playback, with parameters growing (e.g. extrude height) beside your model.
   - Teal and blue highlights, labels, audio, transcript, slider and Fit View behave as before.
5. Pause during an Extrude. Create a Sketch and an Extrude in your Design.
   - **Expected:** only your two features are added to your Timeline.
   - The reference stays visible and you cannot select it.
6. Press Play again.
   - **Expected:** playback resumes from where it paused. Your model and Timeline do not change.
7. Scrub backward and forward, and jump between steps.
   - **Expected:** the reference changes; your model does not.
8. Save your Design, close it, reopen it.
   - **Expected:** your work is all there.
   - No reference graphics or features are saved in it.
   - The reference `.f3d` file on disk is unchanged.
9. Close the tutorial or stop the add-in.
   - **Expected:** the reference tab closes without a save prompt, and all reference graphics disappear from your viewport.

## Known limits

- **Selecting reference geometry:** to filter steps by selecting reference geometry (HiM filtering), switch to the reference tab and select there. Reference graphics in your viewport are not selectable, by design, so that they never interfere with your modeling.
- **Sketches:** only sketches in the reference root component are drawn in your viewport.
- **Speed:** every animation frame copies the bodies that are being recomputed. Very large reference models may play more slowly.
