# Brainstorm Labs — personal site

Static portfolio site for thebrainstormlabs.com. Two pages, one stylesheet, zero JS,
no build step. Also the distribution page for Reactor Drone (game repos live in
`~/Documents/GameEngines/reactor-drone-v2-*`).

- `site/index.html` — home: intro, download banner, project grid, contact
- `site/reactor-drone/index.html` — game page; download button is "coming soon" until
  the installer is tested and uploaded to R2 (swap one href to activate)
- Deploy: `wrangler pages deploy site/` (Cloudflare Pages project `brainstormlabs`)
- Preview locally: `python3 -m http.server -d site`

Design rules: near-white bg, near-black text, ONE accent color, system-ui/Inter type,
~65ch prose, flat + bordered, no gradients/glass/shadow soup. Keep it minimal.
