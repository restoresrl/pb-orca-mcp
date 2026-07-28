# ws_app fixture

A complete PowerBuilder workspace that keeps a **text projection**, i.e. the
`ws_objects/<lib>.pbl.src/` tree the IDE creates once a workspace is put under
source control. `tiny_app` next door is the opposite shape: a bare `.pbl` with
no workspace file and no projection. Between them they cover the two layouts
pb-orca has to handle, and `test_source_real.py` exercises the same flow
against both.

Contents:

- `ws_app.pbw` — the workspace file. Declares `DefaultExportEncode "UTF-8"`,
  which is what makes the exported `.sr*` files start with an `EF BB BF` BOM.
- `genapp.pbt` — the target: application `genapp` in `genapp.pbl`.
- `genapp.pbl` — a PB 22.0 wizard-generated library: the application object,
  the SDI main window, its menu, the about box, and a DataWindow added by hand
  so the `.srd` path is covered.
- `ws_objects/genapp.pbl.src/*.sr*` — the five objects as the PB IDE itself
  exported them. These are the reference bytes: a test that exports through
  ORCA and compares against them proves pb-orca produces exactly what the IDE
  produces, which is the property the whole `ws_objects` sync depends on.

`d_genapp_dw_test.srd` is plain text — no `Start of PowerBuilder Binary Data
Section` block. Replacing it with a DataWindow that embeds a picture or an OLE
object would extend the coverage to `bExportIncludeBinary`, the one export
option still unproven.

The binaries and the `.sr*` files are marked `binary` in `.gitattributes` so
git preserves the BOM and CRLF byte-for-byte. A test that mutates any of this
must copy the tree to `tmp_path` first.

## Recreating it

Build a wizard SDI application in PB IDE (see `../tiny_app/README.md`), then
in the IDE put the workspace under source control with a local git provider so
the IDE generates `ws_objects/`. Copy the workspace file, the target, the
library and the `ws_objects/` tree here, renaming the `.pbw` to `ws_app.pbw`.
