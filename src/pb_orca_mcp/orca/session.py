"""Singleton ORCA session wrapper.

ORCA is single-session per process. The Session object owns the HPBORCA
handle, tracks (version, arch) of the loaded DLL, and keeps callback
CFUNCTYPE references alive in `_callback_refs` to prevent GC-induced crashes.

Implemented in phase 3.
"""
