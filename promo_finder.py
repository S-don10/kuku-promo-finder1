"""Promo finder for microdrama screenplays.
Stage 1 (code, free): parse screenplay -> events -> enumerate 20-60s windows -> score with transparent rules.
Stage 2 (optional LLM, swappable via env vars): re-rank shortlist + write hook/cliffhanger/why lines.
Usage: python promo_finder.py <screenplay_dir> [--out outputs] [--top 2] [--llm]
"""
import re, os, sys, json, csv, glob, argparse

TS = r"(\d+):(\d+\.\d+)"
def sec(m, s): return int(m) * 60 + float(s)
def fmt(t): return f"{int(t//60):02d}:{t%60:05.2f}"

def parse(path):
    txt = open(path, encoding="utf-8").read()
    ep = int(re.search(r"EPISODE NUMBER:\s*Episode (\d+)", txt).group(1))
    logline = (re.search(r"EPISODE LOGLINE:\s*(.*)", txt) or [None, ""])[1]
    events = []
    for m in re.finditer(r"\*\*([^*\n]+?):\*\*\s*\nStart: \(" + TS + r"\) \| End: \(" + TS + r"\)\s*\n(.*?)(?=\n\*\*|\n\nSCENE|\n--- SCRIPT END|\Z)", txt, re.S):
        label, a1, a2, b1, b2, body = m.groups()
        kind = label.split(" (")[0].strip()
        t = "cam" if kind == "CAMERA" else "act" if kind == "ACTION" else "sfx" if kind == "SOUND FX" else "dlg"
        events.append(dict(type=t, who=kind, tone=(re.search(r"\((.*)\)", label) or [None, ""])[1],
                           s=sec(a1, a2), e=sec(b1, b2), text=body.strip()))
    events.sort(key=lambda x: (x["s"], x["e"]))
    end = max(e["e"] for e in events)
    return dict(ep=ep, logline=logline, events=events, end=end, file=os.path.basename(path))

HOOK_WORDS = r"slap|struck|strike|blood|knife|sword|dagger|poison|arsenic|dead|death|kill|murder|pregnan|traitor|liar|lie|secret|truth|marry|marriage|proposal|kneel|knee|betray|scream|gasp|shock|stunned|gasps|reveal|duke|duchess|scar|bastard|guard|seize|whip|punish|divorce|forgive|forbid|never|how dare|get out|you will pay"
CLIFF_WORDS = r"cliffhanger|ominous|sting|stinger|cut to black|freeze|tension|swell|drone|gasp"
EMO = r"shock|furious|cold|threat|menac|defiant|stun|panic|fear|rage|gasp|disbelie|command|venom|trembl"

def score_window(evs, ep_end, s, e):
    w = [x for x in evs if x["s"] >= s - 0.01 and x["e"] <= e + 0.01]
    first = [x for x in w if x["s"] < s + 3]
    ftxt = " ".join(x["text"] for x in first).lower()
    hook = 0
    hook += min(3, len(re.findall(HOOK_WORDS, ftxt)))
    hook += 1.5 if any(x["type"] == "dlg" and x["s"] < s + 2 for x in first) else 0   # speech starts immediately
    hook += 1 if any(re.search(EMO, x["tone"].lower()) for x in first) else 0
    hook += 0.7 if "!" in ftxt or "?" in ftxt else 0
    last = [x for x in w if x["e"] > e - 6]
    ltxt = " ".join(x["text"] for x in last).lower()
    cliff = 0
    cliff += 3 if e >= ep_end - 1.0 else (1.5 if e >= ep_end - 8 else 0)             # ends at episode end = built-in cliffhanger
    cliff += 1.5 if re.search(CLIFF_WORDS, ltxt) else 0
    cliff += 1 if any(x["type"] == "dlg" and x["text"].rstrip('"').endswith(("?", "...", "—", "-")) for x in last) else 0
    cliff -= 2 if any("resolv" in x["text"].lower() or "embrace" in x["text"].lower() for x in last) else 0
    speakers = {x["who"] for x in w if x["type"] == "dlg"}
    dlg_n = sum(1 for x in w if x["type"] == "dlg")
    stand = 1.5 if 1 <= len(speakers) <= 3 else 0
    stand += 1 if dlg_n >= 4 else -1.5 if dlg_n < 2 else 0
    stand -= 1 if s < 4 and False else 0
    dur = e - s
    length = 0.5 if 30 <= dur <= 50 else 0
    total = 1.2 * hook + 1.2 * cliff + stand + length
    return dict(total=round(total, 2), hook=round(hook, 2), cliff=round(cliff, 2), standalone=round(stand, 2), dur=round(dur, 1)), w

