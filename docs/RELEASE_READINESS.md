# MARU release readiness

Review date: 2026-11-01; live follow-up documented 2026-11-02 (Asia/Seoul).

Final 2026-11-02 update: separate Codex static source audit completed; nine reviewer findings
and two current-session approval/packaging findings were addressed. The owner explicitly
approved the retained Live E2E gate, which reached MERGED with prior evidence preserved.
The original task's PENDING_INDEPENDENT_AUDIT event remains historical evidence; it was not
rewritten as a cross-provider task review. Final test/follow-up counts and remaining limits
are recorded at the top of [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

**READY_FOR_PUBLICATION_APPROVAL** follows the final checks recorded in
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md). The owner confirmed publication rights,
selected MIT, and approved `Copyright (c) 2026 hyeonjunni`. The remaining action is explicit
permission to push the reviewed candidate; hosted CI will run after publication.

## Release boundary

This candidate is an allowlisted snapshot of prior private development, prepared with new Git
history. Only reviewed source, packaged prompts and schemas, tests, configuration examples,
CI and public documentation belong in the release. Private history, runtime databases,
execution logs, recovery records and hosted assets are not migrated. The original development
repository remains separate and unchanged by the export.

The exact release allowlist is [PUBLIC_FILES.txt](../PUBLIC_FILES.txt). Original execution
data, environment directories, local credentials/settings, private handoffs, bootstrap/session
reports, old Git objects and local build output are excluded. Project-specific scenario names
and actor labels in test fixtures were generalized; parser behavior and runtime source remain
preserved except for the documented audit corrections. The original three public-preparation
commits retain their synthetic author identity. New commits use the owner-confirmed
`hyeonjunni <bobo050716@gmail.com>`; this email is intended to be public.

A new curated repository is preferred over changing the original repository's visibility:
it makes the public file boundary explicit and avoids carrying unreviewed historical or hosted
material into the release. The tradeoff is that the first public commit does not show the full
development history, and future synchronization must be deliberate. Do not copy an existing
Git directory or mirror all refs into the public repository.

## Evidence and limits

| Check | Evidence / status |
| --- | --- |
| Prior source/history audit | Reused evidence: Gitleaks 8.30.1 found no secrets in the inspected prior history, reachable blobs and source snapshot. This supports preparation but does not replace scanning this candidate. |
| Candidate privacy review | Paths, account identifiers, email addresses, internal URLs and runtime material were reviewed. Test email addresses and retained session IDs are synthetic fixtures. No private machine path or account identifier was found in the reviewed public files. |
| Final candidate and new history scan | Final execution and results belong in the verification report. This review does not claim a scan that has not run. |
| Submodules / LFS | No submodule configuration, gitlinks or LFS pointers were found in the inspected candidate. |
| Hosted CI | Not verified. The cross-platform workflow is included; remote execution and macOS/Linux results are not inferred from local tests. |
| Hosted assets | Not migrated or relied on as release evidence. Earlier hosted logs/artifacts/releases were unavailable for review. |
| Ownership and project license | Owner confirmed publication rights on 2026-11-02; MIT and Copyright (c) 2026 hyeonjunni are applied in LICENSE and package metadata. |
| Live provider validation | Claude direct smoke and four-role calculator fix passed; the owner later approved the real gate and it reached MERGED. Same-provider task evidence remains PENDING_INDEPENDENT_AUDIT. Separate Codex static code review is complete; MARU-to-Codex live adapter execution is not claimed. |

The scanner came from the [official Gitleaks v8.30.1 release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1),
and its Windows x64 archive matched the published SHA256:

```text
d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e
```

Scanner provenance and unchanged earlier history evidence are reused rather than repeatedly
revalidated. Final scans should use default rules and full redaction, without adding broad
allowlists to suppress findings. For an explicit candidate directory and its newly committed
history, the relevant commands are:

```text
gitleaks dir <candidate-directory> --redact=100
gitleaks git <candidate-directory> --log-opts=--all --redact=100
```

Run the directory scan against the intended release files, excluding build environments and
private runtime data. Record the exact candidate commit and scan results in the verification
report. Review any finding by file and category without publishing secret values.

## Rights and remaining approval

### Final license review (2026-11-02)

