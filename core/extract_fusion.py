"""Compatibility import; implementation lives in core.tutorial.extract_fusion."""
from importlib import import_module as _import_module
_impl = _import_module("core.tutorial.extract_fusion")
import sys as _sys
_sys.modules[__name__] = _impl
