# Backend API Seam Audit

## Scope
- Shell: `apps/web/command_center.py`
- Runtime seam: `core/runtime/application_services.py`
- Storage implementation: `core/runtime/storage.py`
- Verified against: `tests/test_command_center.py`, `tests/test_review_desk.py`, `tests/test_skill_workshop.py`, `tests/test_scene_to_chapter_workbench.py`, `tests/test_end_to_end.py`

## Seam status summary
- `command center` GET surface is already service-backed through workspace snapshot, review proposal, derived artifact, and object read operations.
- `workbench` POST generation flows are already service-backed except `import_outline`, which is now routed through the public `SuperwriterApplicationService.import_outline(...)` seam.
- `create-novel` shell creation flow no longer reaches private storage directly; it now routes canonical project/novel creation through the public `SuperwriterApplicationService.create_workspace(...)` seam.
- `review desk` rendering is service-backed, but the shell still has no POST route for `transition_review(...)`; this remains a blocking extraction item.
- `skills` CRUD/import/rollback flows are service-backed.
- `publish` flow is service-backed.
- `settings` rendering reads provider state through service methods, but `/api/providers` is still a placeholder shell endpoint; provider mutations remain blocked for frontend reliance until that route is upgraded.

## UI surface to internal operation map

### Command center
- Route: `GET /`, `GET /command-center`
- Shell entry: `BookCommandCenter.render_route()` → `render_command_center()` / `build_snapshot()`
- Internal operations:
  - `SuperwriterApplicationService.get_workspace_snapshot(...)`
  - `SuperwriterApplicationService.list_derived_artifacts(...)`
  - `SuperwriterApplicationService.list_review_proposals(...)`
  - `SuperwriterApplicationService.read_object(...)`
- Notes:
  - snapshot composition is still shell-owned view shaping, not an API contract
  - domain invariants remain service/storage-owned

### Create novel
- Route: `POST /create-novel`
- Shell entry: `BookCommandCenterWSGIApp.__call__()` → `BookCommandCenter.submit_create_novel_form()`
- Internal operations:
  - `SuperwriterApplicationService.create_workspace(CreateWorkspaceRequest)`
- Remaining shell-owned side effects:
  - `_write_workspace_manifest(...)` writes `.superwriter/workspace.json`
- Notes:
  - canonical object creation now stays behind the service seam
  - workspace manifest writing remains an intentional local-first shell side effect and must be preserved explicitly during frontend migration

### Workbench
- Route: `GET /workbench`
- Shell entry: `BookCommandCenter.render_route()` → `_render_workbench_page()`
- Internal operations:
  - `SuperwriterApplicationService.get_workspace_snapshot(...)`
  - `SuperwriterApplicationService.list_derived_artifacts(...)`
  - `SuperwriterApplicationService.list_review_proposals(...)`

- Route: `POST /workbench`
- Shell entry: `BookCommandCenterWSGIApp.__call__()` → `BookCommandCenter.submit_workbench_form()`
- Internal operations by `link_type`:
  - `import_outline`
    - `SuperwriterApplicationService.import_outline(ImportOutlineRequest)`
  - `outline_to_plot`
    - `SuperwriterApplicationService.generate_outline_to_plot_workbench(...)`
  - `plot_to_event`
    - `SuperwriterApplicationService.generate_plot_to_event_workbench(...)`
  - `event_to_scene`
    - `SuperwriterApplicationService.generate_event_to_scene_workbench(...)`
- Blocking extraction items:
  - `scene_to_chapter` is rendered and visible, but the shell still does not submit a POST action for it in `submit_workbench_form()`; current surface coverage is incomplete for frontend migration

### Review desk
- Route: `GET /review-desk`
- Shell entry: `BookCommandCenter.render_route()` → `_render_review_desk_page()`
- Internal operations:
  - `SuperwriterApplicationService.get_review_desk(ReviewDeskRequest)`
