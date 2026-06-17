# BOBO OS AI Assistant

The integrated AI assistant provides context-aware help across the entire desktop.

## Components

```
ai-assistant/
├── assistant-daemon.py   ← D-Bus service backend (Ollama / Claude API)
└── assistant-ui.py       ← GTK4 sliding panel (Win+A or taskbar click)
```

## Activation

- **Win+A** — toggle the assistant panel
- **Taskbar AI button** — same as Win+A
- **Proactive** — surfaces error messages from NovaLayer, drivers, and updates automatically

## Daemon

The daemon (`assistant-daemon.py`) exposes a D-Bus service:

| Service | `os.bobo.AIAssistant` |
|---------|----------------------|
| Object | `/os/bobo/AIAssistant` |

| Method | Signature | Description |
|--------|-----------|-------------|
| `Ask(message)` | `s → s` | Send a message, get a reply |
| `ClearHistory()` | `→ ()` | Clear conversation history |
| `GetStatus()` | `→ s` | Returns backend status string |

### Backends

Configured via `config/bobo-os.conf`:

```bash
AI_BACKEND="ollama"          # local Ollama (default)
AI_OLLAMA_MODEL="llama3"     # model to use
AI_OLLAMA_URL="http://127.0.0.1:11434"

# Alternatively:
AI_BACKEND="claude"
ANTHROPIC_API_KEY="sk-..."   # set as environment variable
```

## UI panel

`assistant-ui.py` is a GTK4 layer-shell panel anchored to the right edge:

- Does **not** steal focus from the active window
- Persistent conversation history: `~/.cache/bobo-os/assistant-history.json`
- File drag-and-drop: drop any file to ask about it
- Quick action chips for common tasks
- Fade-in/out animation (150 ms)

```bash
# Start the UI panel
python3 assistant-ui.py

# Self-test (no display needed for logic tests)
python3 assistant-ui.py --test
```

## Running in development

```bash
# Start Ollama first
ollama serve &
ollama pull llama3

# Start the daemon
python3 assistant-daemon.py &

# Start the UI
python3 assistant-ui.py
```
