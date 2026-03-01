# TriggerToDo

FastAPI + SQLite backend for a SPA running in local-DB mode.

## Features

- `/api/*` backend routes + SPA fallback serving
- To Do lists/tasks CRUD via SQLite cache tables
- Task recurrence + complete endpoint
- Task custom fields via open extension `com.triggertodo.meta`
  - `pool`
  - `wfStatus`
  - `triggerRef`
- Trigger engine:
  - Background scheduler
  - Authenticated webhook endpoint
  - Moves tasks between `pool`/`wfStatus` in local DB

## Quick start

1. Install dependencies + build frontend:

```bash
./initialize.sh
```

This script will:
- install backend/frontend dependencies
- build frontend assets
- create DB schema

2. Run server:

```bash
uv run uvicorn app.main:app --reload
```

3. Open `http://localhost:8000/api/health`

## Deploy With Existing DB

If you already have data, deploy the SQLite file directly:

1. Copy `triggertodo.db` to server.
2. Set `DATABASE_URL=sqlite:///./triggertodo.db`.
3. Start server.

`initialize_data.json` scripts are optional and no longer required for normal deployment.

## Testing

Run tests with coverage:

```bash
uv run pytest
```

Coverage is enforced from `pyproject.toml` with a minimum threshold of 35%.

## Core API

- To Do
  - `GET|POST /api/todo/lists`
  - `PATCH|DELETE /api/todo/lists/{list_id}`
  - `GET|POST /api/todo/lists/{list_id}/tasks`
  - `PATCH|DELETE /api/todo/lists/{list_id}/tasks/{task_id}`
  - `PATCH /api/todo/tasks/{task_id}` (list-agnostic task update)
  - `POST /api/todo/lists/{list_id}/tasks/{task_id}/complete`
  - `GET /api/todo/cache/tasks`
- Sync
  - `POST /api/sync/delta`
- Triggers
  - `GET|POST /api/triggers`
  - `PATCH|DELETE /api/triggers/{rule_id}`
  - `POST /api/triggers/run`
  - `POST /api/triggers/webhook` (`X-Trigger-Secret` header)

## Notes

- Scheduler interval is controlled by `TRIGGER_ENGINE_INTERVAL_SECONDS`.
- Trigger rules run by source matching (`source_pool`, `source_wf_status`) and write target fields in local metadata.