- Blocking extraction items:
  - No shell POST route currently calls `SuperwriterApplicationService.transition_review(...)`
  - exact file/function reference: `apps/web/command_center.py`, `BookCommandCenterWSGIApp.__call__()` lacks a `/review-desk` POST branch

### Skills
- Route: `GET /skills`
- Shell entry: `BookCommandCenter.render_route()` → `_render_skill_workshop_page()`
- Internal operations:
  - `SuperwriterApplicationService.get_skill_workshop(SkillWorkshopRequest)`
- Route: `POST /skills`
- Shell entry: `BookCommandCenterWSGIApp.__call__()` → `BookCommandCenter.submit_skill_workshop_form()`
- Internal operations:
  - `SuperwriterApplicationService.upsert_skill_workshop_skill(...)`
  - `SuperwriterApplicationService.rollback_skill_workshop_skill(...)`
  - `SuperwriterApplicationService.import_skill_workshop_skill(...)`

### Publish
- Route: `GET /publish`
- Shell entry: `BookCommandCenter.render_route()` → `_render_publish_page()`
- Internal operations:
  - `SuperwriterApplicationService.list_derived_artifacts(...)`
- Route: `POST /publish`
- Shell entry: `BookCommandCenterWSGIApp.__call__()` → `BookCommandCenter.submit_publish_form()`
- Internal operations:
  - `SuperwriterApplicationService.publish_export(PublishExportRequest)`

### Settings / providers
- Route: `GET /settings`
- Shell entry: `BookCommandCenter.render_route()` → `_render_settings_page()`
- Internal operations:
  - `SuperwriterApplicationService.list_provider_configs()`
- Route: `GET /api/providers`
- Shell entry: `BookCommandCenter.render_route()` → `_handle_providers_api()`
- Current status:
  - placeholder only; no real internal API contract is returned
- Blocking extraction items:
  - provider form actions (`save`, `save_and_activate`, `activate`, `test`, `delete`) post to `/api/providers`, but `_handle_providers_api()` does not parse or dispatch them
  - exact file/function reference: `apps/web/command_center.py`, `BookCommandCenter._handle_providers_api()`
  - service methods exist and are callable, but the shell route contract is not locked yet:
    - `list_provider_configs()`
    - `save_provider_config(...)`
    - `set_active_provider(...)`
    - `delete_provider_config(...)`
    - `test_provider_config(...)`

## Remaining shell/storage bypass inventory
- Removed in this task:
  - `apps/web/command_center.py::submit_create_novel_form()` private access to `self._service._SuperwriterApplicationService__storage.write_canonical_object(...)`
  - `apps/web/command_center.py::submit_workbench_form()` private access for `import_outline`
- Still intentionally shell-owned:
  - `apps/web/command_center.py::_write_workspace_manifest()` local filesystem manifest write
- No additional direct canonical-storage bypasses were found in the audited route handlers for command center, workbench, review desk, skills, publish, settings, or create-novel

## Blocking extraction items before frontend reliance
1. `apps/web/command_center.py::BookCommandCenterWSGIApp.__call__()` needs a `/review-desk` POST branch that routes to `SuperwriterApplicationService.transition_review(...)`.
2. `apps/web/command_center.py::BookCommandCenter._handle_providers_api()` must become a real provider contract instead of a placeholder response.
3. `apps/web/command_center.py::BookCommandCenter.submit_workbench_form()` does not expose `scene_to_chapter` POST semantics even though the page documents that flow.
4. Command center snapshot composition (`build_snapshot`) is still HTML-shell-owned aggregation; frontend migration should not treat its current rendered structure as the API contract.
5. Workspace manifest creation remains a server-owned local-first side effect and must stay explicit in any future API response design.

## Invariants preserved by this seam audit
- Canonical objects remain authoritative.
- Derived artifacts remain rebuildable and non-authoritative.
- Mutation/review ledger semantics remain service/storage-owned.
- Revision pinning, drift detection, and review replay idempotency remain unchanged.
- Local-first behavior is preserved: canonical persistence is backend-owned and workspace manifest creation remains an explicit local filesystem side effect.
