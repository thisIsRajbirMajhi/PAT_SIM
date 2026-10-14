"""Headless-independent search-to-track pipeline (canonical implementation).

Subpackages land incrementally (Tasks 2-5); the public API in
`pat_pipeline/__init__.py` is wired once all submodules have moved.
Shared dependencies (types, enums, config defaults, visibility helpers)
stay in `fsoc_tracker` and are imported, never copied.
"""
