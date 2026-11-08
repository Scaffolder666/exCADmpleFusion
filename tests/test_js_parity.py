"""The reference viewport's JS port must produce the same geometry and
ghost-pointer samples as the Python originals (bundled examples + a
snapshot package). Skipped when Node.js is unavailable."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from core.animation import animation_meshes
from core.pointer import sample

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "ui" / "shared" / "animation.js"
PROGRESS = (0.0, 0.13, 0.5, 0.77, 1.0)


def close(a, b, tol=1e-6):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tol) for k in a)
    return a == b


@unittest.skipUnless(shutil.which("node"), "node not installed")
class JsParityTests(unittest.TestCase):
    def test_examples_match_python(self):
        cases = []
        for name in ("phone_stand.json", "tablet_stand.json"):
            data = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
            for step in data["steps"]:
                for t in PROGRESS:
                    cases.append({"anim": step["animation"], "t": t,
                                  "py": animation_meshes(step["animation"], t)})
                for ms in (0, 700, 1600, 4200, step["duration_ms"]):
                    cases.append({"pointer": step["pointer"], "ms": ms, "py": sample(step["pointer"], ms)})
        tri = lambda z: {"vertices": [[0, 0, z], [1, 0, z], [0, 1, z]], "triangles": [[0, 1, 2]]}
        snap = {"type": "snapshots", "states": [[], [tri(0)], [tri(1)]]}
        for t in PROGRESS:
            cases.append({"anim": snap, "t": t, "py": animation_meshes(snap, t)})
        script = """
const A = require(%s);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(cases.map(c => c.anim ? A.animationMeshes(c.anim, c.t) : A.samplePointer(c.pointer, c.ms))));
""" % json.dumps(str(JS))
        out = subprocess.run(["node", "-e", script], input=json.dumps(cases), capture_output=True,
                             text=True, check=True).stdout
        for case, js in zip(cases, json.loads(out)):
            self.assertTrue(close(case["py"], js), (case.get("anim", {}).get("type"), case.get("t"), case.get("ms")))


if __name__ == "__main__":
    unittest.main()
