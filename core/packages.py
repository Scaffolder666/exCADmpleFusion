"""Load and validate exCADmple design-process examples.

Standalone Python (no Fusion dependency), so the format can be tested outside CAD.
A .json manifest can reference media alongside it; a .excadmple file is a ZIP
containing manifest.json and optional relative assets.
"""
import json
import math
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_MEMBERS = 150
MAX_STEPS = 150
MAX_TRIANGLES = 60000


class PackageError(ValueError):
    pass


def _relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise PackageError("Media paths must be relative forward-slash paths")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts) or ":" in p.parts[0]:
        raise PackageError("Unsafe media path: " + value)
    return p


def _validate_mesh(mesh):
    if not isinstance(mesh, dict):
        raise PackageError("A geometry mesh must be an object")
    vertices = mesh.get("vertices", [])
    triangles = mesh.get("triangles", [])
    if not isinstance(vertices, list) or len(vertices) < 3 or len(vertices) > 40000:
        raise PackageError("Mesh vertex count is invalid")
    if not isinstance(triangles, list) or len(triangles) > MAX_TRIANGLES:
        raise PackageError("Too many mesh triangles")
    for vertex in vertices:
        if not isinstance(vertex, list) or len(vertex) != 3 or not all(
            isinstance(n, (int, float)) and math.isfinite(n) for n in vertex
        ):
            raise PackageError("Each vertex must contain three finite coordinates")
    for tri in triangles:
        if not isinstance(tri, list) or len(tri) != 3 or any(
            not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= len(vertices)
            for i in tri
        ):
            raise PackageError("Invalid triangle indices")


def _validate(data):
    if not isinstance(data, dict) or data.get("format") != "excadmple" or data.get("version") != 1:
        raise PackageError("Expected exCADmple format version 1")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise PackageError("Package title is required")
    steps = data.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise PackageError("Package must contain 1–150 steps")
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("id"), str):
            raise PackageError("Each step requires a string id")
        if step["id"] in seen or not step["id"]:
            raise PackageError("Step ids must be unique and nonempty")
        seen.add(step["id"])
        if not isinstance(step.get("title"), str) or not step["title"]:
            raise PackageError("Each step requires a title")
        duration = step.get("duration_ms", 8000)
        if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not 500 <= duration <= 3600000:
            raise PackageError("Step duration must be between 500 ms and 1 hour")
        geometry = step.get("geometry", {})
        if not isinstance(geometry, dict):
            raise PackageError("Geometry must be an object")
        meshes = geometry.get("meshes", [])
        if not isinstance(meshes, list) or len(meshes) > 50:
            raise PackageError("At most 50 meshes per step")
        for mesh in meshes:
            _validate_mesh(mesh)
        for kind in ("audio", "video"):
            asset = step.get("media", {}).get(kind)
            if asset is not None:
                _relative_path(asset)
        cues = step.get("cues", [])
        if not isinstance(cues, list):
            raise PackageError("Cues must be an array")
        for cue in cues:
            if not isinstance(cue, dict) or not isinstance(cue.get("at_ms"), (int, float)):
                raise PackageError("Cue requires at_ms")
            if not 0 <= cue["at_ms"] <= duration:
                raise PackageError("Cue exceeds step duration")
    return data


class ExamplePackage:
    def __init__(self, data, asset_root, temporary=None):
        self.data = _validate(data)
        self.asset_root = Path(asset_root).resolve()
        self.temporary = temporary

    def close(self):
        if self.temporary:
            shutil.rmtree(self.temporary, ignore_errors=True)
            self.temporary = None

    def player_data(self):
        """Minimal metadata for HTML. Geometry stays Python-side."""
        result = {"title": self.data["title"], "description": self.data.get("description", ""), "steps": []}
        for step in self.data["steps"]:
            meta = {k: v for k, v in step.items() if k not in ("geometry", "media")}
            media = {}
            for kind in ("video", "audio"):
                resource = step.get("media", {}).get(kind)
                if resource:
                    path = (self.asset_root / str(_relative_path(resource))).resolve()
                    if not path.is_relative_to(self.asset_root):
                        raise PackageError("Media path escapes package directory")
                    if path.is_file():
                        media[kind] = path.as_uri()
            meta["media"] = media
            result["steps"].append(meta)
        return result

    def step(self, index):
        if not isinstance(index, int) or not 0 <= index < len(self.data["steps"]):
            raise PackageError("Step index out of range")
        return self.data["steps"][index]


def open_package(filename):
    source = Path(filename).resolve()
    if not source.is_file():
        raise PackageError("Example file does not exist")
    if source.suffix.lower() == ".json":
        if source.stat().st_size > 8 * 1024 * 1024:
            raise PackageError("JSON file is too large")
        return ExamplePackage(json.loads(source.read_text(encoding="utf-8")), source.parent)
    if source.suffix.lower() != ".excadmple":
        raise PackageError("Choose a .json or .excadmple file")
    temp = None
    try:
        with zipfile.ZipFile(source, "r") as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
                raise PackageError("Archive exceeds size limits")
            for member in members:
                _relative_path(member.filename.rstrip("/"))
                # Prevent extracting Unix symlinks.
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise PackageError("Symlinks are not supported")
            if "manifest.json" not in archive.namelist():
                raise PackageError("Archive is missing manifest.json")
            manifest = _validate(json.loads(archive.read("manifest.json").decode("utf-8")))
            temp = tempfile.mkdtemp(prefix="excadmple-")
            needed = set()
            for step in manifest["steps"]:
                for kind in ("audio", "video"):
                    relative = step.get("media", {}).get(kind)
                    if relative:
                        needed.add(str(_relative_path(relative)))
            for filename in needed:
                if filename not in archive.namelist():
                    raise PackageError("Missing media asset: " + filename)
                dest = Path(temp) / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(filename) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            return ExamplePackage(manifest, temp, temporary=temp)
    except (zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise PackageError("Invalid example package: " + str(error)) from error
    except Exception:
        if temp:
            shutil.rmtree(temp, ignore_errors=True)
        raise
