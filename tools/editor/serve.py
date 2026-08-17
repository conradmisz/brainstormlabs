#!/usr/bin/env python3
"""Local copy editor for the Brainstorm Labs site.

Run:  python3 tools/editor/serve.py
Then: http://127.0.0.1:8765
"""
import hashlib
import http.server
import json
import mimetypes
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
CONTENT = ROOT / "content"
HERE = Path(__file__).resolve().parent
PORT = 8765


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
            "md": md_path.read_text(encoding="utf-8") if md_path.exists() else "",
        }
    return out


def save(payload: dict) -> list[str]:
    """Write every block's markdown and inject its html. All or nothing."""
    unknown = set(payload) - set(BLOCKS)
    if unknown:
        raise ValueError(f"unknown block ids: {', '.join(sorted(unknown))}")

    # Validate/render everything first so a broken block fails before anything is written.
    mds = {block_id: data["md"] for block_id, data in payload.items()}
    pages = {}
    for block_id, data in payload.items():
        page = BLOCKS[block_id][0]
        html = pages.get(page) or (SITE / page).read_text(encoding="utf-8")
        pages[page] = inject(html, block_id, data["html"])

    CONTENT.mkdir(exist_ok=True)
    log = []
    for block_id, md in mds.items():
        (CONTENT / f"{block_id}.md").write_text(md.rstrip() + "\n", encoding="utf-8")
    for page, html in pages.items():
        (SITE / page).write_text(html, encoding="utf-8")
        log.append(f"wrote site/{page}")
    log.append(f"wrote {len(payload)} markdown files")
    return log


LIVE_URL = "https://thebrainstormlabs.com/"
BRANCH = "master"  # the Cloudflare Pages production branch


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def _page_url(page: str) -> str:
    """The live URL for a site/<page> path, e.g. 'reactor-drone/index.html' ->
    '.../reactor-drone/' (not '.../reactor-drone/index.html')."""
    if page.endswith("index.html"):
        page = page[: -len("index.html")]
    return LIVE_URL + page


def wait_until_live(timeout: int = 120) -> bool:
    """Poll the live site until every page in BLOCKS serves what we just wrote."""
    pages = sorted({page for page, _label in BLOCKS.values()})
    want = {page: hashlib.sha256((SITE / page).read_bytes()).hexdigest() for page in pages}
    pending = set(pages)
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline and pending:
        attempt += 1
        for page in list(pending):
            try:
                req = urllib.request.Request(
                    f"{_page_url(page)}?_={attempt}", headers={"Cache-Control": "no-cache"}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    if hashlib.sha256(r.read()).hexdigest() == want[page]:
                        pending.discard(page)
            except OSError:
                pass  # site briefly 5xx-ing mid-deploy is normal; keep polling
        if pending:
            time.sleep(3)
    return not pending


def publish(payload: dict):
    """Save, commit, push, deploy, verify. Yields progress lines as it goes."""
    code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if code or branch != BRANCH:
        yield (f"FAILED — you are on branch '{branch}'. Publishing reaches "
               f"{LIVE_URL} only from '{BRANCH}'. Merge your work into {BRANCH} first, "
               "then publish. Nothing was written.")
        return

    yield "Saving files…"
    for line in save(payload):
        yield f"  {line}"

    code, out = run(["git", "add", "-A", "content", "site"])
    if code:
        yield f"  git add failed: {out}"
        yield "FAILED — nothing was committed or deployed"
        return

    if run(["git", "diff", "--cached", "--quiet", "--", "content", "site"])[0] == 0:
        yield "Nothing to commit — the copy is unchanged. Deploying anyway."
    else:
        yield "Committing…"
        code, out = run(["git", "commit", "-m", "content: update site copy",
                         "--", "content", "site"])
        yield f"  {out}"
        if code:
            yield "FAILED — commit failed, nothing deployed"
            return
        yield "Pushing to GitHub…"
        code, out = run(["git", "push", "-u", "origin", "HEAD"])
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

    def do_POST(self):
        if self.path != "/publish":
            self._send(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise TypeError("request body must be a JSON object")
        except (TypeError, ValueError) as e:
            # Nothing has been written to the client yet, so a normal error
            # response is still possible (and clearer than a stream sentinel).
            self._send(400, f"bad request: {e}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        log_lines = []
        try:
            for line in publish(payload):
                log_lines.append(line)
                self.wfile.write((line + "\n").encode())
                self.wfile.flush()
        except (ValueError, KeyError) as e:
            self.wfile.write(f"NOT PUBLISHED\n{e}\n".encode())
        except Exception as e:
            # subprocess.run can raise OSError/FileNotFoundError if git or
            # wrangler aren't resolvable, plus any other surprise mid-stream.
            # Headers are already sent, so failure has to be a sentinel line.
            self.wfile.write(f"FAILED — unexpected error: {e}\n".encode())
        finally:
            try:
                (HERE / "last-publish.log").write_text(
                    "\n".join(log_lines) + "\n", encoding="utf-8")
            except OSError:
                pass  # a failed log write must not take down the publish itself

    def log_message(self, fmt, *args):
        pass  # ponytail: the page shows what happened; the console does not need to


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}/"
    print(f"editing {ROOT}\nopen {url}")
    webbrowser.open(url)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
