# Jarvis

Jarvis is a voice-controlled AI assistant that runs as a companion app on your machine. It stays idle in the background until you say the wake word, then listens, responds, and can take actions on your behalf - answering questions, pulling real-time info, or working with your email and calendar.

> **Status:** Currently tested on macOS. Windows support is a work in progress.

## Current features
- Voice-first interaction with wake-word activation (idle until triggered)
- General conversations
- Web search for latest news, weather, or any real-time info
- macOS control by voice - see below

### macOS voice controls

Built-in tools for hands-free Mac use (macOS only):

| Capability | What you can say | Tool |
| --- | --- | --- |
| Launch apps | "Open Spotify", "Launch VS Code" | `open_mac_app` |
| Spotify transport | "Play / pause / next / previous", "set volume to 40", "what's playing" | `spotify_*` |
| Global media | "Pause the music", "next track", "what song is this?" - picks Spotify or Apple Music automatically | `media_*` |
| Window snapping | "Put this on the left", "snap to top-right", "maximize", "center the window" | `snap_window`, `minimize_window` |
| Screenshots | "Take a screenshot" (save to Desktop) | `screenshot_save` |
| iMessage | "Text Mom I'm running late", "iMessage +1555… saying …" - confirms before sending | `send_imessage` |
| Run shell | "Run `npm run dev` in the jarvis folder", "open a Terminal and pull the latest" | `run_in_terminal` |
| Browser tab | "What tab am I on?", "open github dot com in incognito" | `browser_active_tab`, `browser_open_url` |
| Spotlight find/open | "Find my taxes folder", "where's the lease PDF?", "open Downloads", "reveal that file in Finder" | `find_files`, `open_path` |
| Reminders + Calendar | "Remind me to call mom at 5", "add milk to groceries", "block 3 to 4 tomorrow for design" | `add_reminder`, `add_calendar_event` |
| Focus mode | "Turn on do not disturb", "start deep work", "end focus" | `set_focus`, `end_focus` |
| System status | "What's my battery?", "how's my Wi-Fi?", "am I on VPN?", "system status" | `system_status` |
| Clipboard | "What's on my clipboard?", "copy this to my clipboard" | `read_clipboard`, `write_clipboard` |
| Meeting mute | "Mute me", "unmute", "mute the meeting" - works in Zoom, Teams, Google Meet | `toggle_meeting_mute` |
| **Shortcuts.app** | "Run my Take a Break shortcut", "summarize this tab", "add milk to groceries", "what shortcuts can I run?" | `list_shortcuts`, `run_shortcut` |

#### macOS permissions

Permissions are granted to the **host process** running Jarvis - typically your terminal (Terminal.app or iTerm), your IDE if you launch from there, or the packaged app once distributed. macOS will prompt the first time each permission is needed; this section is just so you know what to expect.

**Where to grant** - System Settings → Privacy & Security:

- **Accessibility** - for tools that send keystrokes or move/resize windows.
- **Screen Recording** - for screen capture (`screencapture`).
- **Automation** - appears as one prompt per target app (e.g. "Terminal is requesting access to Spotify"). Approve each once.
- **Contacts** / **Reminders** / **Calendars** - privacy panes; the first call to a relevant tool triggers the dialog.
- **Full Disk Access** - *optional*. Improves Spotlight (`find_files`) coverage for indexed-but-protected folders.

**Per-tool matrix** - what each tool actually needs:

| Tool | macOS permission(s) | Env var |
| --- | --- | --- |
| `open_mac_app` | - | - |
| `spotify_*` | Automation → Spotify | - |
| `media_play_pause`, `media_next`, `media_previous`, `media_now_playing` | Automation → Spotify, Music; Automation → System Events (process check) | - |
| `snap_window`, `minimize_window` | **Accessibility** (System Events UI scripting) + Automation → Finder | - |
| `screenshot_save` | **Screen Recording** | - |
| `send_imessage` | Automation → Messages; Automation → Contacts + **Contacts** privacy (only if resolving by name) | - |
| `run_in_terminal` | Automation → Terminal *or* iTerm | - |
| `browser_active_tab`, `browser_open_url` | Automation → Google Chrome and/or Safari (whichever you use) | - |
| `find_files`, `open_path` | - (Full Disk Access optional for full Spotlight coverage) | - |
| `add_reminder` | Automation → Reminders + **Reminders** privacy | - |
| `add_calendar_event` | Automation → Calendar + **Calendars** privacy | - |
| `set_focus`, `end_focus` | One-time `Set Focus` shortcut in Shortcuts.app (see Notes) | - |
| `system_status` | - | - |
| `read_clipboard`, `write_clipboard` | - | - |
| `toggle_meeting_mute` | **Accessibility** (keystrokes) + Automation → target app (Zoom / Microsoft Teams / your browser for Meet) | - |
| `list_shortcuts`, `run_shortcut` | - for the bridge itself; each shortcut may prompt for its own per-action permissions on first run | - |

**API keys** - set in `.env.local`:

- The core agent keys (`LIVEKIT_*`, plus your chosen TTS / STT / LLM provider) are covered in **Dev Setup** below.

**Tip** - to pre-clear Automation prompts, run each tool once interactively (or trigger its underlying action in any app). macOS doesn't surface the prompts again after first approval; if you ever revoke or reset them, they reappear. You can audit them at System Settings → Privacy & Security → Automation.

#### Notes & limitations

