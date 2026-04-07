# Frontend runtime modes

`superwriter_local_server.py` now accepts `SUPERWRITER_FRONTEND_MODE=legacy|hybrid|spa`.

## Modes

- `legacy` (default): Python serves the current HTML shell for `/`, `/command-center`, `/workbench`, `/review-desk`, `/skills`, `/publish`, and `/settings`.
- `hybrid`: Python keeps the legacy shell on the existing product routes and serves the built frontend from `/app` plus static assets from the frontend dist output. This is the coexistence mode.
- `spa`: Python still owns `/api/*`, `/create-novel`, and the no-`project_id` start page, but serves the built frontend `index.html` for product GET routes and static assets from the dist output.

In both `hybrid` and `spa`, the legacy shell remains available under `/legacy/...` for rollback-safe checks before final cutover.

## Dist output

Production/local release expects the frontend build to exist at `apps/frontend/dist/`. The Python process serves that directory directly; the default local-user release workflow does not require a separate frontend process.

## Startup commands

### Legacy shell

```powershell
python superwriter_local_server.py
```

### Hybrid mode

```powershell
$env:SUPERWRITER_FRONTEND_MODE = "hybrid"
python superwriter_local_server.py
```

Check both surfaces:

```powershell
curl http://127.0.0.1:18080/app
curl "http://127.0.0.1:18080/legacy/command-center?project_id=<project-id>&novel_id=<novel-id>"
```

### SPA mode

```powershell
npm --prefix apps/frontend run build
$env:SUPERWRITER_FRONTEND_MODE = "spa"
python superwriter_local_server.py
```

Check the SPA plus rollback path:

```powershell
curl "http://127.0.0.1:18080/command-center?project_id=<project-id>&novel_id=<novel-id>"
curl "http://127.0.0.1:18080/legacy/command-center?project_id=<project-id>&novel_id=<novel-id>"
```

## Development workflow

Frontend development still uses Vite as a separate dev process with `/api/*` proxied to the Python server. That two-process setup is only for local frontend development; production/local release stays single-process on Python serving the built assets.
