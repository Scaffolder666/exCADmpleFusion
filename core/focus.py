"""Reversible opacity overrides used only during Focus Mode.

Pure Python so session transitions can be tested without Autodesk Fusion.
The caller supplies entity lookups and the current design identity. This
manager does not save any opacity override into a .f3d or .excadmple package.
"""
MAX_DIM_BODIES = 250


class FocusError(RuntimeError):
    pass


class OpacityFocus:
    def __init__(self, resolve, current_design):
        self.resolve = resolve
        self.current_design = current_design
        self._originals = {}
        self._document_key = None

    @property
    def active(self):
        return bool(self._originals)

    def restore(self):
        if not self._originals:
            self._document_key = None
            return
        if self.current_design() != self._document_key:
            raise FocusError("Focus belongs to another design; activate it to restore opacity")
        failures = []
        for token, original in list(self._originals.items()):
            body = self.resolve(token)
            if body is None:
                failures.append(token)
                continue
            try:
                body.opacity = original
                del self._originals[token]
            except Exception:
                failures.append(token)
        if not self._originals:
            self._document_key = None
        if failures:
            raise FocusError("Could not restore {} body opacity override(s)".format(len(failures)))

    def apply(self, document_key, body_items, protected, dim_opacity=0.22):
        """body_items: iterable of (token, Fusion body) *native* geometry.

        All items are checked before writing. Target source bodies are never
        modified, including their other instances that share native geometry.
        """
        self.restore()
        if not document_key or self.current_design() != document_key:
            raise FocusError("Focus requires the currently active source design")
        if not 0 < dim_opacity < 1:
            raise ValueError("Opacity must be between 0 and 1")
        if not protected:
            raise FocusError("No stable target geometry identified")
        items = {}
        for token, body in body_items:
            if not token or body is None or token in protected:
                continue
            items[token] = body
        if len(items) > MAX_DIM_BODIES:
            raise FocusError("Focus supports up to {} background bodies per session".format(MAX_DIM_BODIES))
        captured = {}
        for token, body in items.items():
            try:
                captured[token] = float(body.opacity)
            except Exception as error:
                raise FocusError("Unable to capture original body opacity") from error
        self._document_key = document_key
        try:
            for token, body in items.items():
                original = captured[token]
                if original <= dim_opacity:
                    # Never make the user's already transparent geometry opaque.
                    continue
                # Record the original value before writing it to Fusion.
                self._originals[token] = original
                body.opacity = dim_opacity
        except Exception:
            self.restore()
            raise
        if not self._originals:
            self._document_key = None
        return len(self._originals)
