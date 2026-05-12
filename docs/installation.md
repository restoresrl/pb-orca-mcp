# Installation & troubleshooting

> **Status**: phase 1 scaffolding — written content arrives with phase 2 (discovery)
> and phase 7 (packaging + docs).

## Requirements

- Windows
- PowerBuilder, **IDE edition** (runtime-only installs do not ship `pborc.dll`).
  Tested with PB 2019 R3, 2022 R3, 2025; older releases that ship `pborc.dll`
  should also work but aren't covered by CI.
- Python 3.10+ matching the architecture of the PB install (the IDE is
  historically x86; some recent releases also ship x64 builds)

## Install

```pwsh
uv tool install pb-orca-mcp
# or
pipx install pb-orca-mcp
```

## Verify

```pwsh
pb-orca-mcp doctor
```

Should list every PB IDE installation it found, with version, arch, and the
exact `pborc.dll` it would load.

## Troubleshooting

(TODO — phases 2 & 7)

- Registry not found
- Wrong architecture mismatch (x86 Python + x64 DLL)
- Runtime-only install detected
- DLL locked by a running PB IDE