- Window snapping treats "fullscreen" as *maximized to the visible screen frame*, not the green-button native fullscreen Space.
- Global media keys do **not** control browser audio (YouTube etc.) - macOS doesn't expose that surface to AppleScript.
- `run_in_terminal` dispatches the command to a visible Terminal/iTerm window and returns immediately. It does not capture command output.
- `send_imessage` sends immediately and cannot be recalled. The agent is instructed to read back the recipient and message before calling it - confirm out loud.
- `set_focus` / `end_focus` need a one-time **Set Focus** shortcut in Shortcuts.app: create a new shortcut named exactly `Set Focus`, add the **Set Focus** action, and wire its parameter to `Shortcut Input`. The tool returns setup instructions if it's missing.
- `toggle_meeting_mute` activates the meeting app briefly to deliver the hotkey when it's not already frontmost - expect a ~150 ms focus flicker. Slack huddles and Discord aren't supported. Google Meet only triggers when the browser is frontmost AND the active tab is on `meet.google.com` (so we don't mute the wrong tab).

#### Shortcuts.app bridge - zero-config voice automation

Anything you can build in **Shortcuts.app** (built-in on macOS) can be triggered by voice. No code, no per-shortcut wiring - Jarvis discovers your shortcuts automatically at session start and matches them by name.

How it works:

1. Open **Shortcuts.app** and build a shortcut visually. Give it a name you'd say out loud (e.g. "Summarize Current Tab").
2. Run it once manually so macOS clears any one-time permission prompts.
3. Start Jarvis. The library is loaded into a 5-minute cache automatically. Just ask: *"Run my summarize current tab shortcut."*
4. Added a new shortcut mid-session? Say *"refresh shortcuts"* and the agent will re-read the library.

Voice → tool flow:

- *"What shortcuts do I have?"* → `list_shortcuts` returns the names.
- *"Run my Shazam shortcut."* → `run_shortcut(name="Shazam shortcut")` → returns the song.
- *"Summarize this tab."* → matches a shortcut named "Summarize Current Tab" via case-insensitive substring fallback.
- *"Translate clipboard to Spanish."* → if you have a "Translate Clipboard" shortcut that takes text input, the agent passes the clipboard contents through `text_input`.

A few example shortcuts worth building:

| Shortcut name | What it does | Voice trigger |
| --- | --- | --- |
| Summarize Current Tab | Get URL of frontmost Safari tab → fetch contents → Apple Intelligence summary | "Summarize this tab" |
| Add to Groceries | Add input to a Reminders list called Groceries | "Add milk to groceries" |
| Deep Work | Toggle Focus mode + close Slack + open Notion | "Start deep work" |
| Next Meeting | Read next event from Calendar | "What's my next meeting?" |
| OCR Screenshot | Screenshot region + Apple Vision text recognition + copy result | "OCR my screen" |
| Find My Phone | Trigger Find My ping | "Where's my phone?" |
| Shazam It | Identify song playing nearby | "What song is this?" |

Caveats:

- Shortcut names must be unique. The agent matches case-insensitively and accepts a single-substring fallback (so "deep work" finds "Deep Work Mode") - but ambiguous names return suggestions instead of running.
- Shortcuts that prompt for UI input ("Choose from list", file pickers) will block the voice flow. Prefer shortcuts that have hard-coded defaults or accept text input.
- First run of any shortcut may show a one-time permission dialog (Reminders, Photos, etc.). Run it once by hand before voice-triggering it.
- Output is text. For shortcuts that return images or files, save them inside the shortcut and have it return a path string.

# Dev Setup

Clone the repository and install dependencies to a virtual environment:

```
uv sync
```

Create `.env.local` file based on `.env.example` file and add required keys

Livekit can [local hosted](https://docs.livekit.io/home/self-hosting/local/) or cloud. Get the Livekit keys
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Get other required keys for TTS, STT and LLM (including Perplexity). OR You can use livekit inference so you won't need separate api keys, just livekit cloud keys will be enough. `TTS`, `STT` and `LLM` can be changed easily.. more [here](https://docs.livekit.io/agents/models/)

### Personalization

The assistant's name (also used as the wake word), the user's name, country, and the startup greeting are read from `.env.local`. Defaults kick in if the variable is unset.

| Variable | Default | What it does |
| --- | --- | --- |
| `ASSISTANT_NAME` | `Jarvis` | Name used in the system prompt and as the wake word (e.g. "hey jarvis") |
| `ASSISTANT_GREETING` | `Hello There!` | Spoken on session start |
| `USER_NAME` | `User` | Used in the system prompt so the assistant addresses you by name |
| `USER_COUNTRY` | `Canada` | Used for locale-aware responses (timezone hints, units, etc.) |
| `USER_AWAY_TIMEOUT` | `10` | Seconds of silence before the assistant auto-mutes. Say the wake word (e.g. *"hey jarvis"*) to resume. Set to `0` or `none` to disable. |

#### Mute / unmute

The assistant has two ways to stop listening:

- **Auto-mute** - after `USER_AWAY_TIMEOUT` seconds of silence (default 10s), the assistant goes idle. Wake it back up with the wake word, e.g. *"hey jarvis"*.
- **Explicit mute** - say *"mute"* to silence it on demand. Resume with *"unmute"* or the wake word.

You can extend the capabilities of assistant by creating [new tool](https://docs.livekit.io/agents/build/tools/) or using [MCP integration](https://docs.livekit.io/agents/build/tools/#model-context-protocol-mcp-)


# Run the Assistant

Before your first run, you must download certain models such as [Silero VAD](https://docs.livekit.io/agents/build/turns/vad/) and the [LiveKit turn detector](https://docs.livekit.io/agents/build/turns/turn-detector/):

`uv run python -m agent download-files`

Next, run this command to speak to your agent directly in your terminal:

`uv run python -m agent console`