def candidates(ep, top=2):
    evs = [x for x in ep["events"] if x["type"] != "cam"]  # cam events only used for bounds below
    starts = sorted({x["s"] for x in evs if x["type"] in ("dlg", "act")})
    ends = sorted({x["e"] for x in evs} | {ep["end"]})
    cands = []
    for s in starts:
        for e in ends:
            if 20 <= e - s <= 60:
                sc, w = score_window(ep["events"], ep["end"], s, e)
                cands.append((sc["total"], s, e, sc))
    cands.sort(reverse=True)
    chosen = []
    for tot, s, e, sc in cands:
        if all(e <= c["s"] or s >= c["e"] for c in chosen):
            chosen.append(dict(ep=ep["ep"], s=s, e=e, score=sc))
        if len(chosen) == top: break
    return chosen

def describe(ep, c):
    w = [x for x in ep["events"] if x["s"] >= c["s"] - .01 and x["e"] <= c["e"] + .01]
    d = [x for x in w if x["type"] == "dlg"]
    first = next((x for x in d if x["s"] < c["s"] + 5), None) or next((x for x in w if x["type"] == "act"), w[0])
    last = [x for x in w if x["type"] in ("dlg", "act")][-1]
    c["hook"] = (f'{first["who"].title()}: {first["text"]}' if first["type"] == "dlg" else first["text"])[:220]
    c["cliffhanger"] = (f'{last["who"].title()}: {last["text"]}' if last["type"] == "dlg" else last["text"])[:220]
    c["segments"] = [{"episode": ep["ep"], "start": fmt(c["s"]), "end": fmt(c["e"])}]
    c["why"] = f'Rule score {c["score"]["total"]} (hook {c["score"]["hook"]}, cliffhanger {c["score"]["cliff"]}, standalone {c["score"]["standalone"]}); episode context: {ep["logline"][:140]}'
    return c

def llm_rerank(items, eps):
    """Optional stage 2. Any OpenAI-compatible endpoint: set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL. Swap model = change env var."""
    import urllib.request
    base, key, model = os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"], os.environ.get("LLM_MODEL", "gpt-4o-mini")
    for it in items:
        ep = eps[it["ep"]]
        w = [x for x in ep["events"] if x["s"] >= it["s"] - .01 and x["e"] <= it["e"] + .01]
        script = "\n".join(f'[{fmt(x["s"])}] {x["who"]}: {x["text"]}' for x in w)
        prompt = ("You pick promo clips for vertical microdrama. Given this 20-60s excerpt, return JSON "
                  '{"hook":str,"cliffhanger":str,"why":str,"standalone_1to5":int,"hook_1to5":int,"cliff_1to5":int}.\n\n' + script)
        req = urllib.request.Request(base.rstrip("/") + "/chat/completions", method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}).encode())
        r = json.loads(json.loads(urllib.request.urlopen(req).read())["choices"][0]["message"]["content"])
        it.update(hook=r["hook"], cliffhanger=r["cliffhanger"], why=r["why"])
        it["score"]["total"] = round(it["score"]["total"] + r["hook_1to5"] + r["cliff_1to5"] + r["standalone_1to5"], 2)
    return items

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--out", default="outputs")
    ap.add_argument("--top", type=int, default=2); ap.add_argument("--llm", action="store_true")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    eps = {}
    for f in sorted(glob.glob(os.path.join(a.dir, "episode-*.txt"))):
        e = parse(f); eps[e["ep"]] = e
    items = []
    for n, e in eps.items():
        for c in candidates(e, a.top): items.append(describe(e, c))
    if a.llm: items = llm_rerank(items, eps)
    items.sort(key=lambda x: -x["score"]["total"])
    for i, it in enumerate(items, 1): it["rank"] = i
    json.dump(items, open(f"{a.out}/promos.json", "w"), indent=1)
    with open(f"{a.out}/promos.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["rank", "episode", "segments", "duration_s", "score", "hook", "cliffhanger", "why"])
        for it in items: w.writerow([it["rank"], it["ep"], "; ".join(f'Ep{s["episode"]} {s["start"]}-{s["end"]}' for s in it["segments"]), it["score"]["dur"], it["score"]["total"], it["hook"], it["cliffhanger"], it["why"]])
    with open(f"{a.out}/promos.md", "w") as f:
        f.write("# Ranked promos\n\n")
        for it in items:
            s = it["segments"][0]
            f.write(f'**#{it["rank"]} Ep {s["episode"]} {s["start"]}-{s["end"]}** ({it["score"]["dur"]}s, score {it["score"]["total"]})  \nHook: {it["hook"]}  \nCliffhanger: {it["cliffhanger"]}  \nWhy: {it["why"]}\n\n')
    print(f"{len(eps)} episodes, {len(items)} promos -> {a.out}/")
if __name__ == "__main__": main()