**Selected: MIT**, explicitly approved by the owner on 2026-11-02. The owner confirmed
publication rights and the copyright holder/year. See [LICENSE](../LICENSE); package metadata
uses the SPDX expression `MIT` and includes the license text.

| Choice | Practical terms | Fit for MARU |
|---|---|---|
| [MIT](https://opensource.org/license/mit) | Broad reuse; preserve copyright and permission notice; warranty disclaimer. No express patent grant in the text. | Short, straightforward terms for a small CLI and portfolio repository; recommended here. |
| [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | Express contributor patent grant and patent-termination terms; preserve required notices and identify modified files; handle NOTICE where supplied. | Useful if explicit patent terms and larger corporate contribution workflows become a priority; more notice administration. |

The tracked candidate contains no vendored dependency source, submodules or binary bundles.
No copied-code attribution markers were found in the inspected runtime/scripts/tests; that
does not establish authorship. The owner has confirmed rights to publish the selected code,
prompts, fixtures and model-generated material. That confirmation is recorded as an owner
statement, distinct from an independently reconstructed provenance history.

Installed locked-environment metadata was inspected for all 26 third-party distributions:

| Declared license | Packages (locked environment) |
|---|---|
| MIT | annotated-doc, annotated-types, ast_serialize, iniconfig, librt, markdown-it-py, mdurl, mypy, mypy_extensions, platformdirs, pluggy, pydantic, pydantic_core, pytest, pytest-cov, rich, ruff, typer, typing-inspection |
| BSD / BSD-2-Clause | colorama, Pygments |
| Apache-2.0 | coverage |
| Apache-2.0 OR BSD-2-Clause | packaging |
| MPL-2.0 | pathspec (development dependency; not vendored into MARU) |
| ISC | shellingham |
| PSF-2.0 | typing_extensions |

The clean wheel install resolved newer platformdirs/pydantic/pydantic-core/typer versions
than uv.lock; their installed metadata also declares MIT. Both environments were distinguished
in validation. This is a dependency metadata and packaging review, not proof of every
upstream file's provenance or a legal clearance. The wheel does not bundle these dependencies;
preserve upstream licenses/notices if distributing them separately or in a combined package.
Build-system tooling is not shipped as MARU runtime code. No additional package dependency was added.

### Historical export scans

The exact 89-file allowlist export passed Gitleaks 8.30.1 with **zero findings**
(602,917 bytes scanned). The new initial commit `66dc41e` was then scanned with
`gitleaks git . --log-opts=--all --redact=100`: **one commit, zero findings**.
No submodules, LFS pointers, private directory names or personal machine paths were found in
the selected files. Subsequent evidence-only commits are scanned before handoff; they do not
change the tested runtime or demo. Scanner provenance and old private-history evidence were
reused without rerunning those historical scans.

The historical preparation author is `MARU Release Preparation` with a reserved example-domain
address. The current `origin` is `https://github.com/hyeonjunni/maru-orchestrator.git`. GitHub
metadata and `git ls-remote` confirmed an empty public repository with default branch `main`.
The local publication branch is also `main`. Only the curated root commit `66dc41e` and its
public-candidate descendants belong to this history; the private Git directory was not imported.

The owner confirmed rights for this candidate and selected MIT. Third-party dependencies
retain their own licenses and notices; the project license does not replace those terms.

Previously inspected direct runtime dependency metadata declares MIT for platformdirs,
pydantic, rich and typer. Development/transitive dependencies include other licenses; these
metadata observations are not a complete compatibility review. Preserve upstream notices
where distribution requires them. No dependency source is vendored by this candidate.

Before publication:

1. Complete and record exact-candidate tests, package smoke and secret scans; retain any skips
   and platform limitations in the verification report.
2. Rights, MIT selection, copyright holder/year and new commit identity: confirmed by owner.
3. Obtain explicit owner approval before pushing `main` to the supplied repository. No force
   push, visibility change, hosted-artifact migration or GitHub Release publication is authorized.
   The connected GitHub tool currently reports read-only permission; Git CLI push authentication
   has not been tested. Resolve any authentication requirement when publication is authorized.

Secret-pattern detection does not prove the absence of every secret or private business fact.
The release recommendation is limited to the reviewed candidate and the stated evidence.
