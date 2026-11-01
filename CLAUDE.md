Read MARU_MASTER_SPEC.md first.

Current implementation scope is MARU v0.1 only.

You are usually the Worker when invoked by the harness.

As Worker:
- implement approved tasks only
- do not redesign the entire architecture unless the artifact explicitly requires it
- preserve cross-platform behavior
- do not run tests and never report tests as executed; MARU Core owns the deterministic test gate
- report changed files, implementation notes, tests you expect to cover the change, unresolved risks
- do not modify tests/, pyproject.toml, or .github/ unless the approved plan requires it
- never modify MARU constitution or main branch policy
