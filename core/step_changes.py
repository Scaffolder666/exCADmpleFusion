"""Spatial guidance for recorded geometry: what did this step add or change?

Pure Python (no Fusion). Tutorials without the designer's .f3d carry one
model snapshot per step (lists of triangle meshes). The geometry a step
created or modified is found by comparing its snapshot with the previous
step's snapshot *geometrically*:

* a mesh identical to a previous mesh (same triangles, in any vertex or
  triangle order, within a tolerance) is unchanged and skipped whole;
* in every other mesh, a triangle is unchanged when it lies on the previous
  model's surface (its centroid and three interior sample points are all
  within the tolerance of a previous triangle). Re-triangulating an
  unchanged face therefore does not count as a change; a new lip, a fillet
  surface or the walls of a cut do.

The result is only the changed triangles, so a small local feature is
highlighted without the rest of the model. Geometry that was only removed
leaves nothing to highlight; nothing is invented for it.
"""
import math

REL_TOLERANCE = 1e-3          # of the model's bounding-box diagonal
MIN_TOLERANCE = 1e-4          # cm
MAX_EXAMINED = 60000          # triangles; beyond this the comparison is skipped


def _bounds(meshes):
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for mesh in meshes:
        for v in mesh.get("vertices", []):
            for i in range(3):
                lo[i] = min(lo[i], v[i])
                hi[i] = max(hi[i], v[i])
    if lo[0] == math.inf:
        return None
    return lo, hi


def tolerance_for(meshes):
    box = _bounds(meshes)
    if box is None:
        return MIN_TOLERANCE
    diagonal = math.dist(box[0], box[1])
    return max(MIN_TOLERANCE, diagonal * REL_TOLERANCE)


def _triangles(mesh):
    vertices = mesh.get("vertices", [])
    for tri in mesh.get("triangles", []):
        try:
            a, b, c = (tuple(float(x) for x in vertices[i]) for i in tri)
        except (IndexError, TypeError, ValueError):
            continue
        yield a, b, c


def mesh_key(mesh, tol):
    """Order-independent identity of a mesh (vertices snapped to ``tol``)."""
    q = 1.0 / tol

    def snap(p):
        return tuple(int(round(c * q)) for c in p)

    return frozenset(tuple(sorted((snap(a), snap(b), snap(c)))) for a, b, c in _triangles(mesh))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def closest_point(p, a, b, c):
    """Closest point to p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = _sub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return (a[0] + v * ab[0], a[1] + v * ab[1], a[2] + v * ab[2])
    cp = _sub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return (a[0] + w * ac[0], a[1] + w * ac[1], a[2] + w * ac[2])
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        bc = _sub(c, b)
        return (b[0] + w * bc[0], b[1] + w * bc[1], b[2] + w * bc[2])
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    return (a[0] + ab[0] * v + ac[0] * w, a[1] + ab[1] * v + ac[1] * w, a[2] + ab[2] * v + ac[2] * w)


class SurfaceIndex:
    """The previous model's triangles in a uniform grid, for distance queries."""

    def __init__(self, meshes, tol):
        self.tol = tol
        self.triangles = [t for mesh in meshes for t in _triangles(mesh)]
        box = _bounds(meshes)
        size = math.dist(box[0], box[1]) if box else 1.0
        self.cell = max(size / 24.0, tol * 4.0, 1e-6)
        self.grid = {}
        for n, (a, b, c) in enumerate(self.triangles):
            lo = [min(a[i], b[i], c[i]) - tol for i in range(3)]
            hi = [max(a[i], b[i], c[i]) + tol for i in range(3)]
            ranges = [range(self._cell(lo[i]), self._cell(hi[i]) + 1) for i in range(3)]
            for x in ranges[0]:
                for y in ranges[1]:
                    for z in ranges[2]:
                        self.grid.setdefault((x, y, z), []).append(n)

    def _cell(self, value):
        return int(math.floor(value / self.cell))

    def near(self, p):
        """True when p lies within the tolerance of a previous triangle."""
        key = tuple(self._cell(p[i]) for i in range(3))
        limit = self.tol * self.tol
        for n in self.grid.get(key, ()):
            a, b, c = self.triangles[n]
            q = closest_point(p, a, b, c)
            d = _sub(p, q)
            if _dot(d, d) <= limit:
                return True
        return False


def _samples(a, b, c):
    g = ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3)
    return [g] + [((v[0] + g[0]) / 2, (v[1] + g[1]) / 2, (v[2] + g[2]) / 2) for v in (a, b, c)]


def _area2(a, b, c):
    n = _cross(_sub(b, a), _sub(c, a))
    return math.sqrt(_dot(n, n))


class ChangeDetector:
    """Compares snapshots with one fixed previous snapshot (built once)."""

    def __init__(self, previous_meshes, current_meshes=None):
        previous_meshes = list(previous_meshes or [])
        self.tol = tolerance_for(previous_meshes + list(current_meshes or []))
        # Keep the meshes alive: an id() of a freed mesh could be reused.
        self.previous = previous_meshes
        self.previous_ids = {id(m) for m in previous_meshes}
        self.previous_keys = {mesh_key(m, self.tol) for m in previous_meshes}
        self.index = SurfaceIndex(previous_meshes, self.tol) if previous_meshes else None

    def examined_count(self, meshes):
        return sum(len(m.get("triangles", [])) for m in meshes if id(m) not in self.previous_ids)

    def split(self, meshes):
        """(unchanged meshes, changed meshes) covering ``meshes`` exactly.

        Unchanged meshes are passed through as they are; a modified mesh is
        split into its unchanged and its new/modified triangles. Returns
        None when the snapshot is too large to compare (the caller then
        shows no guidance rather than a guess)."""
        if self.examined_count(meshes) > MAX_EXAMINED:
            return None
        same, changed = [], []
        for mesh in meshes:
            if id(mesh) in self.previous_ids or (
                    self.previous_keys and mesh_key(mesh, self.tol) in self.previous_keys):
                same.append(mesh)
                continue
            kept, new = _Builder(), _Builder()
            for a, b, c in _triangles(mesh):
                if _area2(a, b, c) <= self.tol * self.tol * 1e-3:
                    kept.add(a, b, c)
                elif self.index is not None and all(self.index.near(p) for p in _samples(a, b, c)):
                    kept.add(a, b, c)
                else:
                    new.add(a, b, c)
            for builder, bucket in ((kept, same), (new, changed)):
                if builder.triangles:
                    bucket.append(builder.mesh())
        return same, changed

    def changed(self, meshes):
        """Only the new or modified triangles (None: too large to compare)."""
        result = self.split(meshes)
        return None if result is None else result[1]


class _Builder:
    def __init__(self):
        self.vertices, self.triangles, self.remap = [], [], {}

    def add(self, *points):
        face = []
        for p in points:
            if p not in self.remap:
                self.remap[p] = len(self.vertices)
                self.vertices.append(list(p))
            face.append(self.remap[p])
        self.triangles.append(face)

    def mesh(self):
        return {"vertices": self.vertices, "triangles": self.triangles}


def changed_geometry(previous_meshes, current_meshes):
    """Convenience: the new/modified triangles of ``current_meshes``."""
    return ChangeDetector(previous_meshes, current_meshes).changed(list(current_meshes or []))
