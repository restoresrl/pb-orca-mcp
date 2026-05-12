# Server MCP `pb-orca-mcp` — Bridge Claude Code ↔ PowerBuilder via ORCA

## Context

PowerBuilder è un IDE "closed-world": un agente AI come Claude Code può oggi leggere/scrivere i sorgenti estratti (`ws_objects/src/<pbl>.pbl.src/*.sr*`) ma **non può compilare, validare, ispezionare le PBL, o produrre EXE/PBD** senza che un umano apra l'IDE o lanci PowerGen. Risultato: il loop "modifica → compila → leggi errori → correggi" — che è il cuore del coding agentico — su PB è rotto.

ORCA (PowerBuilder Open Repository CASE API, distribuita come `pborc.dll` in ogni installazione PB IDE sotto `<install>\IDE\`) espone in C tutto quello che serve per chiudere il loop: aprire una sessione, listare PBL, esportare/importare entry, compilare con callback di errore, fare full-rebuild di un target, costruire EXE/PBD, navigare gerarchie di ereditarietà e cross-reference. Storicamente PowerGen wrappa ORCA — quello che PowerGen fa per la build batch, ORCA permette di farlo programmaticamente.

L'obiettivo è un **server MCP generico** (non specifico a un singolo vendor o workspace) che esponga l'API ORCA come tool MCP, permettendo a chi sviluppa con PB di abilitare un workflow agentico completo in Claude Code. Scope: "tutte le funzioni esposte da ORCA" — Claude deve potere operare in autonomia su PB. Funziona con **qualsiasi versione di PB che fornisca `pborc.dll`** (ABI stabile da PB 2019); copertura di test attiva su PB 2019 R3, 2022 R3, 2025.

## Decisioni di scope

> **Aggiornamento post-Ultraplan (sessione `session_01XLVQLNEXbiUbmeMCVPMnJw`)**: i raffinamenti elencati qui sotto sono entrati nel piano dopo la review remota.

- **Multi-version PB IDE come requisito core (non rinviato)**: il server v1 deve riconoscere e caricare DLL distinte da installazioni PB coesistenti sulla stessa macchina (es. PB 2019 R3 + 2022 R3 + 2025 in parallelo). Tutte le release shipano la stessa DLL `pborc.dll` (no suffisso versione) dentro `<install>\IDE\`; il loader sceglie l'installazione corretta per ogni target invece di puntare a una sola installazione globale.
- **Discovery con distinzione IDE vs runtime**: l'installer PowerBuilder genera due famiglie di installazione — "IDE" (contiene `PowerBuilder.exe`, `pborc.dll`, SDK headers) e "runtime" (solo VM PB, senza ORCA). Il discovery deve **filtrare e ignorare le installazioni runtime-only** e segnalarle in `pb_discover_pb_install` come "ORCA not available" invece di crashare al primo `LoadLibrary`.
- **Selezione versione PB esplicita**: il chiamante deve sempre indicare quale installazione PB usare, via `pb_version` (es. `"22.0"`) o `install_path` esplicito al momento di `pb_session_open`. Niente auto-pick, niente inferenza da `.pbt`/`.pbw`: i file di progetto/workspace PB **non contengono la versione PB** — l'unico header presente è il magic costante `Save Format v3.0(19990112)` (format del file, congelato dal 1999). Il tool `pb_target_info` resta utile per estrarre `appname`/`applib`/`lib_list`/`type` (e per `.pbw`, lista dei target), ma non popola `pb_version`. Eventuale inferenza dall'header binario delle PBL è valutabile in una fase successiva, non è in v1.
- **Linguaggio**: Python 3.10+, binding con `ctypes`. SDK MCP `mcp` (ufficiale Anthropic).
- **Distribuzione**: package PyPI `pb-orca-mcp`, installabile con `uv tool install` / `pipx install`. Snippet `.claude/mcp.json` per integrazione.
- **Architettura**: l'arch del runtime Python deve coincidere con l'arch della `pborc.dll` caricata (storicamente l'IDE PB è x86; alcune release recenti hanno anche build x64). Il discovery riporta l'arch per ogni installazione e il loader rifiuta mismatch con un errore comprensibile.
- **Audience**: chiunque sviluppi PB. Niente hardcoded path / convenzioni vendor-specifiche nel core. Eventuali ricette workspace-specifiche stanno in un capitolo separato della docs.

## Architettura

### Componenti

```
pb-orca-mcp/
├── pyproject.toml
├── README.md
├── docs/
│   ├── tools.md              # ref di ogni tool MCP
│   ├── installation.md       # registry discovery, x86/x64, troubleshooting
│   ├── recipes.md            # workflow tipici (compile-test loop, rebuild target)
│   └── claude-code-setup.md  # snippet .claude/mcp.json
├── src/pb_orca_mcp/
│   ├── __init__.py
│   ├── __main__.py           # entry point CLI (uvicorn-like)
│   ├── server.py             # MCP server bootstrap + tool registration
│   ├── config.py             # config schema (env + TOML opzionale)
│   ├── discovery.py          # localizza install PB via registry / env
│   ├── orca/
│   │   ├── __init__.py
│   │   ├── dll.py            # ctypes CDLL load + prototypes
│   │   ├── types.py          # ctypes.Structure per PBORCA_*
│   │   ├── constants.py      # PBORCA_OK, error codes, entry types
│   │   ├── session.py        # singleton wrapper sessione
│   │   ├── callbacks.py      # CFUNCTYPE per error/build/progress
│   │   └── errors.py         # eccezioni Python + error decoder
│   └── tools/
│       ├── __init__.py
│       ├── session.py        # Open/Close/SetCurrentAppl/SetLibraryList
│       ├── library.py        # Create/Delete/Directory/EntryInfo/Export/Delete/Move/Comment
│       ├── compile.py        # CompileEntryImport(List)/ApplicationRebuild
│       ├── build.py          # ExecutableCreate/DynamicLibraryCreate
│       └── query.py          # ObjectQueryHierarchy/Reference/ObjectRegenerate
└── tests/
    ├── conftest.py
    ├── test_discovery.py
    ├── test_dll_loading.py
    ├── test_session.py
    ├── test_library_ops.py
    ├── test_compile.py
    └── fixtures/
        └── tiny_app/         # minimo .pbt + 2 PBL + 3-4 oggetti, per test E2E reali
```

### Modello di sessione

ORCA è **single-session per process**. Il server MCP mantiene una sola sessione attiva, persistente attraverso le tool call dello stesso process:

- `pb_session_open` → carica il `pborc.dll` dell'installazione scelta, chiama `PBORCA_SessionOpen`, memorizza l'handle (`HPBORCA`).
- Tutti i tool successivi prendono l'handle dalla sessione globale.
- `pb_set_current_application` (`PBORCA_SessionSetCurrentAppl`) configura target+app+LibList correnti — necessario prima di Compile/Rebuild/ObjectQuery.
- `pb_session_close` → `PBORCA_SessionClose` + unload DLL.
- Cleanup automatico su shutdown del server (atexit hook).

Cambio di target = close + reopen della sessione (più robusto che riusare la sessione).

### Binding ctypes — note implementative

- Stringhe PB sono UTF-16 LE → `c_wchar_p` (LPCWSTR).
- Calling convention: ORCA è `__cdecl` su Windows → `ctypes.CDLL` (non `WinDLL`).
- Struct `PBORCA_DIRENTRY`, `PBORCA_COMPERR`, `PBORCA_HIER_DIRENTRY` ecc. → `ctypes.Structure` con `_fields_` esatto dall'header `PBORCA.H` (distribuito con PB SDK).
- Callbacks (error/build/progress) registrati con `CFUNCTYPE(None, POINTER(...), c_void_p)`. **Le callback Python vanno tenute referenced** per tutta la durata della chiamata (altrimenti GC = crash); le mettiamo in `Session._callback_refs`.
- Wrapper Pythonic ritorna eccezioni `OrcaError(code, name, message)` invece di codici di ritorno raw.

### Tool MCP esposti (mapping completo API ORCA → tool)

| Tool MCP | Funzione ORCA | Note |
|---|---|---|
| `pb_discover_pb_install` | (registry/env scan) | Ritorna **lista** di installazioni PB IDE valide (con versione + arch + path DLL), escludendo i runtime-only |
| `pb_target_info` | (parser `.pbt`/`.pbw`) | Estrae AppName, applib, LibList, type dal `.pbt`; per `.pbw` lista dei target. **Non** ritorna `pb_version` (i file di progetto/workspace PB non la contengono, vedi §"Parser `.pbt` / `.pbw`") |
| `pb_session_open` | `PBORCA_SessionOpen` | Richiede selezione esplicita dell'installazione: parametro `install_path` oppure `pb_version` (es. "19.0", "22.0", "25.0"). Nessuna inferenza automatica |
| `pb_session_close` | `PBORCA_SessionClose` | |
| `pb_set_current_application` | `PBORCA_SessionSetCurrentAppl` | Setta target/PBT/LibList |
| `pb_set_library_list` | `PBORCA_SessionSetLibraryList` | Override LibList post-open |
| `pb_library_create` | `PBORCA_LibraryCreate` | |
| `pb_library_delete` | `PBORCA_LibraryDelete` | |
| `pb_library_directory` | `PBORCA_LibraryDirectory` | Ritorna lista entry con tipo/comment/dimensione |
| `pb_library_entry_information` | `PBORCA_LibraryEntryInformation` | Metadata di un singolo entry |
| `pb_library_entry_export` | `PBORCA_LibraryEntryExport` | Estrae source dell'oggetto |
| `pb_library_entry_delete` | `PBORCA_LibraryEntryDelete` | |
| `pb_library_entry_move` | `PBORCA_LibraryEntryMove` | Sposta tra PBL |
| `pb_library_comment_modify` | `PBORCA_LibraryCommentModify` | |
| `pb_library_entry_comment_modify` | `PBORCA_LibraryEntryCommentModify` | |
| `pb_compile_entry_import` | `PBORCA_CompileEntryImport` | Singola entry da source file |
| `pb_compile_entry_import_list` | `PBORCA_CompileEntryImportList` | Batch import + compile |
| `pb_application_rebuild` | `PBORCA_ApplicationRebuild` | Full/incremental/migrate (sostituisce `BuildProject*` deprecati in R3) |
| `pb_executable_create` | `PBORCA_ExecutableCreate` | Build EXE, con PBR/icon/flag machine code |
| `pb_dynamic_library_create` | `PBORCA_DynamicLibraryCreate` | Build PBD da una PBL |
| `pb_object_query_hierarchy` | `PBORCA_ObjectQueryHierarchy` | Catena di ereditarietà |
| `pb_object_query_reference` | `PBORCA_ObjectQueryReference` | Chi referenzia chi |
| `pb_object_regenerate` | `PBORCA_ObjectRegenerate` | Rebuild singolo oggetto |
| `pb_get_last_compile_errors` | (buffer interno) | Errori dall'ultima Compile/Rebuild call |

Tool **non** esposti in v1 (esistono in ORCA ma valore marginale per agente):
- `PBORCA_Scc*` (source control connector) — la maggior parte degli utenti PB moderni usa git, non MSSCCI.
- `PBORCA_BuildProject` / `BuildProjectEx` / `BuildProjectWithOverrides` — **deprecati in R3**, usiamo `ApplicationRebuild`.

### Schema input/output dei tool (pattern)

Esempio `pb_library_directory`:

```json
// input
{
  "pbl_path": "C:\\projects\\myapp\\src\\main.pbl",
  "entry_type": "any"  // "any" | "application" | "datawindow" | "function" | "menu" | "query" | "structure" | "userobject" | "window" | "pipeline" | "project" | "proxy" | "binary"
}

// output (success)
{
  "entries": [
    {"name": "n_cst_main", "type": "userobject", "size_source": 12450, "size_object": 8920, "modified": "2026-04-12T10:22:14", "comment": ""},
    {"name": "w_main", "type": "window", ...}
  ],
  "count": 87
}

// output (error)
{
  "error": {"code": -3, "name": "PBORCA_DIROPENERR", "message": "Cannot open directory: file locked by PB IDE"}
}
```

Errori di compile arrivano come array strutturato:

```json
{
  "success": false,
  "errors": [
    {"object": "n_cst_main", "line": 142, "column": 8, "severity": "error", "message": "Undefined function: getfoo"},
    {"object": "n_cst_main", "line": 158, "column": 1, "severity": "warning", "message": "Unreferenced variable: ll_unused"}
  ]
}
```

### Discovery installazione PB (multi-version, IDE-only)

`discovery.py` enumera **tutte** le installazioni PB IDE presenti sulla macchina e ritorna una lista strutturata. Sorgenti consultate (unite, dedup):

1. Env var `PB_INSTALL_PATH` (override esplicito; può essere lista CSV).
2. Registry: `HKLM\SOFTWARE\WOW6432Node\Sybase\PowerBuilder\<X.0>` (e hive 64-bit equivalente). Appeon ha mantenuto la chiave legacy Sybase — la chiave `HKLM\SOFTWARE\Sybase\PowerBuilder` (senza `WOW6432Node`) **non esiste** sulle macchine osservate. Le subkey trovate (`19.0`, `22.0`, `25.0`, …) sono i candidati major version. Per ogni subkey i valori utili sono: `Location` (= **parent** directory, es. `C:\Program Files (x86)\Appeon`, **non** l'install dir esatta), `IPS Name` (= subdir, es. `PowerBuilder 22.0`), `Build` (= file version completa, es. `22.2.0.3397`), `BuildFlag` (= product version human-readable, es. `2022 R3`), `VersionMajor`/`VersionMinor`. L'install dir si ricostruisce come `Location + "\" + "IPS Name"`.
3. Filesystem scan dei path standard: `C:\Program Files\Appeon\PowerBuilder *.0\` e `C:\Program Files (x86)\Appeon\PowerBuilder *.0\` (l'IDE PB è storicamente x86). Filtrare i sibling con stesso prefisso ma diverso ruolo (`PowerBuilderUtilities X.0\`, `PowerBuilder Installer\`, `Runtime Packager\`, `PowerBuilderCompiler X.0\` — tutti privi di `IDE\pborc.dll`).

Per ogni candidato verifica:
- Presenza di `<install>\IDE\pborc.dll` (no suffisso versione: il nome è invariato fra release; **case varia**: PB 19.0 ship `PBORC.DLL` uppercase, PB 22.0/25.0 lowercase — Windows filesystem è case-insensitive comunque). **Se manca → è un'installazione "runtime" o non-IDE, scartata** e segnalata separatamente nel return.
- Architettura della DLL (PE header `Machine` field a offset `0x3C → PE+4`: `0x14c` = x86, `0x8664` = x64). Implementato in `_pe.py` con `struct.unpack`, senza dipendenze esterne.
- Versione esatta. **Sorgente primaria: registry** (campi `Build` + `BuildFlag` già normalizzati). **Fallback se l'install è stata trovata solo via filesystem**: `VersionInfo` PE del DLL — `FileVersion` (es. `22.2.0.3397`) e `ProductVersion` (testo human-readable, es. `2022 R3 Build 3397`).

Output di `pb_discover_pb_install`:

```json
{
  "ide_installations": [
    {
      "version": "22.0",
      "file_version": "22.2.0.3397",
      "product_version": "2022 R3 Build 3397",
      "arch": "x86",
      "install_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0",
      "ide_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0\\IDE",
      "orca_dll": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0\\IDE\\pborc.dll",
      "tested": true
    },
    {
      "version": "25.0",
      "file_version": "25.0.0.3683",
      "product_version": "2025 Build 3683",
      "arch": "x86",
      "install_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 25.0",
      "ide_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 25.0\\IDE",
      "orca_dll": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 25.0\\IDE\\pborc.dll",
      "tested": true
    }
  ],
  "runtime_only_installations": [
    {"version": "22.0", "arch": "x86", "path": "C:\\Program Files (x86)\\Appeon\\Runtime 22.0", "reason": "pborc.dll missing"}
  ]
}
```

`tested: true` per le major version in `KNOWN_VERSIONS` (`19.0`, `22.0`, `25.0` in v1). Versioni trovate ma non testate (es. PB 17.0, 21.0, future 26.0) compaiono comunque nella lista con `tested: false` — il loader prova a caricarle assumendo l'ABI ORCA stabile da PB 2019.

### Loader DLL version-aware

`orca/dll.py` non è un singleton globale ma una factory: `load_orca(install: PbInstall) -> OrcaApi` riceve un `PbInstall` (output di discovery) e ritorna un oggetto che wrappa il `pborc.dll` di quella specifica installazione con i prototypes ORCA. Le firme ORCA sono **stabili da PB 2019 in poi** (ABI non viene più toccata; verificato su PB 2019 R3, 2022 R3, 2025), quindi un singolo set di prototypes copre tutte le release moderne. Il loader resta version-aware per:
- scegliere fra DLL coesistenti sulla macchina (più install PB in parallelo);
- gestire eventuali divergenze future (es. struct nuove in una release N) senza riscrivere il discovery;
- emettere un warning leggibile quando carica una versione non in `KNOWN_VERSIONS` (`tested: false`).

`KNOWN_VERSIONS = ("19.0", "22.0", "25.0")` in v1 — è una lista di versioni testate, non un gate: il discovery accetta qualsiasi installazione con `pborc.dll` presente.

La sessione ORCA è singleton **per process**, ma il `Session` object ricorda quale `PbInstall` ha aperto: switch di versione = close + reopen.

### Parser `.pbt` / `.pbw`

Il `.pbt` (text format) e il `.pbw` (workspace) condividono la stessa sintassi minimale. Formato verificato su 5 `.pbt` + 3 `.pbw` reali sulla macchina di sviluppo (PB 19, 22, 25):

```
Save Format v3.0(19990112)        <- magic header costante (format-version del file, non versione PB)
@begin Projects                    <- blocco opzionale (lista progetti embedded nel .pbt)
 0 "1&p_main&main.pbl";
@end;
appname "myapp";
applib "myapp.pbl";
LibList "myapp.pbl;..\\dep\\rstpb_core.pbl;..\\dep\\pbunit.pbd";
type "pb";                          <- pb | component | asm | ...
```

`.pbw` (workspace):

```
Save Format v3.0(19990112)
@begin Targets
 0 "src\\main.pbt";
 1 "src\\tools.pbt";
@end;
DefaultTarget "src\\main.pbt";
DefaultExportEncode "UTF-8";        <- opzionale
DefaultRemoteTarget "src\\main.pbt";
```

Note:
- Magic header `Save Format v3.0(19990112)` è **costante** (data di freeze del formato Sybase, 1999-01-12). **Non identifica la versione PB**.
- Keyword sono case-insensitive (`LibList` ↔ `liblist` osservati nello stesso codebase).
- Stringhe usano escape stile C-string per i backslash dei path (`..\\dep\\rstpb_core.pbl`).
- `LibList` separa con `;`.
- I file PB di progetto/workspace **non contengono la versione PowerBuilder** (verificato su `.pbt` PB 19, 22, 25 e `.pbw` di workspace mw24/mw25). La selezione della DLL ORCA è quindi sempre esplicita lato chiamante.

Tool `pb_target_info`:

```json
// input: {"path": "C:\\projects\\foo\\foo.pbt"}
// output (caso .pbt):
{
  "kind": "pbt",
  "target_name": "foo",        // dal nome file
  "app_name": "foo",           // da `appname`
  "app_lib": "foo.pbl",        // da `applib`
  "lib_list": ["foo.pbl", "..\\dep\\bar.pbl"],
  "type": "pb"                  // da `type`
}

// output (caso .pbw):
{
  "kind": "pbw",
  "workspace_name": "myworkspace",
  "targets": ["src\\main.pbt", "src\\tools.pbt"],
  "default_target": "src\\main.pbt"
}
```

Non c'è inferenza versione: `pb_session_open` riceve `install_path` o `pb_version` direttamente dal chiamante (vedi §"Decisioni di scope").

### Configurazione

Lookup in ordine (primo hit vince):
1. Argomenti CLI (`--pb-install`, `--arch`, ecc.).
2. Env vars (`PB_INSTALL_PATH`, `PB_ORCA_MCP_ARCH`).
3. File `pb-orca-mcp.toml` nel cwd o `~/.config/pb-orca-mcp/config.toml`.
4. Auto-discovery.

### Integrazione Claude Code

Snippet documentato in `docs/claude-code-setup.md`:

```json
// .claude/mcp.json (project-level) oppure ~/.claude/mcp.json (user-level)
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": ["pb-orca-mcp"],
      "env": {
        "PB_INSTALL_PATH": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0"
      }
    }
  }
}
```

## Roadmap (7 fasi, post-Ultraplan)

| Fase | Contenuto | Stima |
|---|---|---|
| **1 — Foundation** | Repo skeleton, `pyproject.toml`, server MCP entry point vuoto, fixture `tests/fixtures/tiny_app/`, CI Windows. | 1-2 gg |
| **2 — Discovery & loader multi-version** | `discovery.py` (registry+filesystem, IDE vs runtime, ricostruzione install dir da `Location`+`IPS Name`), `_pe.py` (PE Machine field via `struct`), `pb_target_info` parser `.pbt`/`.pbw` (no inferenza versione), `orca/dll.py` factory `load_orca(install)`, tool `pb_discover_pb_install`. Test reali contro PB 19.0, 22.0, 25.0. | 2-3 gg |
| **3 — Session & application** | `PBORCA_SessionOpen/Close`, `SessionSetCurrentAppl`, `SessionSetLibraryList`. Singleton `Session` con tracking version+arch. | 1-2 gg |
| **4 — Library ops** | Tool MCP per Create/Delete/Directory/EntryInfo/Export/Delete/Move/Comment + struct ctypes (`PBORCA_DIRENTRY` ecc.). | 2-3 gg |
| **5 — Compile loop (core value)** | Callback infrastructure (CFUNCTYPE), buffer errori, `CompileEntryImport(List)`, `ApplicationRebuild`, `pb_get_last_compile_errors`. | 3-4 gg |
| **6 — Build artifacts & object query** | `ExecutableCreate`, `DynamicLibraryCreate` (PBR/icon/machine-code), `ObjectQueryHierarchy/Reference/Regenerate`. | 2-3 gg |
| **7 — Packaging + docs** | Release PyPI, README, `docs/tools.md`, `docs/recipes.md`, snippet `.claude/mcp.json`, `CLAUDE.md` locale al progetto. | 1-2 gg |

Totale: ~14-20 giorni-uomo per la v1 completa.

## File critici da creare

Tutti i path relativi alla root del repository:

- **`pyproject.toml`** — metadata, dipendenze (`mcp>=1.0`, `pydantic`, `click`), entry point `pb-orca-mcp = pb_orca_mcp.__main__:cli`.
- **`src/pb_orca_mcp/orca/dll.py`** — `CDLL` load, tutte le `argtypes`/`restype` delle 30+ funzioni ORCA. Il file più "denso" ma meccanico.
- **`src/pb_orca_mcp/orca/types.py`** — `ctypes.Structure` per `PBORCA_DIRENTRY`, `PBORCA_COMPERR`, `PBORCA_HIER_DIRENTRY`, `PBORCA_REF_DIRENTRY`, ecc. Esatti dall'header `PBORCA.H` (in `<PB_install>/SDK/Include/`).
- **`src/pb_orca_mcp/orca/session.py`** — singleton `Session` con `_callback_refs` per tenere vive le callback durante chiamate ORCA.
- **`src/pb_orca_mcp/orca/callbacks.py`** — fabbrica di callback Python con buffer di errori thread-local-ish (in realtà single-thread).
- **`src/pb_orca_mcp/server.py`** — registrazione di tutti i tool MCP con `@server.tool()` dell'SDK.
- **`src/pb_orca_mcp/tools/*.py`** — un file per gruppo funzionale, ognuno espone tool MCP che wrappano chiamate `Session.*`.
- **`tests/fixtures/tiny_app/`** — un mini-workspace PB con un `.pbt`, 2 PBL, 3-4 oggetti (Application, una function, una window). Usato per test E2E reali contro `pborc.dll` (non mockato).
- **`README.md`** — install, config, `.claude/mcp.json` snippet, troubleshooting registry.
- **`CLAUDE.md`** (locale al progetto) — istruzioni per future sessioni di Claude su questo specifico repo (linguaggio Python, no PB code style, test contro DLL reale, ecc.).

## Considerazioni critiche

- **Lockfile `.pbl`**: se l'IDE PB è aperto sulla stessa PBL, le operazioni di scrittura falliscono. Il server deve restituire un errore comprensibile ("PBL locked by another process — chiudi l'IDE o lavora su una copia") invece del codice grezzo `PBORCA_*ERR`.
- **Thread-safety**: ORCA **non è** thread-safe e single-session. Il server MCP è single-threaded per default; se l'SDK MCP esegue tool call in parallelo, mettere `asyncio.Lock` attorno a ogni chiamata ORCA.
- **Callback lifetime**: errore classico ctypes — se la `CFUNCTYPE` Python viene garbage-collected mentre la C la sta chiamando, crash. Tutti i callback registrati vivono in `Session._callback_refs` finché la sessione è aperta.
- **x86 vs x64**: Python deve girare nella stessa arch della `pborc.dll`. Storicamente l'IDE PB è x86 (vedi cartelle `Program Files (x86)\Appeon\PowerBuilder *.0\`); alcune release recenti hanno anche build x64. Per una `pborc.dll` x86 serve Python x86, per una x64 serve Python x64. `uvx` rispetta l'arch dell'interprete usato.
- **Path Windows**: ORCA vuole path Windows native con `\`. I tool MCP accettano sia `\` sia `/` in input e normalizzano internamente.
- **EXE building con PBR**: `PBORCA_ExecutableCreate` accetta lista di risorse `.pbr`. Per uso agentico tipico (validazione build, non release), si può chiamare senza PBR; per uso "build runner" servono tutti i parametri (icon, ServerFlags, machine-code switch).
- **Multi-version dal day-1**: il loader in `orca/dll.py` carica la `pborc.dll` dell'installazione PB scelta (`load_orca(install)` dove `install` viene da discovery). `KNOWN_VERSIONS = ("19.0", "22.0", "25.0")` sono solo le testate; release future (es. PB 2026) o intermedie (es. PB 2021, 2022 R1/R2) vengono trovate automaticamente dal discovery se installano `pborc.dll` nello schema standard. ABI ORCA stabile da PB 2019.
- **IDE vs runtime**: il discovery filtra le installazioni runtime-only (senza `pborc.dll`) e le segnala separatamente. Errore comprensibile se l'utente punta a una runtime install.
- **Non sostituisce PowerGen / build di rilascio**: il server MCP è strumento di sviluppo interattivo. Le pipeline batch esistenti (PowerGen, OrcaScript, script custom) restano come oggi nei workspace che le usano. Documentato esplicitamente in `docs/recipes.md`.

## Verifica end-to-end

1. **Install**: `uv tool install pb-orca-mcp` su una Windows con almeno una PB IDE installazione. Comando `pb-orca-mcp doctor` deve passare (rileva DLL, conferma arch, lista tutte le install trovate).
2. **Integrazione Claude Code**: aggiungere snippet a `~/.claude/mcp.json`, riavviare Claude Code, verificare che i ~23 tool `pb_*` siano elencati in `/mcp`.
3. **Session smoke test**: prompt "apri sessione ORCA". Tool `pb_session_open` ritorna success con `pb_version: "22.0"` e `dll_path` valido.
4. **Library inspection** (fixture): `pb_library_directory` su `tests/fixtures/tiny_app/main.pbl` → lista coerente con quello che PB IDE mostra (oggetti, tipi, comment).
5. **Compile-test loop** (fixture): export di una function, modifica intenzionale rotta, `pb_compile_entry_import` → errori riportati con line/column corretti. Correggi, re-import → success.
6. **Application rebuild** (fixture): `pb_set_current_application` + `pb_application_rebuild` con `rebuild_type=full` → 3-pass build, zero errori.
7. **Build EXE** (fixture): `pb_executable_create` → produce `.exe` runnabile (avviare sì/no è opzionale, basta esistenza e che PB IDE riesca a importarlo).
8. **Object query** (fixture): hierarchy su una user object ereditata da `nonvisualobject` → catena corretta.
9. **Test contro workspace reale** (opt-in): puntare il server su una PBL di un applicativo PB esistente (a IDE chiuso), `pb_library_directory` deve listare gli oggetti coerenti con i sorgenti estratti in `ws_objects/src/<pbl>.pbl.src/`.
10. **Stress lock**: aprire IDE PB sulla stessa PBL durante una `CompileEntryImport` → errore comprensibile, non crash.

## Out of scope (esplicitamente)

- Source Control Connector (SCC) — niente `PBORCA_Scc*` (chi usa PB con SCC è una minoranza, git è lo standard).
- Sostituzione di workflow batch tipo PowerGen / OrcaScript / script custom — il server è strumento di sviluppo interattivo, non build runner di rilascio.
- Integrazione con `.gen` file PowerGen — il server lavora su `.pbt`/`.pbl` direttamente.
- UI / dashboard — è puro MCP server stdio.
- Macro/script PB IDE — fuori scope di ORCA stessa.
- PB Classic (versioni precedenti a PB 2019) — il discovery non le filtra (qualsiasi installazione con `pborc.dll` è candidata), ma le release pre-2019 possono avere ABI ORCA divergente. Supportate best-effort; nessun test contro queste versioni.

## Decisioni residue (da risolvere durante/dopo lo scaffolding)

| Decisione | Quando va presa | Opzioni emerse |
|---|---|---|
| **Licenza** | Prima di publish PyPI | MIT (raccomandata per package general-purpose) / Apache 2.0 / proprietaria |
| **Disponibilità nome `pb-orca-mcp` su PyPI** | Prima di pubblicare la v0.1 | Check `pip index versions pb-orca-mcp` + reserve squat. Alternative se occupato: `powerbuilder-orca-mcp`, `pb-orca` |

Decisioni risolte:
- ✅ **Git remote**: `https://github.com/restoresrl/pb-orca-mcp` (private GitHub org Restore srl), pushed 2026-05-12.
