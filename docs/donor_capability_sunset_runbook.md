# Donor capability sunset runbook

## Goal

Retire implementation-base donor behavior only after Superwriter has replacement evidence for every publish/export responsibility that still references donor-era assumptions.

## Replacement evidence required

- Imports run through `SuperwriterApplicationService.import_from_donor()` and record `import_source` in `import_records` for every project that will be published.
- Publish/export runs through shared application services, creates an `export_artifact`, and writes only explicit filesystem projections from that derived payload.
- End-to-end verification covers: donor import, command-center diagnosis, scene auto-apply, chapter prose auto-apply, non-scene review-required change, approval, skill edit, and publish/export.
- Recovery paths are explicit for stale lineage, importer mismatch, and interrupted/partial projection failures, with canonical state left unchanged.

## Sunset criteria

Mark donor capability as sunset-ready only when all of the following are true:

1. New publishing depends only on canonical objects, derived chapter/export artifacts, and shared application services.
2. No filesystem artifact is read back as truth for scenes, chapters, skills, or review decisions.
3. Import provenance is still available from `import_records`, but publish no longer needs any donor runtime coupling beyond matching the recorded import source.
4. The required verification commands pass on current code:
   - `python -m pytest tests/test_end_to_end.py -q`
   - `npm --prefix apps/web test -- --runInBand`
5. A failed publish can be retried from the stored `export_artifact` without re-importing donor state or mutating canonical truth.

## Deprecation checklist

- Keep `webnovel-writer` as the implementation-base donor for import validation only.
- Reject any proposal to restore donor storage/runtime coupling, dual-writing, or filesystem-as-truth behavior.
- Remove donor-specific publish assumptions only after the replacement evidence above stays green in CI and local verification.

## Non-goals

- This runbook does not authorize editor-plugin behavior, marketplace behavior, unrestricted skill execution, or retrieval-as-truth workflows.
