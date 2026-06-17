# BOBO OS — Init System (runit)

BOBO OS uses **runit** as its init system. runit is a fast, simple, reliable
process supervisor with three stages.

## Stage files

| File | Purpose |
|------|---------|
| `1`  | System initialization: mount filesystems, start udev, set up zram |
| `2`  | Service supervisor loop: starts `runsvdir` which manages all services |
| `3`  | Shutdown / reboot: stop services, sync disks, power off |

## Services (`sv/`)

Each service is a directory containing:
- `run` — the script that starts the service (must `exec` the daemon)
- `finish` — called when `run` exits (optional)
- `log/run` — pipes stdout/stderr through `svlogd`

| Service | Description |
|---------|-------------|
| `display-manager` | Wayfire Wayland compositor |
| `networkd` | Network management (systemd-networkd + iwd) |
| `bluetoothd` | Bluetooth (BlueZ) |
| `pipewire` | Audio/video routing |
| `novalayer` | Multi-platform compatibility daemon |
| `novasync` | Cloud sync daemon |
| `novastore-backend` | App store API (FastAPI, port 8740) |
| `ai-assistant` | AI assistant background daemon |
| `clamav` | Antivirus (clamd) |
| `firewall` | nftables rules loader (one-shot) |

## Boot order

```
Stage 1  →  udev, zram, modules
Stage 2  →  runsvdir (starts all services in /etc/service/ in parallel)
             ├── firewall      (first: security rules before any network)
             ├── networkd
             ├── bluetoothd
             ├── pipewire
             ├── display-manager
             ├── novalayer     (waits for D-Bus)
             ├── novasync      (waits for D-Bus + network)
             ├── novastore-backend
             ├── clamav
             └── ai-assistant
```

## How to manage services

```sh
# Check status of a service
sv status /etc/service/display-manager

# Restart a service
sv restart /etc/service/pipewire

# Stop a service temporarily
sv stop /etc/service/novasync

# View live logs
tail -f /var/log/bobo/display-manager/current
```

## Testing (self-test)

Run from a BOBO OS live environment:
```sh
for svc in display-manager networkd bluetoothd pipewire novalayer \
           novasync novastore-backend ai-assistant clamav firewall; do
  status=$(sv status /etc/service/$svc 2>&1 | head -1)
  echo "$svc: $status"
done
```
