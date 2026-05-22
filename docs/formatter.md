# PowerScript body formatter

`pb-orca-mcp` ships a small token-based formatter that normalizes the
PowerScript body of an entry before it is written to disk. The goal is
narrow on purpose: enforce a few low-controversy invariants so files
written by an agent (or a tool, or a teammate using a different editor)
look the same as files written by PB IDE.

The formatter is **off by default in opt-in mode**. A workspace activates
it by committing a `.pb-format.toml` file. Without that file,
`pb_edit_and_import` writes exactly what it has always written — no
breaking change.

## What it does

Four invariants, applied in order on the source body (never on the
`$PBExportHeader$` / `$PBExportComments$` lines, which the tool rebuilds
itself):

1. **Indent** — leading whitespace on each line is converted between TAB
   and `N`-space forms. This is a 1:1 substitution, not a re-indent: the
   formatter does not infer logical nesting from the AST. Sub-unit
   residue (e.g. two stray spaces under `tab_width = 4`) is preserved
   verbatim.
2. **Line endings** — every newline in the output becomes CRLF, the
   format PB IDE writes on export. Applies inside block comments too.
3. **Keyword case** — reserved words (`if`, `then`, `string`,
   `subroutine`, …) are folded to lowercase by default; configurable to
   uppercase or preserve. Words right after `.` or `::` are left
   untouched because they may be user-defined members or scope
   references that happen to share a keyword's spelling.
