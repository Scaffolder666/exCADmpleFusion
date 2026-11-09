"""Compatibility import; implementation lives in core.tutorial.reference_plan."""
from importlib import import_module as _import_module
_impl = _import_module("core.tutorial.reference_plan")
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
