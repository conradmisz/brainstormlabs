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
