"""Find a real reference feature's position in the learner's single viewport.

The source .f3d remains an independent document. Its Custom Graphics are
translated by SameViewportPresenter.offset. Fusion's Viewport API can project
the feature's real 3D bounding-box center to a 2D screen coordinate.
Return None for unprojectable features instead of guessing a target.
"""
import adsk.core


def _center(obj):
    bounds = getattr(obj, "boundingBox", None)
    if bounds is None:
        for attr in ("bodies", "faces", "edges"):
            collection = getattr(obj, attr, None)
            if collection is None:
                continue
            try:
                if collection.count:
                    bounds = getattr(collection.item(0), "boundingBox", None)
                    if bounds:
                        break
            except Exception:
                continue
    if bounds is None:
        return None
    a,b = bounds.minPoint, bounds.maxPoint
    return ((a.x+b.x)*.5,(a.y+b.y)*.5,(a.z+b.z)*.5)


def screen_anchor(app,session,step_index):
    try:
        if (not session or not session.live or not session.presenter.attached
                or not 0 <= step_index < len(session.mapped)):
            return None
        for feature in reversed(session.mapped[step_index]):
            entity = session.model.entity(feature)
            center = _center(entity)
            if center is None:
                continue
            offset = session.presenter.offset
            p=adsk.core.Point3D.create(
                center[0]+offset[0],center[1]+offset[1],center[2]+offset[2])
            viewport=app.activeViewport
            view=viewport.modelToViewSpace(p)
            screen=viewport.viewToScreen(view)
            if screen is not None:
                return [float(screen.x),float(screen.y)]
    except Exception:
        return None
    return None
