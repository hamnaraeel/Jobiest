# career_profile.json

This file is **placeholder data only** — every value is a clearly marked
`YOUR_*` stand-in. Nothing in it is real information about you, and it must
not be treated as a factual career profile.

## How to use it

1. Open `career_profile.json` and replace every `YOUR_*` placeholder with
   your real, verifiable information. Delete the top-level `_comment` key
   (it's documentation, not data).
2. Only set `"verified": true` on a fact once you also add a corresponding
   entry under `"evidence"` linking to it (see below) — verification is not
   just a label, it's a claim that evidence backs it.
3. `"id"` fields inside `experiences[].bullets`, `projects[].results`, and
   `skills[]` are **not** real database ids — they're just local reference
   numbers so `evidence[].links[].entity_id` can point at the right item
   within this same file. On import, the server assigns real ids and remaps
   these links automatically.
4. Import it once your backend is running:

   ```bash
   curl -X POST http://localhost:8000/profile/import \
     -H "Content-Type: application/json" \
     --data @data/career_profile.json
   ```

5. To check what's currently stored, export it back out:

   ```bash
   curl http://localhost:8000/profile/export | python3 -m json.tool
   ```

## Why placeholders instead of an empty file

An empty/absent profile is easy to mistake for "not filled in yet, but the
shape is trustworthy." Explicit `YOUR_*` markers make it unmistakable which
fields are real and which still need your input — the same principle the
whole system is built on: nothing is treated as a verified fact unless a
human (you) put it there and backed it with evidence.
