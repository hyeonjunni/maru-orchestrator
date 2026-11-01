# MARU release readiness

Review date: 2026-11-01 (Asia/Seoul).

**READY_WITH_LIMITATIONS** is the recommendation for this curated release candidate,
conditional on the final candidate checks recorded in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).
It is not publication approval. Ownership confirmation, license selection and the owner's
explicit approval to publish remain required.

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
unchanged. Public commit preparation uses a clearly labeled synthetic author identity, which
the owner should replace with their chosen public identity for future contributions.

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
| Ownership and project license | Pending owner confirmation. No project license has been selected or applied. |
| Live provider validation | No new paid model call is part of this preparation. Recorded fixtures and offline tests do not prove current provider authentication or availability. |

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

Authorship metadata and successful scans cannot establish rights to every source, prompt,
fixture or model output. The owner must confirm that the selected files may be published and
identify any required third-party notices. MIT is a possible permissive project license,
not a license granted by this review.

Previously inspected direct runtime dependency metadata declares MIT for platformdirs,
pydantic, rich and typer. Development/transitive dependencies include other licenses; these
metadata observations are not a complete compatibility review. Preserve upstream notices
where distribution requires them. No dependency source is vendored by this candidate.

Before publication:

1. Complete and record exact-candidate tests, package smoke and secret scans; retain any skips
   and platform limitations in the verification report.
2. Confirm publication rights, select a project license and review the public commit identity.
3. Obtain explicit owner approval before creating/uploading a public repository or changing
   repository visibility. Do not migrate prior hosted artifacts implicitly.

Secret-pattern detection does not prove the absence of every secret or private business fact.
The release recommendation is limited to the reviewed candidate and the stated evidence.
