# Playlist

Beat-matched continuous mixes from the Plex libraries, written straight to
bone-conduction swimming headphones. Plane project `PLAY`.

## Shape

- **Runs on Mace** (HP ProDesk, i5-7500T, read-only root) as a Docker Compose
  service deployed by the Mace playbook in `home-servers`. Not AWS: there is no
  CDK, Cognito or Lambda. Authentication is Leia's mTLS client-certificate gate
  on `playlist.home.nakomis.com` and on the MCP endpoint.
- **Deploys are Ansible runs** from `home-servers`, never from CI. CI lints,
  tests and builds the image.
- **Plex is on Leia**; the audio lives on the L&L NAS. Genres and track lists
  come from the Plex API, one section per library. Analyse on Mace, never on
  Leia (its CPU has no SSSE3 and is far too slow).
- **Libraries:** `Music` = CC0 / CC BY from FMA, `Purchased` = bought music.
  A mix may be published (YouTube etc.) only if every track is from `Music`.
  Never weaken that check.
- **No LLM in the core.** Planning is deterministic (Camelot key, BPM, energy).
  The AI request front end (PLAY-9) produces a request the planner consumes; it
  never does the beat-matching.

## The headphones

Guudsoud bone-conduction IP68 MP3 player, 8 GB. Assume no gapless playback
until PLAY-1's test kit says otherwise: cut split files at bar starts in steady
sections, never inside a transition. Bone conduction carries little bass, so
judge transitions on mids and highs. CBR MP3, 192 kbps by default.

## Repository layout

```
backend/   Python (uv, ruff, pytest): analyser, planner, renderer, API, MCP
web/       React + Vite + Tailwind 4 + Biome + Vitest (pnpm)
tools/     headphone-test/ (PLAY-1)
docs/      logo, architecture diagram
```

## Testing

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest` (70% floor)
- `cd web && pnpm lint && pnpm typecheck && pnpm test` (70% floor)

## Architecture diagrams

Source: `docs/architecture/playlist.drawio`, SVG auto-regenerated on commit by
`.githooks/pre-commit`.

To activate the hook after cloning:
```bash
git config core.hooksPath .githooks
```
