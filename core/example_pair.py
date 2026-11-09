"""Compatibility import; implementation lives in core.tutorial.example_pair."""
from importlib import import_module as _import_module
_impl = _import_module("core.tutorial.example_pair")
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
