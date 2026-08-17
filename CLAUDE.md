# Brainstorm Labs — personal site

Static portfolio site for thebrainstormlabs.com. Two pages, one stylesheet, zero JS,
no build step. Also the distribution page for Reactor Drone (game repos live in
`~/Documents/GameEngines/reactor-drone-v2-*`).

- `site/index.html` — home: intro, download banner, project grid, contact
- `site/reactor-drone/index.html` — game page; download button is "coming soon" until
  the installer is tested and uploaded to R2 (swap one href to activate)
- Deploy: `wrangler pages deploy site/` (Cloudflare Pages project `brainstormlabs`)
- Preview locally: `python3 -m http.server -d site`
- Edit copy: `python3 tools/editor/serve.py` — markdown editor at localhost:8765
  for every prose block. Publish: writes `content/*.md`, injects rendered html
  between `<!--edit:ID-->` markers, commits, pushes, deploys, streams progress,
  and confirms when the live site has the new bytes.
  Adding a block = add marker pair + `BLOCKS` entry in `serve.py`.
- Prose lives in `content/*.md`. The html between edit markers is generated —
  edit the markdown, not the html.

Design rules: near-white bg, near-black text, ONE accent color, system-ui/Inter type,
~65ch prose, flat + bordered, no gradients/glass/shadow soup. Keep it minimal.
