# Installation & troubleshooting

## Requirements

- **Windows**. ORCA is a Win32 DLL — there is no macOS / Linux build.
- **PowerBuilder, IDE edition**. Runtime-only installs do not ship `pborc.dll`.
  Tested with **PB 2019 R3**, **PB 2022 R3**, **PB 2025**. The ABI has been
  stable since PB 2019, so other releases should also work, but they aren't
  in the CI matrix.
- **Python 3.10+**, with the **same architecture** as the PB install.

## x86 vs x64 — the most common gotcha

PB IDE is historically **x86** across every release through 2025 (the
install dir is under `C:\Program Files (x86)\Appeon\PowerBuilder N.0\`).
`ctypes` can't load an x86 DLL from an x64 Python process, or vice versa.

If `pb-orca-mcp doctor` reports:

> No PB install is usable from this Python (x64).

… install an **x86 Python interpreter** alongside your existing one and
re-create the `uvx` tool environment from it. Example with `uv`:

```pwsh
# Install an x86 Python via uv
uv python install 3.12 --arch x86

# Recreate the pb-orca-mcp tool from that interpreter
uv tool uninstall pb-orca-mcp
uv tool install --python "3.12-x86" pb-orca-mcp
```

With `pipx` the equivalent is `pipx install --python <path-to-x86-python.exe> pb-orca-mcp`.

## Install

```pwsh
uv tool install pb-orca-mcp
# or:
pipx install pb-orca-mcp
```

After install, the `pb-orca-mcp` command is on `PATH`.

## Verify

```pwsh
pb-orca-mcp doctor
```

Lists every PB IDE installation found on the machine with version, arch,
the exact `pborc.dll` that would be loaded, and whether it's loadable from
the current Python. Example output on a developer machine with PB 19/22/25
running an x86 Python:

```
pb-orca-mcp 0.1.0
Python: 3.12.0 (x86)

[OK] PB 19.0  [x86]  C:\Program Files (x86)\Appeon\PowerBuilder 19.0
    file_version : 19.2.0.2803
    product      : 2019 R3 Build 2803
    source       : registry
    load         : OK (session entry points bound)

[OK] PB 22.0  [x86]  C:\Program Files (x86)\Appeon\PowerBuilder 22.0
    file_version : 22.2.0.3397
    product      : 2022 R3 Build 3397
    source       : registry
    load         : OK (session entry points bound)

[OK] PB 25.0  [x86]  C:\Program Files (x86)\Appeon\PowerBuilder 25.0
    file_version : 25.0.0.3683
    product      : 2025 Build 3683
    source       : registry
    load         : OK (session entry points bound)

Doctor OK: 3 usable install(s) for x86 Python.
```

`[OK]` marks versions actively tested by the project; `[??]` marks an
installed major that's outside `KNOWN_VERSIONS` (`19.0`, `22.0`, `25.0`).
Untested majors are still attempted — ORCA's ABI is stable since PB 2019.

## Discovery sources

The server merges three sources, with later ones only filling gaps:

1. **Environment variable** `PB_INSTALL_PATH` — explicit override, may
   contain a single install root or a `;`-separated list. Useful for
   portable installs.
2. **Windows registry**: `HKLM\SOFTWARE\WOW6432Node\Sybase\PowerBuilder\<X.0>`.
   Appeon kept the legacy Sybase key. Each `<X.0>` subkey contributes
   `Location` (parent dir) + `IPS Name` (subdir) for the path,
   `Build` for the file version, and `BuildFlag` for the product name.
3. **Filesystem scan** of `C:\Program Files{,(x86)}\Appeon\PowerBuilder *.0\`
   as a fallback when neither env nor registry pointed there. Sibling
   directories without `IDE\pborc.dll` (`PowerBuilderUtilities N.0\`,
   `PowerBuilder Installer\`, `Runtime Packager\`, …) are filtered out.

The version metadata comes from the registry when present; otherwise the
DLL's PE `VS_VERSION_INFO` resource is read as a fallback.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `doctor` exits 1 with "No PowerBuilder IDE installation found" | PB Runtime installed, not IDE | Install PB IDE; runtime packages don't ship `pborc.dll`. |
| `doctor` exits 1 with "No PB install is usable from this Python (x64)" | arch mismatch between Python and DLL | Install an x86 Python (see above). |
| `doctor` lists install but `load failed: Failed to load …` | DLL present but blocked (AV / Defender / SmartScreen) | Whitelist `<install>\IDE\pborc.dll` or run a clean install of the same PB version. |
| `pb_library_*` calls return `PBORCA_LIBIOERROR` | the IDE PB is open on the same PBL | Close the IDE or operate on a copy. ORCA respects PB IDE file locks. |
| `pb_set_current_application` returns `PBORCA_LIBLISTNOTSET` | called before `pb_set_library_list` | Call `pb_set_library_list` first, then `pb_set_current_application`. |
| `pb_compile_*` returns `{"error": {"name": "PB_ORCA_MCP_STATEERROR"}}` | no session open | Call `pb_session_open` first. |
| Untested major (e.g. PB 17.0) loads but a tool returns `PBORCA_UNKNOWN(...)` | ABI drift from pre-2019 release | Use PB 2019 R3 or later — pre-2019 releases are best-effort, untested. |
| `pb-orca-mcp doctor` shows an install but `IPS Name` is missing | very old install layout (pre-Appeon Sybase release) | Set `PB_INSTALL_PATH` to the install root explicitly. |

## Uninstall

```pwsh
uv tool uninstall pb-orca-mcp
# or:
pipx uninstall pb-orca-mcp
```

The package owns no on-disk state — no caches, no config files. Removing
the tool removes everything.
