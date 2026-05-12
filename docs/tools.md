# MCP tool reference

> **Status**: phase 1 scaffolding — tool list is documented in the plan, schemas
> arrive incrementally with the implementation phases.

Full reference of the ~23 MCP tools exposed by `pb-orca-mcp`. Each tool maps
1:1 (or close to it) to a `PBORCA_*` function in the PowerBuilder ORCA API,
with the exception of `pb_discover_pb_install`, `pb_target_info` and
`pb_get_last_compile_errors`, which are higher-level helpers.

## Tool groups

| Group | Tools | Roadmap phase |
|---|---|---|
| **Discovery** | `pb_discover_pb_install`, `pb_target_info` | 2 |
| **Session** | `pb_session_open`, `pb_session_close`, `pb_set_current_application`, `pb_set_library_list` | 3 |
| **Library** | `pb_library_create`, `pb_library_delete`, `pb_library_directory`, `pb_library_entry_information`, `pb_library_entry_export`, `pb_library_entry_delete`, `pb_library_entry_move`, `pb_library_comment_modify`, `pb_library_entry_comment_modify` | 4 |
| **Compile / rebuild** | `pb_compile_entry_import`, `pb_compile_entry_import_list`, `pb_application_rebuild`, `pb_get_last_compile_errors` | 5 |
| **Build artifacts** | `pb_executable_create`, `pb_dynamic_library_create` | 6 |
| **Object query** | `pb_object_query_hierarchy`, `pb_object_query_reference`, `pb_object_regenerate` | 6 |

(TODO: per-tool input/output schemas as each phase lands.)
