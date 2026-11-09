"""Compatibility import; implementation lives in core.playback.him_motion."""
from importlib import import_module as _import_module
_impl = _import_module("core.playback.him_motion")
import sys as _sys
_sys.modules[__name__] = _impl
