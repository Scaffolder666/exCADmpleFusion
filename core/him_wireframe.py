"""Compatibility import; implementation lives in core.playback.him_wireframe."""
from importlib import import_module as _import_module
_impl = _import_module("core.playback.him_wireframe")
import sys as _sys
_sys.modules[__name__] = _impl
# `from core import module` must resolve to the same implementation object.
setattr(_sys.modules[__package__], __name__.rsplit('.', 1)[-1], _impl)
