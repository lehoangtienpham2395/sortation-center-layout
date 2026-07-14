# Project Rules and Guidelines

To prevent recurring issues with data syncing and incorrect timezone offsets, always adhere to the following rules:

1. **GitHub Workflows Configuration**:
   - **DO NOT** enable automatic triggers (push or schedule) in `.github/workflows/sync_inventory.yml`. This workflow runs without `--sync-only` and pulls raw UTC timezone data, which overwrites correct local data.
   - The primary active workflow is `.github/workflows/sync.yml`. It runs every 30 minutes and executes:
     `python -u sync_to_sheets.py --sync-only`

2. **Timezone Handling**:
   - All backend processing logic (`sync_to_sheets.py`) and data processing must use `Asia/Ho_Chi_Minh` timezone conversion.
   - Database timestamps in Neon PostgreSQL are stored in UTC and must be converted to ICT (`+07:00`) prior to generating operating dates via `get_operating_date()`.

3. **Performance Optimization (Migration Guard)**:
   - Ensure the `init_db()` migration logic in `sync_to_sheets.py` uses the `_INIT_DB_DONE` guard so that database migrations are strictly executed only once per process, avoiding redundant database scans and timeouts.
