# BuddyAI

BuddyAI is a private AI companion that runs on your own computer. It has a
browser-based chat interface, selectable personalities, saved conversations,
and automatic personal memory.

BuddyAI does **not** train a new AI model. It uses an existing local language
model and personalizes future replies by saving useful facts in a local SQLite
database.

## What BuddyAI can do

- Chat through a simple local web interface.
- Use Chill, Playful, Supportive, or Thoughtful personalities.
- Save conversations so they can be opened again.
- Automatically remember useful facts that the user states directly.
- Use relevant memories in later conversations.
- Show all saved memories and let the user delete them.
- Run without sending conversations to a cloud AI service.

Memory is automatic. There is no approval or editing step. A saved memory can
be viewed or deleted afterward.

## The easiest way to run BuddyAI

The recommended setup uses [Ollama](https://ollama.com/download) and the
`qwen2.5:3b` model.

### 1. Install the required software

Install:

- Python 3.11 or newer
- Ollama

You only need an internet connection while installing the Python packages and
downloading the model. Afterward, BuddyAI and Ollama can run locally.

### 2. Open a terminal in the project folder

```bash
cd /path/to/BuddyAI
```

For this repository on macOS, the command is:

```bash
cd "/Users/janniella/Documents/ChatGPT/BuddyAI"
```

### 3. Create a Python environment

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The environment is active when `(.venv)` appears at the beginning of the
terminal prompt.

### 4. Download the local AI model

Open Ollama. Then run this command in a terminal:

```bash
ollama pull qwen2.5:3b
```

On a headless Linux computer, start Ollama first:

```bash
ollama serve
```

Keep that terminal open and run the remaining commands in a second terminal.

### 5. Start BuddyAI

Make sure the Python environment is active, then run:

```bash
python app.py
```

BuddyAI opens automatically in the default browser. If it does not, open the
local address printed in the terminal. Stop the program with `Ctrl+C`.

## Check that automatic memory works

1. Open the **Chat** tab.
2. Send: `I really enjoy gaming, especially Minecraft.`
3. Wait for the reply. BuddyAI performs a second local model call to find useful
   memories after producing the chat response.
4. Open **What Buddy Knows About Me**.
5. The gaming preference should appear automatically if the local model
   extracted it successfully.
6. Start a new conversation and ask: `What could I do this evening?`
7. BuddyAI can now use the saved preference when answering.

Memory extraction is intentionally selective. A greeting such as `Hello` will
normally create no memory. If extraction fails or the model returns invalid
data, the chat reply is kept and BuddyAI displays a warning instead of saving
an unsafe or malformed memory.

## Where is the data folder?

By default, BuddyAI does **not** create a `data` folder inside the repository.
Personal conversations should not accidentally become part of the source code
or a Git commit.

The default database is named `buddyai.sqlite3` and is stored here:

| Operating system | Default location |
|---|---|
| macOS | `~/Library/Application Support/BuddyAI/buddyai.sqlite3` |
| Windows | `%LOCALAPPDATA%\BuddyAI\buddyai.sqlite3` |
| Linux | `~/.local/share/buddy-ai/buddyai.sqlite3` |

The exact path is also shown in the GUI under **Privacy & Data**. The folder
and database are created when the graphical application starts for the first
time, even before the first message is sent.

To keep the database in this repository instead, start the app with:

macOS or Linux:

```bash
BUDDY_DATA_DIR="$PWD/data" python app.py
```

Windows PowerShell:

```powershell
$env:BUDDY_DATA_DIR="$PWD\data"
python app.py
```

This creates `data/buddyai.sqlite3`. The `data/` folder and SQLite files are
already excluded by `.gitignore`.

## What happens when a message is sent?

```text
User sends a message
        |
        v
BuddyAI finds up to 5 relevant saved memories
        |
        v
The local model creates a reply
        |
        v
The conversation is saved (when history is enabled)
        |
        v
The local model extracts possible memories from the user's message
        |
        v
Valid, non-sensitive, non-duplicate memories are saved automatically
```

Only the user's message is used for memory extraction. The allowed memory
types are:

- `preference` — for example, preferred response style or favorite activities;
- `profile` — a directly stated fact such as a preferred name;
- `interest` — subjects or hobbies the user explicitly likes; and
- `episodic` — a useful event that the user explicitly described.

BuddyAI rejects common credentials and sensitive identifiers, speculative
personality claims, inferred emotions, and medical diagnoses. Similar records
are deduplicated. A recognized updated preference replaces the older one.

Saved memories are used starting with the **next** interaction.

## Using the interface

### Chat

Send messages, start a new conversation, reopen an older conversation, or
clear the active conversation.

### What Buddy Knows About Me

See every automatically created memory. Select one memory to delete it, or use
the confirmation control to delete all memories.

### Companion

Choose a personality and change Buddy's display name. Both settings persist
after restarting the program.

### Privacy & Data

- Turn automatic memory creation and retrieval on or off.
- Turn new conversation-history storage on or off.
- See the exact database path.
- Delete all saved conversations.
- Clear only the current in-memory session.

Turning memory off does not delete existing memories. Turning history off does
not delete older conversations. Use the separate delete controls when removal
is intended.

Deleting a conversation also does not delete personal memories, and deleting a
memory does not remove the same words from an already saved conversation.

## Run the automated tests

The test suite does not require Ollama, a downloaded model, or internet access.

```bash
python -m pytest -q
```

## Terminal-only version

The original command-line interface is still available:

```bash
python main.py
```

Available commands:

```text
/help
/personality chill|playful|supportive|thoughtful
/reset
/model
/exit
```

The terminal interface only keeps the current conversation in memory. Use
`python app.py` for persistent memories and saved conversations.

## Configuration

BuddyAI can be configured with environment variables before it is started.

| Variable | Default | Meaning |
|---|---|---|
| `BUDDY_RUNTIME` | `ollama` | Local runtime: `ollama`, `llama.cpp`, or `lm-studio` |
| `BUDDY_BASE_URL` | Runtime default | Local OpenAI-compatible API address |
| `BUDDY_MODEL` | `qwen2.5:3b` for Ollama | Model identifier |
| `BUDDY_TEMPERATURE` | `0.7` | Reply variety from 0 to 2 |
| `BUDDY_MAX_TOKENS` | `350` | Maximum reply length in tokens |
| `BUDDY_TIMEOUT_SECONDS` | `120` | Maximum wait for a local model request |
| `BUDDY_HISTORY_TURNS` | `10` | Recent complete turns sent to the model |
| `BUDDY_DATA_DIR` | Operating-system app-data folder | Database directory |

Example using a larger Ollama model:

```bash
BUDDY_MODEL=qwen2.5:7b python app.py
```

BuddyAI accepts only local HTTP endpoints on `localhost` or another loopback
address. It rejects remote model URLs so an accidental configuration cannot
send chat text to a cloud endpoint.

### LM Studio

Load an instruction-tuned model in LM Studio and start its local server. Use the
exact model identifier displayed by LM Studio:

```bash
BUDDY_RUNTIME=lm-studio \
BUDDY_MODEL='your-model-identifier' \
python app.py
```

### llama.cpp

Start a local llama.cpp server with an instruction-tuned GGUF model:

```bash
llama-server --model /absolute/path/to/model.gguf --host 127.0.0.1 --port 8080
```

Then, in a second terminal:

```bash
BUDDY_RUNTIME=llama.cpp BUDDY_MODEL=local-model python app.py
```

## Project structure

```text
BuddyAI/
├── app.py                         starts the graphical application
├── main.py                        starts the terminal application
├── config.py                      reads runtime and data settings
├── requirements.txt               Python packages
├── agent/
│   ├── application_controller.py  coordinates chat, history, and memory
│   ├── buddy_agent.py             creates conversational responses
│   ├── conversation_manager.py    keeps recent working context
│   ├── personality.py             defines the four personalities
│   └── prompt_builder.py          safely builds the model prompt
├── memory/
│   ├── database.py                creates and accesses the SQLite database
│   ├── memory_extractor.py        validates model-produced memory JSON
│   ├── memory_manager.py          saves, deduplicates, and updates memories
│   └── memory_retriever.py        finds memories relevant to a message
├── models/
│   ├── base_model.py              shared model interface
│   ├── local_model.py             calls the local OpenAI-compatible API
│   └── model_factory.py           creates the selected runtime adapter
├── prompts/
│   └── memory_extraction.txt      tells the model what may be remembered
├── ui/
│   └── gradio_app.py              builds the browser interface
└── tests/                          automated tests
```

The main graphical request flow is implemented in
`agent/application_controller.py` inside `BuddyApplication.send_message()`.
That is the best starting point when learning how chat, history, and automatic
memory work together.

## Common problems

### `Gradio is not installed`

Activate the environment and reinstall the requirements:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate it with `.venv\Scripts\Activate.ps1` instead.

### `Local runtime unavailable or request failed`

Make sure Ollama is open, then verify that the model exists:

```bash
ollama list
```

If `qwen2.5:3b` is missing, run:

```bash
ollama pull qwen2.5:3b
```

### A reply appears, but no memory is created

This can be normal. The message may not contain a useful long-term fact. Also
check that automatic memory is enabled under **Privacy & Data**. Try a direct
statement such as `I prefer concise answers.` and watch the status below the
chat after sending it.

### The database is not inside the repository

This is expected. See **Where is the data folder?** above or set
`BUDDY_DATA_DIR` when starting the app.

### The application is slow

Each normal interaction can require two local model calls: one for the reply
and one for memory extraction. Speed depends on the computer and model size.
The default 3B model is intended to be a practical CPU-friendly starting point.

## Privacy and limitations

- The graphical server listens only on `127.0.0.1` and does not create a public
  Gradio sharing link.
- BuddyAI has no telemetry or cloud-model fallback.
- The SQLite database is local but is **not encrypted automatically**. Device
  users with enough access may be able to read it.
- Small local models can misunderstand a statement. Every saved memory is
  visible and deletable for this reason.
- Memory search is keyword-based rather than an embedding or vector search.
- The program supports one local user profile.
- Automatic memory extraction adds a second model request and therefore some
  latency.
- BuddyAI does not use a webcam or perform facial-expression recognition.
