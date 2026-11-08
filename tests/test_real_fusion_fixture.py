"""The committed real-model fixture: fusion_example.json + fusion.f3d.

Checks what can be checked without Fusion: the exact file is present, the
JSON accepts it (SHA-256), loading never changes it, and the pair asks for
the real Timeline before any step exists. Reading that Timeline and
playing it needs Fusion Desktop (docs/REAL_FUSION_MODEL_TEST.md)."""
import hashlib
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.packages import open_package

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real_fusion"
SHA256 = "696ce58b26afc66d68789daa860e8c5ab735522abe2eaa7620b955f1e51c944b"


@unittest.skipUnless((FIXTURE / "fusion.f3d").is_file(), "fixture missing: tests/fixtures/real_fusion/fusion.f3d")
class RealFusionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        for name in ("fusion_example.json", "fusion.f3d"):
            shutil.copy2(FIXTURE / name, self.folder / name)

    def test_exact_model_is_present_and_is_a_fusion_archive(self):
        data = (FIXTURE / "fusion.f3d").read_bytes()
        self.assertEqual(len(data), 324089)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SHA256)
        with zipfile.ZipFile(FIXTURE / "fusion.f3d") as archive:
            names = archive.namelist()
        self.assertIn("Manifest.dat", names)
        self.assertTrue(any("FusionDesignSegmentType1" in n for n in names))

    def test_pair_loads_waits_for_the_real_timeline_and_leaves_the_model_unchanged(self):
        model = self.folder / "fusion.f3d"
        before = model.read_bytes()
        package = open_package(self.folder / "fusion_example.json")
        self.assertTrue(package.needs_populate)
        self.assertEqual(package.source_model_path(), model.resolve())
        self.assertEqual(package.data["steps"], [])       # no guessed steps before Fusion reads it
        self.assertTrue(package.raw["auto_generate"])
        package.close()
        self.assertEqual(model.read_bytes(), before)
        self.assertFalse((self.folder / "fusion_example.generated.json").exists())


if __name__ == "__main__":
    unittest.main()
