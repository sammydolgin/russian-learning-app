# Russian Learning App — Project Guide

## How to Work With Me

**No assumptions.** If something is ambiguous, ask before building. A wrong assumption costs more time than a clarifying question.

**Interview style.** When requirements are unclear, ask focused questions one cluster at a time — not a wall of questions at once. Keep asking until there's no remaining ambiguity that could send the build in the wrong direction.

**Challenge oversights.** If a request seems incomplete, contradictory, or likely to cause a problem downstream, say so directly rather than just doing what was asked. The goal is the right outcome, not just compliance.

**Push back on bad ideas.** If a feature request or design choice seems counterproductive to building a good language learning app — even if it sounds appealing on the surface — say so clearly before building it. Explain why, then ask if the user still wants to proceed. Don't just implement something that will hurt learning outcomes.

**Confirm before major decisions.** Architecture choices, data model changes, or anything that would take significant time to undo — confirm first.

---

## Project Overview

A standalone Python/Streamlit Russian vocabulary learning app. No Claude API in the runtime — pure Python logic.

**Tech stack:** Python, Streamlit, SQLite (via stdlib `sqlite3`), rapidfuzz for fuzzy answer matching.
**Deployment:** Runs locally or on Render.

### Phase Progression (in order)

Content is organized into three CEFR levels, each split into many "parts." Within each part there are three phase types presented to the learner: **Words**, **Phrases (Ru→En)**, and **Phrases (En→Ru, reverse)**.

1. **Alphabet** — 33 letters in 6 groups (~5–6 letters each)
2. **A0** — ~200 words across 4 parts; phrases + reverse for each part
3. **A1** — ~570 words across 11 parts; phrases + reverse for each part
4. **A2** — ~1,300 words across 26 parts; phrases + reverse for each part

Each part contains ~45–50 word items and ~50 phrase items.

**Graduation criteria (all phases):** 85% all-time accuracy + 50% of phase items answered correctly at least once.

### Quiz mechanics
- 10 items per session
- Russian shown → user types English answer (or English → Russian for reverse phrases)
- Fuzzy match threshold: ~80 (accepts close answers)
- Item statuses: unseen → review (seen once) → mastered (3+ correct)

### Content authoring rules

When creating or extending phrase content for a given part:

- Each phrase must include **at least one word from that part's word list**. This is what makes the phrase reinforce the vocabulary the learner just acquired.
- Phrases may also draw on words from **earlier parts** (same level or earlier levels) to keep the Russian natural. Avoid relying heavily on words from *later* parts the learner hasn't seen yet.
- Aim for ~50 phrases per part, matching the existing pattern.
- Each item has `prompt`, `answer`, and `alt_answers` (list of acceptable English variants — e.g., football/soccer, color/colour). Reverse files typically leave `alt_answers` empty.

---

## File Structure

```
russian/
  app.py                  # Streamlit app (all views)
  db.py                   # SQLite init + all CRUD; loads content files on first run
  requirements.txt
  CLAUDE.md
  data/
    content/
      alphabet.json                              # 33 letters in 6 groups
      a0_part{1..4}_words.json                   # A0 vocabulary
      a0_part{1..4}_phrases.json                 # A0 phrases (Ru→En)
      a0_part{1..4}_phrases_reverse.json         # A0 phrases (En→Ru)
      a1_part{1..11}_words.json                  # A1 vocabulary
      a1_part{1..11}_phrases.json                # A1 phrases (Ru→En)
      a1_part{1..11}_phrases_reverse.json        # A1 phrases (En→Ru)
      a2_part{1..26}_words.json                  # A2 vocabulary
      a2_part{1..26}_phrases.json                # A2 phrases (Ru→En)
      a2_part{1..26}_phrases_reverse.json        # A2 phrases (En→Ru)
      *_audio.json, *_audio_reverse.json         # Present on disk but NOT loaded by db.py
                                                  # (audio is not currently a visible phase type)
    russian_learning.db   # Created at runtime — do not commit
```

`db.py` discovers content via filename pattern `{level}_part{N}_{phase_type}.json` where `phase_type ∈ {words, phrases, phrases_reverse}`. New files dropped into `data/content/` matching this pattern are auto-loaded on next run.

---

## Development Notes

- `db.py` owns all database logic. `app.py` calls `db.*` functions only — no raw SQL in the UI layer.
- Content files are source of truth for the word/phrase lists. DB is populated from them on first run.
- Adding new content: drop a new JSON file matching the naming pattern. `_load_new_content` picks it up automatically.
- Updating existing content: editing `answer` / `alt_answers` / `example` in a content file syncs to the DB via `_sync_existing_phase_items` (never removes items, so user progress is preserved).
- If you need a clean reset, delete `russian_learning.db` and rerun.
- User progress lives in the DB, not in content files.
- The `_reverse.json` files are static, not auto-generated. When you add a new forward phrase file, add the matching reverse file as well.
- Audio files (`*_audio.json`) exist on disk for some parts but are not currently surfaced as a visible phase type — see `VISIBLE_PHASE_TYPES` in `db.py:12`.
