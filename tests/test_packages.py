"""Run with: python -m unittest discover -s tests -v"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.packages import open_package, PackageError


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.demo = json.loads((Path(__file__).resolve().parents[1] / "examples" / "phone_stand.json").read_text())

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, data, name="example.json"):
        p = self.root / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_demo_is_valid_and_has_independent_snapshots(self):
        pkg = open_package(Path(__file__).resolve().parents[1] / "examples" / "phone_stand.json")
        self.assertEqual(len(pkg.data["steps"]), 9)
        counts = [len(s["geometry"]["meshes"]) for s in pkg.data["steps"]]
        self.assertEqual(counts, sorted(counts))   # cumulative construction
        self.assertNotIn("geometry", pkg.player_data()["steps"][0])
        self.assertTrue(pkg.player_data()["steps"][0]["has_geometry"])
        self.assertEqual(pkg.player_data()["steps"][0]["reasoning"]["source"], "mockup")
        pkg.close()

    def test_duplicate_ids_rejected(self):
        self.demo["steps"][1]["id"] = self.demo["steps"][0]["id"]
        with self.assertRaises(PackageError):
            open_package(self.write_json(self.demo))

    def test_bad_triangle_rejected(self):
        self.demo["steps"][0]["geometry"]["meshes"][0]["triangles"][0][0] = 9999
        with self.assertRaises(PackageError):
            open_package(self.write_json(self.demo))

    def test_media_path_traversal_rejected(self):
        self.demo["steps"][0]["media"]["audio"] = "../private.wav"
        with self.assertRaises(PackageError):
            open_package(self.write_json(self.demo))

    def test_zip_package_with_asset(self):
        self.demo["steps"][0]["media"]["audio"] = "audio/voice.wav"
        path = self.root / "sample.excadmple"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(self.demo))
            z.writestr("audio/voice.wav", b"RIFFexample")
        pkg = open_package(path)
        extracted = Path(pkg.asset_root) / "audio" / "voice.wav"
        self.assertTrue(extracted.exists())
        self.assertTrue(pkg.player_data()["steps"][0]["media"]["audio"].startswith("file:"))
        pkg.close()
        self.assertFalse(extracted.exists())

    def test_zip_with_final_preview_and_source_model(self):
        self.demo["preview"] = "previews/final.png"
        self.demo["source_model"] = "source/original.f3d"
        path = self.root / "with-model.excadmple"
        png = b"\\x89PNG\\r\\n\\x1a\\n" + b"placeholder"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(self.demo))
            z.writestr("previews/final.png", png)
            z.writestr("source/original.f3d", b"original CAD bytes")
        pkg = open_package(path)
        player = pkg.player_data()
        self.assertTrue(player["preview_data_uri"].startswith("data:image/png;base64,"))
        self.assertTrue(player["source_model_included"])
        pkg.close()

    def test_zip_traversal_rejected(self):
        path = self.root / "unsafe.excadmple"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(self.demo))
            z.writestr("../private", b"bad")
        with self.assertRaises(PackageError):
            open_package(path)

    def test_zip_missing_asset_rejected(self):
        self.demo["steps"][0]["media"]["video"] = "media/step.mp4"
        path = self.root / "missing.excadmple"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(self.demo))
        with self.assertRaises(PackageError):
            open_package(path)


if __name__ == "__main__":
    unittest.main()

