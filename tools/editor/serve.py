#!/usr/bin/env python3
"""Local copy editor for the Brainstorm Labs site.

Run:  python3 tools/editor/serve.py
Then: http://127.0.0.1:8765
"""
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
