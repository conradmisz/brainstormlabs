# Site copy editor — design

2026-08-16

## Problem

Editing the copy on thebrainstormlabs.com means hand-editing prose buried in two
HTML files, then remembering the deploy incantation. Conrad wants one local page
that lays out every editable piece of text as markdown, plus a button that ships it.

## Decisions taken

- **Runs locally only.** No hosting, no auth, no stored API token. It shells out to
  the `wrangler` and `git` credentials already on the machine.
- **Prose blocks in place.** The two HTML files stay the committed, readable source
  of the site's structure. The editor owns only marked prose regions inside them.
- **Publish = save -> commit -> push -> deploy**, one button.

## Architecture

New directory `tools/editor/` in this repo:

| File | Role |
|---|---|
| `serve.py` | stdlib `http.server`; serves the editor, serves `site/` under `/preview/`, handles `POST /publish`. ~80 lines. |
| `editor.html` | one page: a labeled `<textarea>` per block, a live preview pane, a Publish button. |
| `marked.min.js` | vendored markdown renderer (~40 KB). Rendering happens in the browser; the server writes what it is given. |
| `test_inject.py` | assert-based check of the marker injection. |

New directory `content/` at repo root: one `.md` file per editable block, committed.

Run with `python3 tools/editor/serve.py` -> `http://localhost:8765`.

### Data flow

1. On load, `serve.py` returns the contents of every `content/*.md` plus its label.
2. Conrad edits. `marked` renders a live preview client-side.
3. Publish POSTs `{block_id: {md, html}}` for every block.
4. Server writes each `content/<id>.md`, then injects the html between that block's
   markers in the owning HTML file.
5. Server runs `git commit -am "content: update site copy"` (no-op if the tree is
   clean), `git push`, then
   `npx wrangler pages deploy site/ --project-name brainstormlabs`.
6. stdout/stderr of each step streams back into the page. A failed deploy leaves the
   commit in place; Conrad re-runs Publish.

### Markers

Each editable region is delimited in the HTML by:

```html
<!--edit:intro-->
...generated html...
<!--/edit:intro-->
```

Injection is a literal search for the two marker strings and a replacement of the
text between them. Everything outside the markers — banner, nav, download grid,
tables, forms, footer — is untouched by the tool.

`serve.py` holds one mapping `BLOCKS = {id: (file, label)}`. That mapping and the
markers in the HTML are the only coupling between the tool and the site.

## Editable blocks

`site/index.html`

| id | label |
|---|---|
| `intro-heading` | Home / headline |
| `intro-body` | Home / intro paragraph + "currently working on" list |
| `card-reactor-drone` | Home / Reactor Drone card blurb |
| `card-daisysynth` | Home / DaisySynth card blurb |
| `contact` | Home / contact list |

`site/reactor-drone/index.html`

| id | label |
|---|---|
| `rd-description` | Reactor Drone / description |
| `rd-mac-note` | Reactor Drone / Mac warning body |
| `rd-download-footnote` | Reactor Drone / note under the download buttons |
| `rd-mailing-list` | Reactor Drone / "Stay up to date" copy |
| `rd-how-to-play` | Reactor Drone / how to play |
| `rd-installing` | Reactor Drone / installing |
| `rd-requirements` | Reactor Drone / system requirements |

**Not editable, by decision:** the download button grid and its version numbers and
asset filenames, the screenshot grid, the controls table, the signup form, the
banner, nav, headings that name sections, and the hero subtitle. These are structure
or typed values, not prose, and stay hand-edited.

Known gap, accepted: the download hrefs hardcode exact release asset filenames, so a
renamed asset breaks the page silently. The editor does not cover that. Adding three
plain text fields for version + filenames is the follow-up if it becomes annoying.

## CSS migration

Markdown renders plain `<p>`, `<ul>`, `<ol>` with no classes, so a few blocks whose
styling currently hangs off a class on the element itself need the class moved to a
wrapper, or the selector loosened:

- `.prose` (max-width) — wrap the region in `<div class="prose">`; the constraint
  applies to children unchanged. No CSS edit.
- `.contact-list` — wrap in `<div class="contact-list">` and change the rule to
  `.contact-list ul`. `.contact-list li` keeps working as a descendant selector.
- `.card-body h3 / p` — markers sit directly inside `.card-body`. No change.
- `.download-note p / ol / li / > :last-child` — markers sit directly inside
  `.download-note`, after the hand-written title. No wrapper, so `> :last-child`
  keeps working. `.download-note-alt` loses its class; replace that rule with
  `.download-note p:last-of-type`.

**Acceptance for the migration: the first Publish produces no visible change.** The
`content/*.md` files are seeded from the current copy, and `git diff` after the first
publish is reviewed to confirm it is whitespace/entity-level only. Both pages are
eyeballed at `/preview/` before the first real deploy.

Markdown escapes entities differently than the hand-written HTML (`&mdash;` becomes a
literal em dash, `&ldquo;` a literal curly quote). That is a byte-level diff with no
visual effect and is accepted.

## Error handling

- Missing, duplicated, or unclosed marker for a known block id -> the tool refuses to
  write that file and reports which block, before any git or deploy step runs.
- `git commit` with a clean tree -> reported as "nothing to commit", not an error;
  the deploy still runs.
- Non-zero exit from `git push` or `wrangler` -> streamed to the page, publish marked
  failed. Files and commit stay as they are.
- Server binds `127.0.0.1` only.

## Testing

`tools/editor/test_inject.py`, plain asserts, run with `python3`:

- replaces only the text between markers, leaves the rest of the file byte-identical
- is idempotent — injecting the same html twice gives the same result
- raises on a missing marker, an unclosed marker, and a duplicated marker

Nothing else gets a test. The HTTP handlers and the subprocess calls are exercised by
using the thing.

## Out of scope

Hosted/remote editing, auth, image upload, adding or reordering sections, new pages,
markdown for the Reactor Drone page's structural elements, rollback beyond `git revert`.
