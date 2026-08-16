# Site Copy Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local-only markdown editor that lays out every editable prose block on thebrainstormlabs.com and publishes edits with one button.

**Architecture:** Markdown files in `content/` are the source of truth for prose; the two committed HTML files stay the source of truth for structure. Each prose region is delimited by `<!--edit:ID-->` / `<!--/edit:ID-->` comments, and publishing renders the markdown in the browser and replaces the text between those markers. A ~100-line stdlib Python server serves the editor, serves `site/` for preview, and on publish writes files then runs git and wrangler.

**Tech Stack:** Python 3 stdlib (`http.server`, `subprocess`, `json`, `pathlib`), vendored `marked.min.js`, plain HTML/CSS/JS. No pip installs, no npm packages, no `package.json`.

**Spec:** `docs/superpowers/specs/2026-08-16-site-editor-design.md`

## Global Constraints

- Repo root is `~/Documents/projects/brainstormlabs`. All paths below are relative to it.
- No new runtime dependencies. Python stdlib only on the server; one vendored JS file on the client.
- Server binds `127.0.0.1` only, port `8765`.
- Cloudflare Pages project name is `brainstormlabs`; deploy command is `npx wrangler pages deploy site/ --project-name brainstormlabs`.
- Git remote is `origin`, branch is `master`, and `master` is the production branch — a deploy from it goes live.
- Site design rules (from `CLAUDE.md`): near-white bg, near-black text, one accent color, no gradients or shadows. The editor page does not have to follow these — it is a tool, not the site — but keep it plain.
- Never edit `site/_headers`, the download button hrefs, the screenshot grid, the controls table, or the signup form.
- Python is invoked as `python3`.

---

### Task 1: Marker injection

**Files:**
- Create: `tools/editor/serve.py`
- Create: `tools/editor/test_inject.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `inject(html: str, block_id: str, body: str) -> str` in `tools/editor/serve.py`. Raises `ValueError` on any marker problem. Later tasks import it as `from serve import inject, BLOCKS`.

- [ ] **Step 1: Write the failing test**

Create `tools/editor/test_inject.py`:

```python
"""Run: python3 tools/editor/test_inject.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from serve import inject

PAGE = (
    "<body>\n"
    "  <p>untouched before</p>\n"
    "  <!--edit:intro-->\n"
    "  <p>old</p>\n"
    "  <!--/edit:intro-->\n"
    "  <p>untouched after</p>\n"
    "</body>\n"
)


def test_replaces_only_between_markers():
    out = inject(PAGE, "intro", "<p>new</p>")
    assert "<p>new</p>" in out
    assert "<p>old</p>" not in out
    assert "<p>untouched before</p>" in out
    assert "<p>untouched after</p>" in out
    assert out.startswith("<body>\n  <p>untouched before</p>\n")
    assert out.endswith("  <p>untouched after</p>\n</body>\n")


def test_is_idempotent():
    once = inject(PAGE, "intro", "<p>new</p>")
    twice = inject(once, "intro", "<p>new</p>")
    assert once == twice


def test_leading_and_trailing_whitespace_in_body_is_normalised():
    a = inject(PAGE, "intro", "<p>new</p>")
    b = inject(PAGE, "intro", "\n\n  <p>new</p>  \n\n")
    assert a == b


def test_missing_marker_raises():
    try:
        inject(PAGE, "nope", "<p>new</p>")
    except ValueError as e:
        assert "nope" in str(e)
    else:
        raise AssertionError("expected ValueError for a missing marker")


def test_unclosed_marker_raises():
    page = "<body><!--edit:intro--><p>old</p></body>"
    try:
        inject(page, "intro", "<p>new</p>")
    except ValueError as e:
        assert "intro" in str(e)
    else:
        raise AssertionError("expected ValueError for an unclosed marker")


def test_duplicated_marker_raises():
    page = PAGE + PAGE
    try:
        inject(page, "intro", "<p>new</p>")
    except ValueError as e:
        assert "intro" in str(e)
    else:
        raise AssertionError("expected ValueError for a duplicated marker")


def test_close_before_open_raises():
    page = "<body><!--/edit:intro--><p>old</p><!--edit:intro--></body>"
    try:
        inject(page, "intro", "<p>new</p>")
    except ValueError as e:
        assert "intro" in str(e)
    else:
        raise AssertionError("expected ValueError when close precedes open")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tools/editor/test_inject.py`
Expected: `ModuleNotFoundError: No module named 'serve'`

- [ ] **Step 3: Write the minimal implementation**

Create `tools/editor/serve.py`:

```python
#!/usr/bin/env python3
"""Local copy editor for the Brainstorm Labs site.

