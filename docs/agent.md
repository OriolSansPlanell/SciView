# AI assistants

There are two ways to have a language model build the film with you:

* the **assistant panel** in the editor, which talks to a model served on your computer (Ollama, LM Studio,
  llama.cpp, vLLM or any OpenAI-compatible server);
* the **MCP server**, `sciview mcp`, for assistants that run elsewhere and speak the Model Context Protocol,
  such as Claude Desktop or LM Studio's chat.

Both use the same checked tools, so the model can only do what you could do in the editor, and never touches
locked objects.

## The assistant panel

Open it with **Assistant** in the editor's top bar. The first time, press the settings button and choose:

* **Server**: Ollama (`http://localhost:11434/v1`), LM Studio (`http://localhost:1234/v1`), llama.cpp server
  (`http://localhost:8080/v1`), vLLM (`http://localhost:8000/v1`) or another address. Hosted services that
  speak the OpenAI chat API work too; their API key is stored only on your computer.
* **Model**: **Find models** lists what the server offers. Choose one that calls tools reliably. Models of
  about 30 billion parameters (Gemma 4 31B, Qwen 3 32B, Mistral Small) do well; very small models often miss
  steps or invent property names.
* **Let the model see frames**: sends the pictures it renders, so it can check its own work. Needs a model
  with image input; turn it off otherwise.

The settings are kept per user (`~/.config/sciview/assistant.json` on Linux, `~/Library/Application
Support/SciView` on macOS, `%APPDATA%\SciView` on Windows; `SCIVIEW_CONFIG_DIR` overrides it).

How a request runs:

1. The model gets your request, a description of the film (or of the scene or objects you allowed under
   **May change**) and the tools.
2. It changes the film step by step; each change shows in the preview at once.
3. After every round of changes SciView checks the result: problems in the film (missing files, bad
   expressions, broken references), text that overlaps other text and objects outside the frame. These are
   sent back to the model, which fixes them before it answers.
4. The panel lists **what changed** and, under **Please check**, values the model chose itself: numbers that
   are not in your request or in the film already, and new wording. Check those before you show the film.
5. The whole request is one undo step.

While a request runs, the editor does not accept your own edits; the stop button ends the request early,
keeping what was done so far (it is still one undo step).

### Comparing models

A benchmark of 42 small tasks (adding objects, keyframes, timing, layout, scenes, captions, themes, staying
inside the scope, not inventing values) checks each result automatically:

```bash
python -m sciview.agent.bench --base-url http://localhost:11434/v1 --model gemma4:31b
python -m sciview.agent.bench --model gemma4:26b --only scenes,layout -o results.json
python -m sciview.agent.bench --list
```

It prints the pass rate per group, the steps and the time per task, and `-o` writes everything as JSON. Use
it to choose a model for your computer or to see whether a new model is worth switching to.

## The MCP server

SciView can be driven by an outside AI assistant through the
[Model Context Protocol](https://modelcontextprotocol.io) (MCP). The assistant gets a small set of checked tools: it can read the film, add objects, set values and
keyframes, change timing and look at frames, but it cannot run code, open other files or touch objects you
have locked. It works with assistants that run on your own computer, such as a local model in LM Studio, and
with hosted ones such as Claude Desktop.

```bash
sciview mcp film.sciview.json                  # edit a project file; it is saved after every change
sciview mcp --editor http://localhost:8765     # drive the open editor: changes appear live
```

The command speaks MCP over standard input and output, so you do not run it yourself: you tell your assistant
how to start it, and the assistant starts it when it needs it.

### Connecting an assistant

Most assistants read a JSON file listing MCP servers. Use absolute paths, because the assistant does not start
the command in your project folder. If `sciview` is not found, give the full path of the executable
(`which sciview` on macOS and Linux, `where sciview` on Windows) or use your Python with `-m sciview`.

**Claude Desktop**: Settings → Developer → Edit Config opens `claude_desktop_config.json`. Add:

```json
{
  "mcpServers": {
    "sciview": {
      "command": "sciview",
      "args": ["mcp", "/Users/me/talks/neutrons/film.sciview.json"]
    }
  }
}
```

and restart Claude Desktop.

**LM Studio** (0.3.17 or later): edit `mcp.json` from the Program tab (it lives in `~/.lmstudio/mcp.json`) and
add the same `"sciview"` entry under `"mcpServers"`. Choose a model that is good at calling tools; models with
around 30 billion parameters or more follow the tool descriptions much more reliably than small ones.

**Other clients** (Cursor, VS Code, Open WebUI through an MCP bridge, your own scripts): any client with the
stdio transport works with the same command and arguments.

To let the assistant work in the editor while you watch, start the editor first (`sciview edit film.sciview.json`)
and use `"args": ["mcp", "--editor", "http://localhost:8765"]`. Every change appears in the editor within about
a second with a short note, and Ctrl+Z takes back what you do not want, like your own edits (changes that
arrive within the same second are undone together).

### Limiting what it may change

```bash
sciview mcp film.sciview.json --time 12 20          # only between 12 s and 20 s
sciview mcp film.sciview.json --ids title1,caption3 # only these objects (and the ones it adds)
sciview mcp film.sciview.json --scene Method        # only this scene
```

Locked objects (the lock in the editor's timeline, or `obj.locked = True`) are never changed, deleted or
grouped, whatever the scope. A tool call outside the scope is refused with a message that says why, so the
assistant can tell you instead of guessing.

### The tools

| Tool | What it does |
| --- | --- |
| `list_object_types` | Every object type, with what it is for |
| `get_schema` | The properties of one type: kinds, defaults, ranges, choices and help |
| `describe_film` | Settings, camera, every object with its values, keyframes and timing, the problems found and the scope |
| `add_object` | Add an object with properties and timing |
| `set_property` | Set a value, or add a keyframe when a time is given |
| `add_keyframe`, `remove_keyframe` | Animate a property |
| `set_timing` | When an object appears and disappears, and its effects |
| `place` | Move a 2D object to a region of the frame (`center`, `top-left`, `right-third`…) |
| `align` | Line up 2D objects (left, centre, right, top, middle, bottom) or space them evenly |
| `group` | Put objects in a group |
| `delete` | Delete an object (a group goes with its members) |
| `add_scene`, `set_scene` | Add a scene (empty, or from a template), change its name, length, transition and notes |
| `render_frame` | The picture at a time (of a scene), so the assistant can look at what it made |
| `check_frames` | Text that overlaps, objects outside the frame, text that is hard to read |
| `validate` | Missing files, unreadable expressions, broken references |
| `review` | Everything changed in this session, for you to check |

Every value is checked against the property's kind and range before it is applied. The assistant is told to
use your numbers and expressions and to ask, or mark placeholders clearly, rather than invent scientific
values; check what it made before you show the film.

## From Python

The same tools are available without MCP, for example to connect your own model:

```python
import sciview as sv
from sciview.agent import FilmTools

film = sv.load("film.sciview.json")
tools = FilmTools(film, scope={"time": [12, 20]})
print(tools.call("describe_film", {}))
tools.call("add_object", {"type": "caption", "props": {"text": "The beam hardens"}, "start": 13})
film.save()
```

`sciview.agent.TOOLS` holds each tool's description and JSON schema, ready to pass to a model that calls
functions.
