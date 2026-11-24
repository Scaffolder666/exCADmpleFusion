"""Pure geometry + teaching timeline for the Blender in-viewport tutorial.

This module deliberately imports NO bpy, bmesh, gpu, or Blender objects.
A reference object is a transient GPU drawing, never a Mesh datablock.
The five manually-authored demonstration moments are NOT inferred history.
"""
from dataclasses import dataclass

OFFSET_X = 4.6
HALF_WIDTH = 1.6
REAR_START_Y = 0.72
REAR_END_Y = 1.0
BASE_THICKNESS = 0.22
EXTRUDE_DISTANCE = 2.4

PHASES = (
    ("tool", 2.1, "EXTRUDE REGION", "Edit Mode  |  Face Select [3]  |  Extrude [E]"),
    ("face", 2.2, "SELECT THE SOURCE FACE", "Select the highlighted rear strip on top of the base"),
    ("extrude", 4.5, "EXTRUDE ALONG Z", "Press E, move upward and watch the selected face extend"),
    ("parameter", 1.7, "ENTER THE DISTANCE", "Type 2.4, then press Enter to confirm"),
    ("why", 3.5, "WHY THIS SUPPORT HEIGHT?", "The example design keeps a wide base while raising the phone support"),
)
TOTAL_SECONDS = sum(p[1] for p in PHASES)
WHY_SOURCE = "Authored demo rationale · not the original designer's recorded intent"


@dataclass(frozen=True)
class Moment:
    index: int
    name: str
    title: str
    hint: str
    start: float
    duration: float
    fraction: float


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def moment_at(seconds):
    """Deterministic seek works forwards AND backwards without modifying scene."""
    t = clamp(float(seconds), 0.0, TOTAL_SECONDS)
    previous = 0.0
    for i, (name, duration, title, hint) in enumerate(PHASES):
        if t < previous + duration or i == len(PHASES) - 1:
            return Moment(i, name, title, hint, previous, duration,
                          clamp((t - previous) / duration))
        previous += duration
    raise AssertionError("unreachable")


def moment_start(index):
    return sum(p[1] for p in PHASES[:max(0, min(len(PHASES), int(index)))])


def smoothstep(x):
    u = clamp(x)
    return u * u * (3.0 - 2.0 * u)


def extrude_height(seconds):
    moment = moment_at(seconds)
    if moment.index < 2:
        return 0.0
    if moment.index == 2:
        return EXTRUDE_DISTANCE * smoothstep(moment.fraction)
    return EXTRUDE_DISTANCE


def practice_base_mesh(x_offset=0.0):
    """Manifold slab with TWO top faces, so its REAR FACE is genuinely
    selectable and extrudable in Blender Edit Mode (not a fictitious
    colored subregion of a single top face).
    Returns (vertices, quads), no Blender dependency.
    """
    xs = (-HALF_WIDTH + x_offset, HALF_WIDTH + x_offset)
    ys = (-1.0, REAR_START_Y, REAR_END_Y)
    zs = (0.0, BASE_THICKNESS)
    vertices = [(x, y, z) for x in xs for y in ys for z in zs]
    idx = lambda x, y, z: (x * 3 + y) * 2 + z
    quads = []
    for j in range(2):
        # Top + bottom, both segmented across the y-axis.
        quads.append((idx(0,j,1),idx(1,j,1),
                      idx(1,j+1,1),idx(0,j+1,1)))
        quads.append((idx(0,j+1,0),idx(1,j+1,0),
                      idx(1,j,0),idx(0,j,0)))
        quads.append((idx(0,j,0),idx(0,j,1),
                      idx(0,j+1,1),idx(0,j+1,0)))
        quads.append((idx(1,j+1,0),idx(1,j+1,1),
                      idx(1,j,1),idx(1,j,0)))
    # Front and rear caps close the manifold.
    quads.append((idx(0,0,0),idx(1,0,0),idx(1,0,1),idx(0,0,1)))
    quads.append((idx(1,2,0),idx(0,2,0),idx(0,2,1),idx(1,2,1)))
    return vertices, quads


def extrude_wall_mesh(height):
    """Vertical rear support created by extruding the real rear top face.
    Returns only visible sides and top (no hidden bottom cap)."""
    h = max(0.0, float(height))
    if h <= 1.e-5:
        return [], []
    xs = (OFFSET_X-HALF_WIDTH, OFFSET_X+HALF_WIDTH)
    ys = (REAR_START_Y, REAR_END_Y)
    z0 = BASE_THICKNESS
    zs = (z0, z0+h)
    vertices = [(x,y,z) for x in xs for y in ys for z in zs]
    idx = lambda xi,yi,zi: (xi*2+yi)*2+zi
    quads = [
        (idx(0,0,1),idx(1,0,1),idx(1,1,1),idx(0,1,1)), # roof
        (idx(0,0,0),idx(1,0,0),idx(1,0,1),idx(0,0,1)), # front
        (idx(1,1,0),idx(0,1,0),idx(0,1,1),idx(1,1,1)), # rear
        (idx(0,1,0),idx(0,0,0),idx(0,0,1),idx(0,1,1)), # left
        (idx(1,0,0),idx(1,1,0),idx(1,1,1),idx(1,0,1)), # right
    ]
    return vertices, quads


def highlight_face(height=0.0):
    """Corresponding 3D face vertices for yellow face-selection highlight."""
    z = BASE_THICKNESS + max(0.0, height) + 0.005
    return ((OFFSET_X-HALF_WIDTH, REAR_START_Y, z),
            (OFFSET_X+HALF_WIDTH, REAR_START_Y, z),
            (OFFSET_X+HALF_WIDTH, REAR_END_Y, z),
            (OFFSET_X-HALF_WIDTH, REAR_END_Y, z))


def anchor_at(seconds):
    h = extrude_height(seconds)
    return (OFFSET_X, (REAR_START_Y+REAR_END_Y)*0.5,
            BASE_THICKNESS + (h if h > 0 else 0.0))


def quads_to_triangles(vertices, quads):
    """GPU-ready vertex positions, independent of Blender render APIs."""
    out = []
    for a,b,c,d in quads:
        out.extend((vertices[a],vertices[b],vertices[c],
                    vertices[a],vertices[c],vertices[d]))
    return out


def unique_edges(vertices, quads):
    edges = set()
    for q in quads:
        for a,b in zip(q,q[1:]+q[:1]):
            edges.add(tuple(sorted((a,b))))
    return [(vertices[a],vertices[b]) for a,b in sorted(edges)]


def snapshot(seconds):
    """All expert drawing is generated from scratch at arbitrary time t."""
    m = moment_at(seconds)
    base_verts, base_faces = practice_base_mesh(OFFSET_X)
    wall_verts, wall_faces = extrude_wall_mesh(extrude_height(seconds))
    return {
        "moment": m,
        "height": extrude_height(seconds),
        "base_vertices": base_verts,
        "base_faces": base_faces,
        "wall_vertices": wall_verts,
        "wall_faces": wall_faces,
        "face": highlight_face(extrude_height(seconds)),
        "anchor": anchor_at(seconds),
    }
