"""Load and validate exCADmple design-process examples.

Standalone Python (no Fusion dependency), so the format can be tested outside CAD.
A .json manifest can reference media alongside it; a .excadmple file is a ZIP
containing manifest.json and optional relative assets.
"""
import json
import base64
import math
import shutil
import tempfile
import zipfile
from core.animation import validate_animation, AnimationError
from core.pointer import validate_pointer, PointerError
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


def _validate_step_sources(step):
    """What was recorded for a step: the tools used and the timeline
    features of the designer's model it covers."""
    tools = step.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise PackageError("tools must be a list of tool names")
    sources = step.get("source_features", [])
    if not isinstance(sources, list) or not all(isinstance(f, dict) and isinstance(f.get("name"), str) for f in sources):
        raise PackageError("source_features must list timeline features")


def _expand_mesh_refs(data):
    """Steps may refer to meshes by id in a package-level "meshes" library
    (consecutive model states share most bodies). Replace ids with the mesh
    objects (shared, not copied)."""
    library = data.get("meshes")
    if library is None:
        return data
    if not isinstance(library, dict):
        raise PackageError("meshes must map ids to meshes")
    for mesh in library.values():
        _validate_mesh(mesh)

    def resolve(items):
        out = []
        for item in items:
            if isinstance(item, str):
                if item not in library:
                    raise PackageError("Unknown mesh id " + item)
                out.append(library[item])
            else:
                out.append(item)
        return out

    for step in data.get("steps", []) if isinstance(data.get("steps"), list) else []:
        if not isinstance(step, dict):
            continue
        geometry = step.get("geometry")
        if isinstance(geometry, dict) and isinstance(geometry.get("meshes"), list):
            geometry["meshes"] = resolve(geometry["meshes"])
        animation = step.get("animation")
        if isinstance(animation, dict) and isinstance(animation.get("states"), list):
            animation["states"] = [resolve(state) if isinstance(state, list) else state
                                   for state in animation["states"]]
    return data


def _validate(data):
    if not isinstance(data, dict) or data.get("format") != "excadmple" or data.get("version") not in (1, 2):
        raise PackageError("Expected exCADmple format version 1 or 2")
    _expand_mesh_refs(data)
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise PackageError("Package title is required")
    for field in ("preview", "source_model"):
        if data.get(field):
            _relative_path(data[field])
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
        if step.get("animation") is not None:
            try:
                validate_animation(step["animation"])
            except AnimationError as exc:
                raise PackageError(str(exc)) from exc
            for mesh in step["animation"].get("context_meshes", []):
                _validate_mesh(mesh)
        for kind in ("audio", "video"):
            asset = step.get("media", {}).get(kind)
            if asset is not None:
                _relative_path(asset)
        offset = step.get("media", {}).get("offset_ms", 0)
        if isinstance(offset, bool) or not isinstance(offset, (int, float)) or offset < 0:
            raise PackageError("media.offset_ms must be a non-negative number")
        _validate_step_sources(step)
        if step.get("pointer") is not None:
            try:
                validate_pointer(step["pointer"], duration)
            except PointerError as exc:
                raise PackageError(str(exc)) from exc
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
    def __init__(self, data, asset_root, temporary=None, source_path=None):
        self.data = _validate(data)
        self.asset_root = Path(asset_root).resolve()
        self.temporary = temporary
        self.source_path = Path(source_path).resolve() if source_path else None

    def source_model_path(self):
        """The designer's .f3d shipped with the example, if any."""
        relative = self.data.get("source_model")
        if not relative:
            return None
        path = (self.asset_root / str(_relative_path(relative))).resolve()
        if not path.is_relative_to(self.asset_root) or not path.is_file() or path.suffix.lower() != ".f3d":
            return None
        return path

    def close(self):
        if self.temporary:
            shutil.rmtree(self.temporary, ignore_errors=True)
            self.temporary = None

    def player_data(self):
        """Minimal metadata for HTML. Geometry stays Python-side."""
        result = {
            "version": self.data.get("version", 1),
            "id": self.data.get("id", ""),
            "title": self.data["title"],
            "description": self.data.get("description", ""),
            "preview_data_uri": None,
            "source_model_included": bool(self.data.get("source_model")),
            "steps": []
        }
        preview = self.data.get("preview")
        if preview:
            path = (self.asset_root / str(_relative_path(preview))).resolve()
            if path.is_relative_to(self.asset_root) and path.is_file() and path.suffix.lower() == ".png":
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise PackageError("Preview PNG too large")
                result["preview_data_uri"] = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        for step in self.data["steps"]:
            meta = {k: v for k, v in step.items() if k not in ("geometry", "media", "animation", "pointer")}
            meta["pointer_available"] = bool(step.get("pointer"))
            # UI can indicate whether a real per-step 3D snapshot exists,
            # distinct from the package's static final-model preview.
            meta["has_geometry"] = bool(step.get("geometry", {}).get("meshes"))
            meta["animation_available"] = bool(step.get("animation"))
            media = {}
            for kind in ("video", "audio"):
                resource = step.get("media", {}).get(kind)
                if resource:
                    path = (self.asset_root / str(_relative_path(resource))).resolve()
                    if not path.is_relative_to(self.asset_root):
                        raise PackageError("Media path escapes package directory")
                    if path.is_file():
                        media[kind] = path.as_uri()
            if media and step.get("media", {}).get("offset_ms"):
                # One long think-aloud recording: this step is a time slice of it.
                media["offset_ms"] = step["media"]["offset_ms"]
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
        data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("format") == "excadmple-pair":
            from .example_pair import LocalPairPackage
            return LocalPairPackage(data, source)
        return ExamplePackage(data, source.parent, source_path=source)
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
            if manifest.get("preview"):
                needed.add(str(_relative_path(manifest["preview"])))
            # The designer's .f3d is extracted so the reference instance (version A)
            # can open a copy of it; it is never imported into the user's design.
            if manifest.get("source_model"):
                if manifest["source_model"] not in archive.namelist():
                    raise PackageError("Missing source model in package")
                needed.add(str(_relative_path(manifest["source_model"])))
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
            return ExamplePackage(manifest, temp, temporary=temp, source_path=source)
    except (zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise PackageError("Invalid example package: " + str(error)) from error
    except Exception:
        if temp:
            shutil.rmtree(temp, ignore_errors=True)
        raise
