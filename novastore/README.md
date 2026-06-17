# NovaStore — BOBO OS App Store

NovaStore is the BOBO OS application store. It provides a GTK4 UI backed by a FastAPI server.

## Architecture

```
novastore/
├── backend/
│   ├── main.py          ← FastAPI server on http://127.0.0.1:8740
│   └── auto-update.py   ← Background update daemon (btrfs snapshots + flatpak)
└── frontend/
    └── store.py         ← GTK4 app store UI
```

## Running

```bash
# Start the backend (normally done by runit sv novastore-backend)
uvicorn bobo.novastore.main:app --host 127.0.0.1 --port 8740

# Start the frontend
python3 novastore/frontend/store.py

# Self-test (frontend)
python3 novastore/frontend/store.py --test
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/apps` | List apps (query: `category`, `search`, `platform`, `limit`, `offset`) |
| GET | `/apps/{id}` | App detail |
| POST | `/apps/{id}/install` | Start install → returns `job_id` |
| GET | `/jobs/{job_id}` | Poll install progress |
| DELETE | `/apps/{id}` | Uninstall |
| GET | `/updates` | List available updates |
| POST | `/updates/apply` | Apply all updates |

## Auto-updates

`auto-update.py` runs as a daemon, checks for updates daily (interval: 86 400 s), takes a btrfs snapshot before applying, and can roll back with `--rollback`.

```bash
python3 auto-update.py --check    # on-demand check
python3 auto-update.py --rollback # revert last update
```
