# NovaSync — Cloud Synchronisation

NovaSync keeps your files in sync with iCloud Drive, OneDrive, and Google Drive.

## Components

```
novasync/
├── novasync-daemon.py        ← D-Bus orchestration daemon
├── icloud/
│   └── icloud-connector.py  ← iCloud Drive, Photos, Contacts, Calendars, Notes
├── onedrive/
│   └── onedrive-connector.py ← OneDrive via Microsoft Graph API delta sync
└── googledrive/
    └── googledrive-connector.py ← Google Drive API v3 (rclone fallback)
```

## Local sync paths

| Service | Local path |
|---------|-----------|
| iCloud Drive | `~/iCloud Drive/Drive/` |
| iCloud Photos | `~/iCloud Drive/Photos/` |
| iCloud Contacts | `~/iCloud Drive/Contacts/*.vcf` |
| iCloud Calendars | `~/iCloud Drive/Calendars/*.ics` |
| OneDrive | `~/OneDrive/` |
| Google Drive | `~/Google Drive/` |

## D-Bus interface

Service: `os.bobo.NovaSync`  
Object: `/os/bobo/NovaSync`

| Method | Description |
|--------|-------------|
| `GetStatus()` | Returns JSON status for all connectors |
| `TriggerSync()` | Starts a full sync immediately |
| `SetPaused(bool)` | Pause/resume background sync |

## Usage

```bash
# Manual sync trigger
python3 novasync-daemon.py --sync

# Status
python3 novasync-daemon.py --status

# iCloud only
python3 icloud/icloud-connector.py --sync

# OneDrive only
python3 onedrive/onedrive-connector.py --sync

# Google Drive only
python3 googledrive/googledrive-connector.py --sync
```

## Dependencies

```bash
pip3 install pyicloud caldav secretstorage \
             google-api-python-client google-auth-httplib2 google-auth-oauthlib \
             requests httpx
```