4. **Operator spacing** — binary operators (`=`, `+`, `-`, `*`, `/`,
   `^`, `<`, `>`, `<=`, `>=`, `<>`, and the compound assignments) get
   exactly one space on each side. Unary `+`/`-` (detected from the
   previous significant token's expression-start position) are not
   padded. `&` (line continuation) and `,` / `;` (separators) are not
   touched.

### What it does **not** do

- No blank-line policy between methods or events.
- No alignment of continuation `&` lines.
- No identifier rewriting (hungarian prefixes, casing of locals): that
  would require an AST and a symbol table, and tracking call sites.
- No DataWindow source (`.srd`) work — DataWindows use a different
  mini-DSL and are skipped outright.
- No re-indentation. A line that came in at column 0 stays at column 0
  even if it "should" be inside a block; that decision needs a parser.

If you need any of the above, the formatter is the wrong tool — file an
issue describing the use case, or run a separate linter.

### Idempotency contract

`format(format(source)) == format(source)` for every input and every
configuration. This is enforced by ~60 parametrized tests
(`tests/format/test_idempotency.py`). Idempotency is what makes the
formatter safe to wire into a write-on-every-call API like
`pb_edit_and_import`: re-saving a file the formatter already touched
produces a no-op diff, so PB IDE's next *Refresh* on the entry stays
quiet rather than triggering an import + compile + regenerate cascade.

## Quick start

1. Drop a `.pb-format.toml` next to your `.pbw`:

   ```toml
   [style]
   indent = "tab"
   keyword_case = "lower"
   spaces_around_operators = true
   line_endings = "crlf"
   ```

2. Call `pb_edit_and_import` exactly as before. The default
   `format = "auto"` walks up from `source_path` looking for that file
   and, when found, normalizes the body before writing.

3. The response now carries `formatted: bool`. If `formatted` is
   `true`, the body went through the normalizer; if `false`, either
   `format` was disabled or no config was found.

Before:

```powerscript
IF a<=b THEN
    return  a+1
END IF
```

After (with the config above):

```powerscript
if a <= b then
	return a + 1
end if
```

## Config reference: `.pb-format.toml`

The file lives at the workspace root — same directory as the `.pbw`, or
any ancestor. Discovery walks upward from the source path until it
finds one or hits the filesystem root.

```toml
[style]
indent = "tab"
keyword_case = "lower"
line_endings = "crlf"
spaces_around_operators = true
tab_width = 4
```

| Key | Accepted values | Default | Effect |
| --- | --- | --- | --- |
| `indent` | `"tab"`, `"spaces:N"` (1 ≤ N ≤ 16) | `"tab"` | Output indent unit. `"spaces:N"` writes N spaces per logical level; `"tab"` writes one TAB per level. |
| `keyword_case` | `"lower"`, `"upper"`, `"preserve"` | `"lower"` | How reserved words are cased. `preserve` disables case folding entirely. |
| `line_endings` | `"crlf"`, `"lf"` | `"crlf"` | Newline style applied to the whole body, including comment interiors. Keep `"crlf"` unless you specifically want non-IDE behaviour. |
| `spaces_around_operators` | `true`, `false` | `true` | Whether binary operators get padded with single spaces. Unary `+`/`-` are never padded. |
| `tab_width` | positive integer | `4` | Only used when converting *from* spaces *to* TAB output. A run of `tab_width` spaces collapses to one TAB; sub-unit residue is kept as spaces. |

Unknown keys under `[style]` are ignored — older versions of the
formatter won't break on a config written for a newer version.

An empty file is valid; you get the defaults. The `[style]` section is
optional for the same reason.

## When the formatter runs

`pb_edit_and_import` accepts a `format` parameter with three modes:

```text
format = "auto"   (default)  → format if .pb-format.toml is discovered
format = True                → always format; use discovered config or defaults
format = False               → never format
```

Independently of `format`, the formatter is **always skipped** for:

- DataWindow entries (`entry_type = "datawindow"`, extension `.srd`).
- Entry types without a canonical `.sr*` extension (`project`,
  `proxyobject`, `binary`).

Everything else — applications, user objects, windows, functions,
structures, menus, queries, projects with PowerScript content — runs
through the formatter when the mode allows.

A malformed `.pb-format.toml` (bad TOML, unknown enum value, `indent`
outside `1..16`) surfaces as `PB_ORCA_MCP_INVALIDARGS` from the tool.
The body is **not** written in that case; the caller sees the error
before any disk side-effect.

## String and comment safety

Reserved words inside string literals or comments are never touched.
The lexer treats every string and comment as a single opaque token, so
case-folding and operator-spacing rules cannot bleed in. Examples:

```powerscript
ls_msg = "IF this THEN that"   // keywords inside strings stay capitalized
// FOR review by ops            ← comment keywords also untouched
/* block comments
   with IF, THEN, ELSE          ← still untouched
   span multiple lines */
```

The tilde escape (`~`) is recognized as the PowerScript escape
character (not backslash). Doubled quotes inside a same-kind string
(`"abc""def"`) are also recognized as a literal-quote escape.

## Programmatic API

The same engine is callable from Python without going through
`pb_edit_and_import`. Use it for ad-hoc reformatting of files on disk,
for tests, or as a building block in larger tooling.

```python
from pathlib import Path
from pb_orca_mcp.format import (
    FormatConfig,
    discover_config,
    format_powerscript,
)

# Load the workspace config, or fall back to defaults.
config_path = discover_config(Path("ws_objects/src/myapp.pbl.src/n_foo.sru"))
config = FormatConfig.from_path(config_path) if config_path else FormatConfig.default()

body = Path("n_foo.sru").read_text(encoding="utf-8")
formatted = format_powerscript(body, config)
```

`FormatConfig.from_path(path)` parses a `.pb-format.toml` and raises
`ValueError` on schema problems. `FormatConfig.default()` returns the
hard-coded defaults (tab indent, lowercase keywords, CRLF, spaces
around operators). Both are immutable dataclasses.

`discover_config(start)` accepts a file or directory path and walks
upward looking for `.pb-format.toml`, returning the first match or
`None`.

## Why a token-based engine?

A real PowerScript parser would let the formatter do a lot more —
proper re-indent, blank-line policy, alignment, identifier rewrites.
None of that exists as a stable open-source artifact today; the public
ANTLR / tree-sitter PowerScript grammars are either incomplete, dormant
for years, or under active design with a bus factor of one.

A token-based normalizer is what we *can* ship safely now:

- It needs no grammar, so it can never crash on syntax the grammar
  doesn't yet cover.
- It owns four invariants that genuinely don't need an AST.
- It is small enough (~700 lines including tests) to audit in an
  afternoon.

The cost is the explicit scope list above: blank-line and alignment
rules are deferred until the language has a maintained grammar this
project can build on. When that happens, a second layer (AST-aware) can
slot in behind the same `format_powerscript` entry point.
