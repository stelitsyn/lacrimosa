# Codex Backend Adapter

## Lesson

Lacrimosa can support more than one agent runtime only when backend-specific details are isolated behind a small dispatch adapter. Backend strings, CLI flags, runtime home paths, and auth assumptions should not be scattered across sensors, scoring, intake, learning, or worker dispatch modules.

## Apply

- Keep Claude as the default backend unless the operator selects another backend explicitly.
- Route all prompt execution through one runner interface.
- Treat long-running worker dispatch as a first-class async runner path, separate from synchronous prompt calls.
- Preserve specialist locks, heartbeat writes, throttle checks, and generated runtime paths when adding a backend.
- Install or generate backend-specific runtime files deterministically, then scan generated files for stale paths and direct backend calls.
- Distill runtime memory before publishing it; never copy live private memory into a public repository.

## Avoid

- Replacing backend names with broad string substitution without a validation pass.
- Letting individual modules shell directly to an agent CLI.
- Publishing product-specific project names, issue IDs, customer details, credential paths, cloud identifiers, or private local paths in memory notes.
- Pushing a public repository from an automation step without explicit operator approval.
