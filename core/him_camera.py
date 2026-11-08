"""Frame native feature bounds without changing the user's viewing direction."""
import math


def focus_geometry(viewport, geometries, point_factory):
    boxes = []
    for entity in geometries:
        try:
            box = entity.boundingBox
            lo = tuple(getattr(box.minPoint, a) for a in 'xyz')
            hi = tuple(getattr(box.maxPoint, a) for a in 'xyz')
            if all(math.isfinite(v) for v in lo + hi):
                boxes.append((lo, hi))
        except Exception:
            continue
    if not boxes:
        return False
    low = [min(b[0][i] for b in boxes) for i in range(3)]
    high = [max(b[1][i] for b in boxes) for i in range(3)]
    center = [(a + b) / 2 for a, b in zip(low, high)]
    radius = max(.01, math.sqrt(sum((b-a)**2 for a, b in zip(low, high))) / 2) * 1.3
    camera = viewport.camera
    direction = [getattr(camera.eye, a) - getattr(camera.target, a) for a in 'xyz']
    camera.target = point_factory(*center)
    camera.eye = point_factory(*(center[i] + direction[i] for i in range(3)))
    camera.isFitView = False
    # setExtents is the current orthographic API. Perspective cameras expose
    # sphere-based viewExtents for compatibility; it adjusts eye/FOV natively.
    try:
        fitted = camera.setExtents(2 * radius, 2 * radius)
    except (AttributeError, RuntimeError):
        fitted = False
    if not fitted:
        camera.viewExtents = radius
    camera.isSmoothTransition = True
    viewport.camera = camera
    return True
