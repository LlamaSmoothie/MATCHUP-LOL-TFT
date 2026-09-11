# Application data

- `static/queues.json`: LoL queue descriptions used by the backend.
- `static/summoner.json`: Summoner-spell metadata used by the backend.
- `tftlol.sqlite3`: Persistent runtime cache and recent-search database, ignored
  by Git. Its location and existing contents were preserved during reorganization.

The database location can be overridden with `DATABASE_PATH` in root `config.env`.
Unused historical rune and TFT snapshots are preserved in `archive/desktop/data/`.
