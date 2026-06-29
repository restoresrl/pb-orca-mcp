# Security Policy

## Scope

`pb-orca-mcp` runs locally on a developer machine and drives a local
PowerBuilder install through `pborc.dll`. It opens no network sockets and
ships no server component. The most relevant risks are therefore:

- A malicious `.pbt` / `.pbw` / `.pb-format.toml` or source file causing
  unexpected file writes outside the intended workspace.
- Path handling that escapes the directory the caller intended.

## Reporting a vulnerability

Please report security issues privately to **carlo.torrese@re-store.it**
rather than opening a public issue. Include a description, affected
version, and a reproduction if possible. You'll get an acknowledgement,
and a fix or mitigation plan once the report is confirmed.

## Supported versions

This project is pre-1.0; only the latest released version receives
security fixes.
