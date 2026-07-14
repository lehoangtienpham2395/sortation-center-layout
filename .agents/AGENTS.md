# Project Rules and Guidelines

To prevent recurring issues with data syncing and incorrect timezone offsets, always adhere to the following rules:

1. **Database Architecture**:
   - **DO NOT USE PostgreSQL (Neon DB)**. The project has been reverted to use the local SQLite database file `backend_sync/db/state.db`.
   - All synchronization and query logic in `sync_to_sheets.py` must interact directly with the local `state.db` file.

2. **GitHub Workflows Configuration**:
   - **DO NOT** enable automatic triggers (push or schedule) in `.github/workflows/sync_inventory.yml` or `.github/workflows/sync.yml`.
   - The sync runs strictly locally on the user's machine via the Windows Task Scheduler task `"SortationCenterAutoSync30min"`. It pulls code, runs the sync locally using SQLite, and pushes the generated JSON output files to GitHub.
