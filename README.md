# Promo Finder (Kuku AI Generalist Assignment, Problem 1)

Reads microdrama screenplays and finds ranked 20-60s promo windows (episode, start/end timestamps, hook, cliffhanger, reason).

Author: Subhendu Bairagya | Roll 23135130 | Mechanical

## Run (no API key, no installs)
1. Put the screenplay `.txt` files (named `episode-XXX-....txt`) in `screenplays/`. They are Kuku's confidential content, so they are NOT in this repo (see `.gitignore`).
2. Run:
```
python promo_finder.py screenplays --out outputs --top 2
```
Output: `outputs/promos.json`, `promos.csv`, `promos.md` (ranked, best first).

`outputs/` in this repo is the unedited result of running this on all 50 episodes of the provided pack (100 promos).

## Optional: LLM re-rank (swappable model)
Works with any OpenAI-compatible endpoint. Change the model by changing env vars only:
```
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=...
export LLM_MODEL=gpt-4o-mini
python promo_finder.py screenplays --out outputs_llm --llm
```
**Status: this stage is written but NOT tested** (no API key was available while building). Treat it as untested.

## How it works
1. Parse each screenplay into timestamped events (dialogue, action, sound, camera).
2. Enumerate every 20-60s window that starts on a dialogue/action event and ends on an event boundary.
3. Score windows with transparent rules: hook (first 3s), cliffhanger (ending), standalone (few speakers, enough dialogue), small length bonus.
4. Keep best N non-overlapping windows per episode, rank globally.

## Known limits
- Rules only; no ground truth, so scores are not validated against editor picks.
- Calm endings near episode end can be scored as cliffhangers (e.g. Ep 16).
- Very short opening lines ("Ah!") can score as hooks.
- "Why" is a score breakdown plus the episode logline, not a real explanation.
- Parser depends on the current screenplay format (`Start: (mm:ss.xx) | End: (mm:ss.xx)`, bold speaker labels).
- Single-episode promos only; multi-segment promos are supported in the output schema but not generated.
