"""Session-only, document-scoped step -> geometry bindings.

Tokens are never compared as object identity, and never assumed to work across
other CAD documents. The source design and package are never modified.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GeometryLink:
    token: str
    label: str
    kind: str
    document_key: str

    def for_ui(self, available):
        return {
            "label": self.label,
            "kind": self.kind,
            "available": bool(available),
        }


class GeometryLinks:
    def __init__(self):
        self._links = {}

    def clear(self):
        self._links.clear()

    def bind(self, step_id, document_key, token, label, kind):
        if not all(isinstance(v, str) and v for v in (step_id, document_key, token, label, kind)):
            raise ValueError("A geometry link requires a step, document, entity token, and label")
        if kind not in ("body", "face", "occurrence"):
            raise ValueError("Supported geometry: body, face, occurrence")
        link = GeometryLink(token=token, label=label, kind=kind, document_key=document_key)
        self._links[step_id] = link
        return link

    def get(self, step_id, document_key):
        link = self._links.get(step_id)
        if link and link.document_key == document_key:
            return link
        return None

    def remove(self, step_id):
        return self._links.pop(step_id, None) is not None

    def display(self, steps, document_key):
        return {item["id"]: (self._links[item["id"]].for_ui(
            self._links[item["id"]].document_key == document_key
        ) if item["id"] in self._links else None) for item in steps}