Run:  python3 tools/editor/serve.py
Then: http://127.0.0.1:8765
"""


def inject(html: str, block_id: str, body: str) -> str:
    """Replace the text between this block's markers with `body`."""
    open_m = f"<!--edit:{block_id}-->"
    close_m = f"<!--/edit:{block_id}-->"
    if html.count(open_m) != 1 or html.count(close_m) != 1:
        raise ValueError(
            f"{block_id}: expected exactly one {open_m} and one {close_m}, "
            f"found {html.count(open_m)} and {html.count(close_m)}"
        )
    start = html.index(open_m) + len(open_m)
    end = html.index(close_m)
    if end < start:
        raise ValueError(f"{block_id}: closing marker comes before the opening one")
    return html[:start] + "\n" + body.strip() + "\n" + html[end:]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tools/editor/test_inject.py`
Expected: seven `ok test_...` lines then `all passed`

- [ ] **Step 5: Commit**

```bash
git add tools/editor/serve.py tools/editor/test_inject.py
git commit -m "feat(editor): marker injection with tests"
```

---

### Task 2: Server and editor page (read-only)

Serves the editor, the block list, and a live preview of `site/`. No publishing yet.

**Files:**
- Modify: `tools/editor/serve.py`
- Create: `tools/editor/editor.html`
- Create: `tools/editor/marked.min.js` (downloaded, committed)
- Create: `content/.gitkeep`

**Interfaces:**
- Consumes: `inject()` from Task 1.
- Produces: `BLOCKS: dict[str, tuple[str, str]]` mapping `block_id -> (html_file_relative_to_site, human_label)`; HTTP endpoints `GET /`, `GET /marked.min.js`, `GET /blocks`, `GET /preview/*`.

- [ ] **Step 1: Vendor the markdown renderer**

```bash
mkdir -p tools/editor content
touch content/.gitkeep
curl -fsSL https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js -o tools/editor/marked.min.js
head -c 120 tools/editor/marked.min.js
```

Expected: a minified JS banner mentioning `marked`. If the download fails, stop and report — there is no fallback renderer in this design.

- [ ] **Step 2: Add the block map and the server to `serve.py`**

Append to `tools/editor/serve.py` (the `inject` function stays at the top):

```python
import http.server
import json
import mimetypes
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
CONTENT = ROOT / "content"
HERE = Path(__file__).resolve().parent
PORT = 8765

# block id -> (page relative to site/, label shown in the editor)
BLOCKS = {
    "intro-heading": ("index.html", "Home / headline"),
    "intro-body": ("index.html", "Home / intro + what I'm working on"),
    "card-reactor-drone": ("index.html", "Home / Reactor Drone card"),
    "card-daisysynth": ("index.html", "Home / DaisySynth card"),
    "contact": ("index.html", "Home / contact"),
    "rd-description": ("reactor-drone/index.html", "Reactor Drone / description"),
    "rd-mac-note": ("reactor-drone/index.html", "Reactor Drone / Mac warning"),
    "rd-download-footnote": ("reactor-drone/index.html", "Reactor Drone / download footnote"),
    "rd-mailing-list": ("reactor-drone/index.html", "Reactor Drone / stay up to date"),
    "rd-how-to-play": ("reactor-drone/index.html", "Reactor Drone / how to play"),
    "rd-installing": ("reactor-drone/index.html", "Reactor Drone / installing"),
    "rd-requirements": ("reactor-drone/index.html", "Reactor Drone / system requirements"),
}


def read_blocks() -> dict:
    out = {}
    for block_id, (page, label) in BLOCKS.items():
        md_path = CONTENT / f"{block_id}.md"
        out[block_id] = {
            "label": label,
            "page": page,
            "md": md_path.read_text() if md_path.exists() else "",
        }
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "editor.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/marked.min.js":
            self._send(200, (HERE / "marked.min.js").read_bytes(), "text/javascript")
        elif self.path == "/blocks":
            self._send(200, json.dumps(read_blocks()), "application/json")
        elif self.path.startswith("/preview/"):
            rel = self.path[len("/preview/"):].split("?")[0] or "index.html"
            target = (SITE / rel).resolve()
            if target.is_dir():
                target = target / "index.html"
            if SITE not in target.parents or not target.is_file():
                self._send(404, "not found")
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype)
        else:
            self._send(404, "not found")

    def log_message(self, fmt, *args):
        pass  # ponytail: the page shows what happened; the console does not need to


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}/"
    print(f"editing {ROOT}\nopen {url}")
    webbrowser.open(url)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
```

Note the preview rewrite: pages reference `style.css?v=4` and `../style.css?v=4`, which resolve correctly under `/preview/` because the paths are relative. The home page's absolute links (`/reactor-drone/`, `/#projects`) will escape the preview prefix — that is expected and not worth fixing; use the preview to check rendering, not navigation.

- [ ] **Step 3: Write the editor page**

Create `tools/editor/editor.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Site copy editor</title>
<style>
  body { font: 15px/1.5 system-ui, sans-serif; margin: 0; background: #fafafa; color: #111; }
  header { position: sticky; top: 0; display: flex; gap: 1rem; align-items: center;
           padding: .75rem 1.25rem; background: #fff; border-bottom: 1px solid #ddd; }
  h1 { font-size: 1rem; margin: 0; flex: 1; }
  button { font: inherit; padding: .5rem 1rem; cursor: pointer; }
  main { padding: 1.25rem; max-width: 1100px; }
  .block { border: 1px solid #ddd; background: #fff; margin-bottom: 1.25rem; }
  .block h2 { font-size: .85rem; text-transform: uppercase; letter-spacing: .05em;
              margin: 0; padding: .5rem .75rem; border-bottom: 1px solid #eee; color: #555; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; }
  textarea { font: 14px/1.5 ui-monospace, monospace; border: 0; border-right: 1px solid #eee;
             padding: .75rem; resize: vertical; min-height: 9rem; }
  .rendered { padding: .75rem; overflow-x: auto; }
  .rendered :first-child { margin-top: 0; }
  #log { white-space: pre-wrap; font: 13px/1.4 ui-monospace, monospace;
         background: #111; color: #eee; padding: 1rem; display: none; }
  .dirty { outline: 2px solid #c60; }
</style>
</head>
<body>
<header>
  <h1>Site copy</h1>
  <a href="/preview/" target="_blank">preview site</a>
  <button id="publish">Publish to thebrainstormlabs.com</button>
</header>
<pre id="log"></pre>
<main id="blocks">loading…</main>
<script src="/marked.min.js"></script>
<script>
const state = {};
const render = md => marked.parse(md, { mangle: false, headerIds: false });

fetch('/blocks').then(r => r.json()).then(blocks => {
  const main = document.getElementById('blocks');
  main.innerHTML = '';
  for (const [id, b] of Object.entries(blocks)) {
    state[id] = b.md;
    const el = document.createElement('section');
    el.className = 'block';
    el.innerHTML = `<h2>${b.label}</h2><div class="pair"><textarea spellcheck="true"></textarea><div class="rendered"></div></div>`;
    const ta = el.querySelector('textarea');
    const out = el.querySelector('.rendered');
    ta.value = b.md;
    out.innerHTML = render(b.md);
    ta.addEventListener('input', () => {
      state[id] = ta.value;
      out.innerHTML = render(ta.value);
      el.classList.add('dirty');
    });
    main.appendChild(el);
  }
});
</script>
</body>
</html>
```

- [ ] **Step 4: Run it and check what loads**

```bash
python3 tools/editor/serve.py
```

Expected: browser opens on the editor. Twelve empty labeled boxes appear (the `content/*.md` files do not exist yet — that is Tasks 3 and 4). `preview site` opens the real home page, styled. Stop the server with Ctrl-C.

- [ ] **Step 5: Commit**

```bash
git add tools/editor content/.gitkeep
git commit -m "feat(editor): local server, editor page, vendored marked"
```

---

### Task 3: Migrate the home page

Move `site/index.html`'s prose into `content/*.md`, add markers, adjust the two CSS rules that hang off classes markdown cannot emit.

**Files:**
- Modify: `site/index.html`
- Modify: `site/style.css:184-192`
- Create: `content/intro-heading.md`, `content/intro-body.md`, `content/card-reactor-drone.md`, `content/card-daisysynth.md`, `content/contact.md`

**Interfaces:**
- Consumes: the `BLOCKS` ids from Task 2.
- Produces: five markers in `site/index.html` matching those ids.

- [ ] **Step 1: Write the seed markdown**

```bash
cat > content/intro-heading.md <<'EOF'
# Exploring the intersection of engineering and creativity.
EOF

cat > content/intro-body.md <<'EOF'
Hello, welcome to my digital portfolio, where I post my latest projects.
Currently I am working on:

1. **Reactor Drone** — a game and engine I have been developing for the game
   engines course in my MS. I wanted to use the opportunity to use AI to teach
   myself how to deploy a game and distribute it to multiple players, since most
   of that back-end knowledge is transferable across domains.
2. **DaisySynth** — building my own custom synthesizer / sequencer / music box
   thing on an STM32H7 development board, the Daisy Seed.
3. **Other miscellaneous little projects** — web apps, AI skills, and whatever
   else I get curious about.
EOF

cat > content/card-reactor-drone.md <<'EOF'
### Reactor Drone

A rogue-like wave shooter. My take on a more modern, neon Space Invaders :)
EOF

cat > content/card-daisysynth.md <<'EOF'
### DaisySynth

A custom synthesizer, sequencer, and music box on the Daisy Seed (STM32H7). Page coming soon.
EOF

cat > content/contact.md <<'EOF'
- Email: <conrad@thebrainstormlabs.com>
- GitHub: [github.com/conradmisz](https://github.com/conradmisz)
EOF
```

- [ ] **Step 2: Add the markers to `site/index.html`**

Replace the `#intro` section body so the `<h1>` and the prose each sit between markers, and wrap the prose in a `div.prose` (markdown emits classless `<p>`/`<ol>`, and `max-width` on the wrapper constrains them identically):

```html
  <section id="intro">
    <!--edit:intro-heading-->
    <h1>Exploring the intersection of engineering and creativity.</h1>
    <!--/edit:intro-heading-->
    <div class="prose">
      <!--edit:intro-body-->
      <p>Hello, welcome to my digital portfolio, where I post my latest projects.
        Currently I am working on:</p>
      <ol>
        <li><strong>Reactor Drone</strong> &mdash; a game and engine I have been developing for
          the game engines course in my MS. I wanted to use the opportunity to use AI to teach
          myself how to deploy a game and distribute it to multiple players, since most of that
          back-end knowledge is transferable across domains.</li>
        <li><strong>DaisySynth</strong> &mdash; building my own custom synthesizer / sequencer /
          music box thing on an STM32H7 development board, the Daisy Seed.</li>
        <li><strong>Other miscellaneous little projects</strong> &mdash; web apps, AI skills, and
          whatever else I get curious about.</li>
      </ol>
      <!--/edit:intro-body-->
    </div>
  </section>
```

In the project grid, put the markers immediately inside each `.card-body` (no wrapper — `.card-body h3` and `.card-body p` already work as descendant selectors):

```html
        <div class="card-body">
          <!--edit:card-reactor-drone-->
          <h3>Reactor Drone</h3>
          <p>A rogue-like wave shooter. My take on a more modern, neon Space Invaders :)</p>
          <!--/edit:card-reactor-drone-->
        </div>
```

```html
        <div class="card-body">
          <!--edit:card-daisysynth-->
          <h3>DaisySynth</h3>
          <p>A custom synthesizer, sequencer, and music box on the Daisy Seed (STM32H7). Page coming soon.</p>
          <!--/edit:card-daisysynth-->
        </div>
```

In `#contact`, turn `<ul class="contact-list">` into a wrapper div, because markdown emits a bare `<ul>`:

```html
  <section id="contact">
    <h2>Contact</h2>
    <div class="contact-list">
      <!--edit:contact-->
      <ul>
        <li>Email: <a href="mailto:conrad@thebrainstormlabs.com">conrad@thebrainstormlabs.com</a></li>
        <li>GitHub: <a href="https://github.com/conradmisz">github.com/conradmisz</a></li>
      </ul>
      <!--/edit:contact-->
    </div>
  </section>
```

- [ ] **Step 3: Fix the contact-list CSS**

In `site/style.css`, change the rule at line 184 so it targets the list inside the wrapper:

```css
.contact-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
```

`.contact-list li` at line 190 is already a descendant selector and needs no change.

- [ ] **Step 4: Verify nothing moved**

```bash
python3 tools/editor/serve.py
```

Expected: the five home-page boxes now show the seeded markdown, and each right-hand preview matches the wording on the live page. Open `http://127.0.0.1:8765/preview/` and compare against https://thebrainstormlabs.com — headline size, intro width (~65ch), numbered list, both cards, and the unbulleted contact list must all look unchanged. Ctrl-C when done.

- [ ] **Step 5: Commit**

```bash
git add site/index.html site/style.css content
git commit -m "refactor(site): move home page prose into content/ behind edit markers"
```

---

### Task 4: Migrate the Reactor Drone page

**Files:**
- Modify: `site/reactor-drone/index.html`
- Modify: `site/style.css:282-284`
- Create: `content/rd-description.md`, `content/rd-mac-note.md`, `content/rd-download-footnote.md`, `content/rd-mailing-list.md`, `content/rd-how-to-play.md`, `content/rd-installing.md`, `content/rd-requirements.md`

**Interfaces:**
- Consumes: the `BLOCKS` ids from Task 2.
- Produces: seven markers in `site/reactor-drone/index.html` matching those ids.

- [ ] **Step 1: Write the seed markdown**

```bash
cat > content/rd-description.md <<'EOF'
A top-down neon arena survival shooter built in C++17 and SDL3 on a hand-rolled
ECS engine. You fly a maintenance drone inside a reactor, mouse-aiming against
ring-spawned waves, banking credits from loot and spending them between waves on
permanent upgrades. A 50-wave run spans nine arenas across four themes — Core,
Foundry, Bio-lab, and Prism — ending in Singularity, a black-hole map the final
boss transforms the arena into. Bosses appear every 10 waves, themed per arena;
killing one grants a choice of three active abilities. Two difficulties are
available.
EOF

cat > content/rd-mac-note.md <<'EOF'
macOS will refuse to open this the first time, saying "Apple could not verify
'ReactorDrone' is free of malware." That is not a warning about the game — Apple
charges $99/yr for the developer certificate that suppresses it, and this build
does not have one.

To open it:

1. Click **Done** on the warning. Do not click Move to Trash.
2. Open **System Settings** → **Privacy & Security**.
3. Scroll down to the line saying ReactorDrone was blocked, and click **Open Anyway**.
4. Confirm when prompted. The game opens, and you only do this once.

Prefer the terminal? Run `xattr -dr com.apple.quarantine ReactorDrone.app`
instead. Right-click → Open no longer works on macOS Sequoia and later.
EOF

cat > content/rd-download-footnote.md <<'EOF'
All three builds are early prototypes. The macOS bundle is not notarized — see
Installing below. A portable Windows zip is also on the
[release page](https://github.com/conradmisz/reactor-drone/releases/tag/v2.2.0).
Intel Macs are not supported.
EOF

cat > content/rd-mailing-list.md <<'EOF'
One mail per release, so you know when there is a new build to grab. Nothing
else, and every mail carries an unsubscribe link.
EOF

cat > content/rd-how-to-play.md <<'EOF'
Each run spawns waves of enemies in rings around the arena. Between waves an
upgrade panel opens, with a full shop appearing every fifth wave, covering eight
upgrade lines: hull, shields, thrusters, fire rate, damage, extra shots,
projectile range, and ricochet. Score accumulates across runs and unlocks new
ships. Runs can be saved from the pause menu.
EOF

cat > content/rd-installing.md <<'EOF'
- **Windows** — run the installer. It is unsigned, so SmartScreen may warn you:
  click "More info", then "Run anyway". Installs to Program Files with a
  Start-menu shortcut; uninstall from Settings → Apps.
- **macOS** — unzip and drag ReactorDrone.app to Applications. It is not
  notarized, so the first launch is blocked. Click **Done** on the warning, then
  open **System Settings → Privacy & Security**, scroll down, and click
  **Open Anyway**. Right-click → Open no longer works on macOS Sequoia and later.
- **Linux** — extract the tarball and run `./run.sh`.
EOF

cat > content/rd-requirements.md <<'EOF'
- Windows 10/11, 64-bit
- macOS 12 or later, Apple silicon
- Linux, x86-64, glibc 2.35 or later
- Any modern GPU
- ~60 MB disk space
- Keyboard and mouse
EOF
```

- [ ] **Step 2: Add the markers**

Hero description — wrap in `div.prose`, leave the `<h1>` and `.subtitle` alone (they are not editable):

```html
    <div class="prose">
      <!--edit:rd-description-->
      <p>A top-down neon arena survival shooter built in C++17 and SDL3 ... Two difficulties are available.</p>
      <!--/edit:rd-description-->
    </div>
```

Keep the existing description text exactly as it is between those markers; only the wrapper and markers are new.

Mac note — markers go inside `.download-note`, directly after the hand-written title. No wrapper, so the existing `.download-note > :last-child` rule keeps working:

```html
    <div class="download-note">
      <strong class="download-note-title">Attention Mac users</strong>
      <!--edit:rd-mac-note-->
      ...the existing <p>, <p>, <ol>, <p class="download-note-alt"> unchanged...
      <!--/edit:rd-mac-note-->
    </div>
```

Download footnote, mailing-list copy, how-to-play copy, installing list, requirements list — each gets the same treatment as the hero: replace `<p class="prose">` / `<ul class="prose">` with a `<div class="prose">` wrapper holding the markers and the existing element inside. For example:

```html
    <div class="prose">
      <!--edit:rd-requirements-->
      <ul>
        <li>Windows 10/11, 64-bit</li>
        <li>macOS 12 or later, Apple silicon</li>
        <li>Linux, x86-64, glibc 2.35 or later</li>
        <li>Any modern GPU</li>
        <li>~60 MB disk space</li>
        <li>Keyboard and mouse</li>
      </ul>
      <!--/edit:rd-requirements-->
    </div>
```

Do not touch the download button list, the screenshot grid, the controls table, the signup form, or any `<h1>`/`<h2>`.

- [ ] **Step 3: Fix the download-note-alt CSS**

The last paragraph of the Mac note loses its `download-note-alt` class once markdown renders it. In `site/style.css`, replace the rule at line 282:

```css
.download-note p:last-of-type {
  color: var(--muted);
}
```

Also drop `class="download-note-alt"` from that paragraph in the HTML so the two states match before and after the first publish.

- [ ] **Step 4: Verify nothing moved**

```bash
python3 tools/editor/serve.py
```

Expected: all twelve boxes are populated. Open `http://127.0.0.1:8765/preview/reactor-drone/` and compare against https://thebrainstormlabs.com/reactor-drone/ — the red Mac callout (title, two paragraphs, numbered steps, muted last line), the download buttons, screenshots, controls table, and the three prose lists must all look unchanged. Ctrl-C when done.

- [ ] **Step 5: Commit**

```bash
git add site/reactor-drone/index.html site/style.css content
git commit -m "refactor(site): move Reactor Drone prose into content/ behind edit markers"
```

---

### Task 5: Save on publish (no git, no deploy yet)

**Files:**
- Modify: `tools/editor/serve.py`
- Modify: `tools/editor/editor.html`

**Interfaces:**
- Consumes: `inject()`, `BLOCKS`, `CONTENT`, `SITE`.
- Produces: `save(payload: dict) -> list[str]` where payload is `{block_id: {"md": str, "html": str}}`; returns a list of log lines. Raises `ValueError` if a block id is unknown or a marker is broken — and writes nothing in that case. `POST /publish` returns `text/plain` with the log.

- [ ] **Step 1: Add `save()` and the POST handler to `serve.py`**

Add above the `Handler` class:

```python
def save(payload: dict) -> list[str]:
    """Write every block's markdown and inject its html. All or nothing."""
    unknown = set(payload) - set(BLOCKS)
    if unknown:
        raise ValueError(f"unknown block ids: {', '.join(sorted(unknown))}")

    # Render every page first so a broken marker fails before anything is written.
    pages = {}
    for block_id, data in payload.items():
        page = BLOCKS[block_id][0]
        html = pages.get(page) or (SITE / page).read_text()
        pages[page] = inject(html, block_id, data["html"])

    CONTENT.mkdir(exist_ok=True)
    log = []
    for block_id, data in payload.items():
        (CONTENT / f"{block_id}.md").write_text(data["md"].rstrip() + "\n")
    for page, html in pages.items():
        (SITE / page).write_text(html)
        log.append(f"wrote site/{page}")
    log.append(f"wrote {len(payload)} markdown files")
    return log
```

Add to `Handler`:

```python
    def do_POST(self):
        if self.path != "/publish":
            self._send(404, "not found")
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            log = save(payload)
        except (ValueError, KeyError) as e:
            self._send(400, f"NOT PUBLISHED\n{e}")
            return
        self._send(200, "\n".join(log))
```

- [ ] **Step 2: Wire the Publish button**

Add to the bottom of the `<script>` in `tools/editor/editor.html`:

```js
const log = document.getElementById('log');
const btn = document.getElementById('publish');
btn.addEventListener('click', async () => {
  const payload = {};
  for (const [id, md] of Object.entries(state)) payload[id] = { md, html: render(md) };
  btn.disabled = true;
  log.style.display = 'block';
  log.textContent = 'publishing…';
  try {
    const r = await fetch('/publish', { method: 'POST', body: JSON.stringify(payload) });
    log.textContent = await r.text();
    if (r.ok) document.querySelectorAll('.dirty').forEach(el => el.classList.remove('dirty'));
  } catch (e) {
    log.textContent = 'request failed: ' + e;
  }
  btn.disabled = false;
});
```

- [ ] **Step 3: Publish once and read the diff**

```bash
python3 tools/editor/serve.py   # click Publish without editing anything, then Ctrl-C
git diff --stat
git diff site/
```

Expected: `wrote site/index.html`, `wrote site/reactor-drone/index.html`, `wrote 12 markdown files` in the log. The diff touches only text between markers. Entity changes (`&mdash;` → `—`, `&ldquo;` → `"`, `&rarr;` → `→`) and re-wrapped lines are expected. Anything outside a marker pair is a bug — stop and fix `inject` or the markers.

- [ ] **Step 4: Confirm it still renders**

```bash
python3 tools/editor/serve.py
```

Check both pages under `/preview/`. They must look the same as in Tasks 3 and 4. Ctrl-C.

- [ ] **Step 5: Verify a broken marker is refused**

```bash
git stash list >/dev/null
python3 - <<'EOF'
import sys; sys.path.insert(0, "tools/editor")
import serve
try:
    serve.save({"not-a-block": {"md": "x", "html": "<p>x</p>"}})
except ValueError as e:
    print("refused:", e)
else:
    raise SystemExit("FAIL: unknown block id was accepted")
EOF
```

Expected: `refused: unknown block ids: not-a-block`

- [ ] **Step 6: Commit**

```bash
git add tools/editor/serve.py tools/editor/editor.html content site
git commit -m "feat(editor): publish writes markdown and injects rendered html"
```

---

### Task 6: Commit, push, deploy — with live progress

The publish button must tell Conrad what is happening while it happens: that files were
written, that the change is being pushed to GitHub, that it is deploying, and finally that
the change is actually live on thebrainstormlabs.com. A single lump of log at the end is
not acceptable — the run takes 30-120 seconds and a silent page reads as a hang.

**Files:**
- Modify: `tools/editor/serve.py`
- Modify: `tools/editor/editor.html`
- Modify: `tools/editor/test_inject.py`

**Interfaces:**
- Consumes: `save()`.
- Produces: `run(cmd: list[str]) -> tuple[int, str]`; `wait_until_live(timeout: int = 120) -> bool`;
  `publish(payload: dict)` — a GENERATOR yielding log lines as each step completes.
  `POST /publish` streams those lines to the browser as they are produced.

- [ ] **Step 1: Add `run()`, `wait_until_live()` and the `publish()` generator to `serve.py`**

Add `import hashlib`, `import subprocess`, `import time`, `import urllib.request` at the top,
then below `save()`:

```python
LIVE_URL = "https://thebrainstormlabs.com/"


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def wait_until_live(timeout: int = 120) -> bool:
    """Poll the live site until it serves the index.html we just wrote."""
    want = hashlib.sha256((SITE / "index.html").read_bytes()).hexdigest()
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            req = urllib.request.Request(
                f"{LIVE_URL}?_={attempt}", headers={"Cache-Control": "no-cache"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                if hashlib.sha256(r.read()).hexdigest() == want:
                    return True
        except OSError:
            pass  # site briefly 5xx-ing mid-deploy is normal; keep polling
        time.sleep(3)
    return False


def publish(payload: dict):
    """Save, commit, push, deploy, verify. Yields progress lines as it goes."""
    yield "Saving files…"
    for line in save(payload):
        yield f"  {line}"

    code, out = run(["git", "add", "-A", "content", "site"])
    if code:
        yield f"  git add failed: {out}"
        yield "FAILED — nothing was committed or deployed"
        return

    if run(["git", "diff", "--cached", "--quiet"])[0] == 0:
        yield "Nothing to commit — the copy is unchanged. Deploying anyway."
    else:
        yield "Committing…"
        code, out = run(["git", "commit", "-m", "content: update site copy"])
        yield f"  {out}"
        if code:
            yield "FAILED — commit failed, nothing deployed"
            return
        yield "Pushing to GitHub…"
        code, out = run(["git", "push"])
        if code:
            yield f"  push failed: {out}"
            yield "  deploying anyway — push by hand later"
        else:
            yield "  pushed to github.com/conradmisz/brainstormlabs"

    yield "Deploying to Cloudflare Pages… (this is the slow bit)"
    code, out = run(["npx", "wrangler", "pages", "deploy", "site/",
                     "--project-name", "brainstormlabs"])
    yield f"  {out}"
    if code:
        yield "FAILED — the deploy did not succeed; the commit is still in place"
        return

    yield "Waiting for the change to go live…"
    if wait_until_live():
        yield f"LIVE — {LIVE_URL} is serving your changes now."
    else:
        yield (f"Deployed, but {LIVE_URL} still served the old page after 2 minutes. "
               "That is usually CDN caching — check it again shortly.")
```

Note `wait_until_live` fingerprints `site/index.html` only. That is deliberate: it is the
page every deploy touches, and hashing the served bytes against the local file is an exact
check with no parsing. A publish that changes only the Reactor Drone page still reports LIVE
once the home page's bytes match, which is the right answer — the deploy is atomic.

- [ ] **Step 2: Stream the log from `do_POST`**

Replace the body of `do_POST` after the payload parse:

```python
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for line in publish(payload):
                self.wfile.write((line + "\n").encode())
                self.wfile.flush()
        except (ValueError, KeyError) as e:
            self.wfile.write(f"NOT PUBLISHED\n{e}\n".encode())
```

The response has no `Content-Length` and the server speaks HTTP/1.0, so the browser sees the
body end when the connection closes. Because the headers go out before the work starts, the
status is always 200: **the client must read the sentinels in the text**, not the status code.
`LIVE —` means live, `FAILED` means it stopped, `NOT PUBLISHED` means nothing was written.

- [ ] **Step 3: Render the stream as it arrives**

In `editor.html`, replace the fetch inside the Publish handler with a streaming read:

```js
    const r = await fetch('/publish', { method: 'POST', body: JSON.stringify(payload) });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let all = '';
    log.textContent = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      all += dec.decode(value, { stream: true });
      log.textContent = all;
      log.scrollTop = log.scrollHeight;
    }
    if (all.includes('LIVE —')) document.querySelectorAll('.dirty').forEach(el => el.classList.remove('dirty'));
```

Keep the existing `btn.disabled` handling so the button is disabled during the run and
re-enabled afterwards, on both the success and the failure path.

- [ ] **Step 4: Write the failing test for the progress sequence**

Add to `tools/editor/test_inject.py`, following that file's plain-assert style. It must not
touch the network, git, or the real files — it stubs `save`, `run`, and `wait_until_live`:

```python
def _drive_publish(run_results, live=True, saved=("wrote site/index.html",)):
    """Run publish() with save/run/wait_until_live stubbed. Returns the yielded lines."""
    calls = []
    real = (serve.save, serve.run, serve.wait_until_live)
    serve.save = lambda payload: list(saved)
    serve.run = lambda cmd: (calls.append(cmd), run_results.pop(0))[1]
    serve.wait_until_live = lambda *a, **k: live
    try:
        return list(serve.publish({"intro-heading": {"md": "x", "html": "<h1>x</h1>"}})), calls
    finally:
        serve.save, serve.run, serve.wait_until_live = real


def test_publish_reports_each_phase_then_live():
    lines, calls = _drive_publish([
        (0, ""),            # git add
        (1, ""),            # git diff --cached --quiet -> there are changes
        (0, "[site-editor abc1234] content: update site copy"),  # git commit
        (0, ""),            # git push
        (0, "Deployment complete! https://abc.brainstormlabs.pages.dev"),  # wrangler
    ])
    text = "\n".join(lines)
    assert "Saving files" in text
    assert "Pushing to GitHub" in text
    assert "pushed to github.com/conradmisz/brainstormlabs" in text
    assert "Deploying to Cloudflare Pages" in text
    assert "LIVE —" in text
    assert lines.index("Pushing to GitHub…") < lines.index("Deploying to Cloudflare Pages… (this is the slow bit)")
    assert calls[-1][:4] == ["npx", "wrangler", "pages", "deploy"]


def test_publish_stops_before_deploy_when_commit_fails():
    lines, calls = _drive_publish([
        (0, ""),                       # git add
        (1, ""),                       # there are changes
        (1, "nothing to commit, working tree clean"),  # git commit fails
    ])
    text = "\n".join(lines)
    assert "FAILED" in text
    assert "Deploying to Cloudflare Pages" not in text
    assert not any(c[0] == "npx" for c in calls)


def test_publish_says_not_live_when_the_site_never_updates():
    lines, _ = _drive_publish([
        (0, ""), (1, ""), (0, "committed"), (0, ""), (0, "Deployment complete!"),
    ], live=False)
    text = "\n".join(lines)
    assert "LIVE —" not in text
    assert "still served the old page" in text
```

- [ ] **Step 5: Run the tests**

Run: `python3 tools/editor/test_inject.py`
Expected: every test passes, including the three new ones, output pristine.

- [ ] **Step 6: Check the real tooling is reachable without deploying**

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, "tools/editor")
import serve
print(serve.run(["git", "status", "--porcelain"]))
print(serve.run(["npx", "wrangler", "--version"]))
EOF
```

Expected: a `(0, ...)` tuple from each. If `npx wrangler --version` fails, stop and report —
the deploy step cannot work and that needs sorting before a live publish.

- [ ] **Step 7: Commit**

```bash
git add tools/editor/serve.py tools/editor/editor.html tools/editor/test_inject.py
git commit -m "feat(editor): stream publish progress and confirm the change is live"
```

---

### Task 7: First live publish and documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `content/*.md` (whatever copy Conrad actually wants to change)

- [ ] **Step 1: Document the tool**

Add to `CLAUDE.md` under the existing bullet list:

```markdown
- Edit copy: `python3 tools/editor/serve.py` — markdown editor at localhost:8765 for every
  prose block on the site; Publish writes `content/*.md`, injects the rendered html between
  the `<!--edit:ID-->` markers in the two pages, commits, pushes, and deploys.
  Adding a block = add a marker pair to the html and an entry to `BLOCKS` in `serve.py`.
- Prose lives in `content/*.md`. The html between edit markers is generated — edit the
  markdown, not the html.
```

- [ ] **Step 2: Commit the docs**

```bash
git add CLAUDE.md
git commit -m "docs: how to edit site copy"
```

- [ ] **Step 3: Make one real edit and publish it**

Start the editor, change something small and visible (a word in the home intro), click Publish, and read the log to the end.

Expected: `wrote site/index.html`, a commit line, a push line, then wrangler's deployment URL.

- [ ] **Step 4: Confirm it is live**

```bash
curl -s https://thebrainstormlabs.com/ | grep -c "<the changed word>"
git status --porcelain    # expect empty
git log --oneline -3
```

Expected: the grep finds the new word (allow a few seconds for the deploy to propagate), the working tree is clean, and the content commit is at the top.

- [ ] **Step 5: Run the test suite once more**

Run: `python3 tools/editor/test_inject.py`
Expected: `all passed`

---

## Notes for the implementer

- The log is returned in one response when publishing finishes, not streamed line by line. A spinner-free 15-second wait is the cost; streaming would mean chunked responses and a reader loop in the client for no real gain.
- If a publish ever reports `NOT PUBLISHED`, no file was written — the render pass in `save()` runs before any write.
- Recovering from a bad publish is `git revert` plus another publish; there is no undo in the tool.
