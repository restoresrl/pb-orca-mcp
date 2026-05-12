"""Discovery of local PowerBuilder IDE installations.

Enumerates all PB IDE installs on the machine (via registry + filesystem),
distinguishes IDE from runtime-only installs, and returns a structured list
with version, arch, IDE path, and ORCA DLL path.

Implemented in phase 2.
"""
