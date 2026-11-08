# Real Fusion integration fixture

This is a **two-file example**, not a ZIP package:

```text
fusion_example.json    # committed
fusion.f3d             # binary, upload separately if permitted
```

The repo is **public**. The designer's actual binary `fusion.f3d` is **not in the repo yet**. Do not commit a fake model, alter the JSON checksum, or claim a full end-to-end test until the exact file is present.

File metadata for the originally supplied model:

- size: 324089 bytes
- SHA-256: `696ce58b26afc66d68789daa860e8c5ab735522abe2eaa7620b955f1e51c944b`

To place the supplied source file here via GitHub web:

1. Go to the `fusion-him` branch of this repository.
2. Open `tests/fixtures/real_fusion/` and choose **Add file → Upload files**.
3. Upload the exact `fusion.f3d` provided by the researcher. Commit to `fusion-him` **only**.
4. Run a SHA-256 check in your checkout before testing.

For the AI coding agent's complete investigation prompt, see [AI_TEST_PROMPT.md](AI_TEST_PROMPT.md).

For Fusion Desktop: copy this pair into a local folder, install the complete `fusion-him` add-in, and import `fusion_example.json` in the **reference** Fusion window. The add-in reads the real Timeline and generates `fusion_example.generated.json`. Test labels are hypothetical and not the original designer's spoken rationale.

**Actual Fusion Desktop testing still requires a computer with Autodesk Fusion installed**. Cloud-based agents/CI can verify Python and JavaScript code and packaging but cannot validate native Fusion geometry recomputation without the desktop application.
