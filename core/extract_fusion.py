"""Compatibility import; implementation lives in core.tutorial.extract_fusion."""
from importlib import import_module as _import_module
_impl = _import_module("core.tutorial.extract_fusion")
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
