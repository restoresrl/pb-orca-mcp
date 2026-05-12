# Recipes

> **Status**: phase 1 scaffolding — recipes arrive in phase 7.

End-to-end agentic workflows that combine multiple `pb_*` tools.

## Planned recipes

- **Compile-test loop** — export entry, modify source, re-import + compile, surface errors to the agent.
- **Cross-PBL rebuild** — set target, run `pb_application_rebuild`, read compile errors.
- **Build a PBD from a PBL** — for snapshot-style dependency distribution (vendoring compiled `.pbd` artifacts into consumers).
- **Hierarchy walk** — given a user object, find every ancestor up to `nonvisualobject` / `window`.
- **Reference audit** — given a function, list every object that calls it.

## Anti-recipe: do NOT replace your build pipeline

If you already have a working batch build (PowerGen, OrcaScript, or custom),
keep it. `pb-orca-mcp` is an interactive development tool for agents, not a
release build runner. Use it for the inner loop, not for tagged releases.
