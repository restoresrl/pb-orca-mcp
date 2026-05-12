"""Callback factories for ORCA error/build/progress notifications.

Each factory returns a CFUNCTYPE bound to a Python list-buffer that
accumulates events during a single ORCA call. The buffer is then drained
into structured Python objects (see tools/compile.py) before being returned
to the MCP caller.

Implemented in phase 5.
"""
