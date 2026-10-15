"""AI HEALTH ASSISTANT — Streamlit edition.
Deterministic analytics (baseline, deviation, similar days, simulator) run in Python;
The AI layer only explains the evidence. Educational project, not medical advice."""
import os, json, sqlite3, hashlib, secrets, datetime as dt, math
import numpy as np, pandas as pd, plotly.graph_objects as go, requests
import streamlit as st, streamlit.components.v1 as components
BASE = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(BASE, "health.db")
try:
    from dotenv import load_dotenv; load_dotenv(os.path.join(BASE, ".env"), override=True)
except Exception:
    pass

MET = {"sleep": ("Sleep", "h"), "activity": ("Activity", "min"), "water": ("Hydration", "ml"), "screen": ("Screen Time", "h"),
       "study": ("Study", "h"), "energy": ("Energy", "/10"), "focus": ("Focus", "/10"), "mood": ("Mood", "/10"), "stress": ("Stress", "/10")}
THRESH = {"sleep": -20, "screen": 35, "activity": -30, "water": -20, "study": 30}  # % deviation vs personal baseline (configurable)
SAFETY = "This is an educational wellness tool, not a medical diagnosis. If symptoms are serious or persistent, please consult a qualified doctor."
URGENT = ["chest pain", "faint", "breathless", "can't breathe", "self-harm", "suicid", "seizure"]

# ---------------- database ----------------
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
def init():
    with db() as c:
        c.executescript("""create table if not exists users(id integer primary key, name text, email text unique, salt text, pw text,
          sleep_target real default 8, water_goal real default 2000, screen_target real default 4);
        create table if not exists logs(user_id int, date text, sleep real, activity real, water real, screen real, study real, breaks int,
          energy int, focus int, mood int, stress int, note text, synthetic int default 0, primary key(user_id, date));
        create table if not exists decisions(user_id int, ts text, question text, result text);""")
def hp(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100000).hex()
def register(name, email, pw, demo=False):
    salt = secrets.token_hex(8)
    with db() as c:
        cur = c.execute("insert into users(name,email,salt,pw) values(?,?,?,?)", (name, email.lower(), salt, hp(pw, salt)))
        uid = cur.lastrowid
    if demo: seed(uid)
    return uid
def login(email, pw):
    with db() as c: u = c.execute("select * from users where email=?", (email.lower(),)).fetchone()
    return dict(u) if u and hp(pw, u["salt"]) == u["pw"] else None
def seed(uid):  # SYNTHETIC demo history with planted patterns
    rng = np.random.default_rng(uid + 7); today = dt.date.today(); rows = []
    for i in range(29, -1, -1):
        sleep = rng.normal(7.2, .5); study = rng.normal(5.5, .9); screen = rng.normal(4.8, .7); act = rng.normal(40, 8); water = rng.normal(1900, 250)
        if rng.random() < .25: sleep -= 1.8; study += 2.2
        if rng.random() < .2: screen += 2.5; act -= 25
        if i == 0: sleep, study, screen, act, water = 5.2, 8.2, 7.1, 15, 1200
        energy = int(np.clip(round(6.5 + (sleep - 7.2) * 1.2 + (act - 40) / 40 - (study - 5.5) * .3 + rng.normal(0, .5)), 1, 10))
        focus = int(np.clip(round(6.8 + (sleep - 7.2) * 1.0 - (screen - 4.8) * .3 + rng.normal(0, .5)), 1, 10))
        if i == 0: energy, focus = 3, 4
        mood = int(np.clip(round(energy * .6 + 3 + rng.normal(0, .6)), 1, 10)); stress = int(np.clip(round(5 - (sleep - 7) * .5 + (study - 5.5) * .4), 1, 10))
        rows.append((uid, str(today - dt.timedelta(days=i)), round(sleep, 1), round(act), round(water), round(screen, 1), round(study, 1),
                     int(max(1, 4 - (study > 7) * 2)), energy, focus, mood, stress, "", 1))
    with db() as c: c.executemany("insert or ignore into logs values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
DEMO_EMAIL = "demo@student.dev"; SCEN = ["Surprise me", "Exam week stress", "Late-night studying", "Balanced routine"]
def rand_rows(uid, sc):  # fresh random SYNTHETIC history each time (used when the AI is unavailable)
    rng = np.random.default_rng(); sc = str(rng.choice(SCEN[1:])) if sc == "Surprise me" else sc
    mu = dict(sleep=7.2, study=5.0, screen=4.8, act=40, water=1900)
    if sc == "Exam week stress": mu.update(sleep=6.4, study=7.5, screen=5.6, act=25, water=1600)
    elif sc == "Late-night studying": mu.update(sleep=5.9, study=7.0, screen=6.2, act=30)
    today = dt.date.today(); rows = []
    for i in range(29, -1, -1):
        sleep = rng.normal(mu["sleep"], .6); study = rng.normal(mu["study"], .9); screen = rng.normal(mu["screen"], .7); act = rng.normal(mu["act"], 9); water = rng.normal(mu["water"], 250)
        if rng.random() < .25: sleep -= 1.6; study += 2
        if i == 0: sleep -= 1.5; study += 2; screen += 2; act *= .4; water -= 500  # today differs from the usual pattern so changes can be demonstrated
        sleep, study, screen, act, water = (float(np.clip(v, a, b)) for v, (a, b) in zip((sleep, study, screen, act, water), ((3.5, 10), (0, 12), (1, 13), (3, 150), (600, 3500))))
        energy = int(np.clip(round(6.5 + (sleep - 7.2) * 1.2 + (act - 40) / 40 - (study - 5.5) * .3 + rng.normal(0, .5)), 1, 10)); focus = int(np.clip(round(6.8 + (sleep - 7.2) - (screen - 4.8) * .3 + rng.normal(0, .5)), 1, 10))
        mood = int(np.clip(round(energy * .6 + 3 + rng.normal(0, .6)), 1, 10)); stress = int(np.clip(round(5 - (sleep - 7) * .5 + (study - 5.5) * .4), 1, 10))
        rows.append((uid, str(today - dt.timedelta(days=i)), round(sleep, 1), int(round(act)), int(round(water)), round(screen, 1), round(study, 1), int(max(1, 4 - (study > 7) * 2)), energy, focus, mood, stress, "", 1))
    return rows
SYSG = ("You create SYNTHETIC demo data for a student wellness app. Invent realistic daily logs for 30 consecutive days (oldest first, last item is today) that match the scenario. "
        "The LAST day must differ noticeably from the earlier average (for example less sleep, more screen time and study, lower energy and focus) so 'what changed' can be shown. "
        "Return STRICT JSON: {\"days\": [30 objects with numeric keys sleep (hours 3-11), activity (minutes 0-180), water (ml 500-4000), screen (hours 1-14), study (hours 0-12), "
        "breaks (0-12), energy (1-10), focus (1-10), mood (1-10), stress (1-10), and a short string note]}.")
def ai_rows(uid, sc):
    d = gem(SYSG, {"scenario": sc, "today": str(dt.date.today())}, "Generate the data", ("days",)); ds = d.get("days") if isinstance(d, dict) else None
    if not isinstance(ds, list) or len(ds) < 30: return None
    cl = lambda v, a, b: float(min(b, max(a, float(v)))); today = dt.date.today(); rows = []
    try:
        for i, x in enumerate(ds[-30:]):
            rows.append((uid, str(today - dt.timedelta(days=29 - i)), round(cl(x["sleep"], 3, 11), 1), int(cl(x["activity"], 0, 180)), int(cl(x["water"], 500, 4000)), round(cl(x["screen"], 1, 14), 1), round(cl(x["study"], 0, 12), 1),
                         int(cl(x["breaks"], 0, 12)), int(cl(x["energy"], 1, 10)), int(cl(x["focus"], 1, 10)), int(cl(x["mood"], 1, 10)), int(cl(x["stress"], 1, 10)), str(x.get("note", ""))[:80], 1))
    except Exception: return None
    return rows
def make_demo(uid, sc="Surprise me"):  # demo account only: AI invents a fresh 30-day history; falls back to a random generator
    rows = ai_rows(uid, sc) or rand_rows(uid, sc)
    with db() as c: c.execute("delete from logs where user_id=?", (uid,)); c.executemany("insert into logs values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
def load(uid):
    with db() as c: df = pd.read_sql("select * from logs where user_id=? order by date", c, params=(uid,))
    if df.empty:  # brand-new user: show zeros (not saved) until the first Daily Log entry
        df = pd.DataFrame([dict(user_id=uid, date=str(dt.date.today()), sleep=0.0, activity=0.0, water=0.0, screen=0.0, study=0.0, breaks=0,
                                energy=0, focus=0, mood=0, stress=0, note="", synthetic=0)]); df.attrs["new"] = True
    return df

# ---------------- deterministic analytics ----------------
def baseline(df, days):
    h = df.iloc[:-1].tail(days)
    if h.empty: h = df.tail(days)  # first entries: compare with itself instead of NaN
    return {k: dict(mean=h[k].mean(), median=h[k].median(), min=h[k].min(), max=h[k].max(), std=h[k].std()) for k in MET}
def deviations(df, days=7):
    t = df.iloc[-1]; b = baseline(df, days); out = []
    for k in MET:
        m = b[k]["mean"]; p = (t[k] - m) / m * 100 if m else 0; th = THRESH.get(k)
        out.append(dict(k=k, label=MET[k][0], today=float(t[k]), base=float(m), pct=float(p), sig=bool(th and ((th < 0 and p <= th) or (th > 0 and p >= th)))))
    return out
def similar(df):
    t = df.iloc[-1]; h = df.iloc[:-1]; b = baseline(df, 30)
    low = t.energy <= 4 or t.focus <= 4
    s = h[(h.energy <= 4) | (h.focus <= 4)] if low else h[(h.energy - t.energy).abs() <= 1]
    rules = {"sleep": lambda r: r.sleep < b["sleep"]["mean"] * .9, "study": lambda r: r.study > b["study"]["mean"] * 1.15,
             "screen": lambda r: r.screen > b["screen"]["mean"] * 1.15, "activity": lambda r: r.activity < b["activity"]["mean"] * .85}
    return len(s), {k: int(sum(f(r) for r in s.itertuples())) for k, f in rules.items()}
def signal(n, c):
    if n < 3: return "Insufficient Data"
    r = c / n; return "Strong Signal" if r >= .7 else "Moderate Signal" if r >= .5 else "Limited Evidence"
def simulate(df):
    h = df.copy(); h["nf"] = h.focus.shift(-1); h["ne"] = h.energy.shift(-1); h = h.iloc[:-1]
    b = baseline(df, 30); A = h[(h.sleep < b["sleep"]["mean"] - 1) & (h.study > b["study"]["mean"] + 1)]; B = h[h.sleep >= b["sleep"]["mean"] - .5]
    f = lambda d, c: round(float(d[c].mean()), 1) if len(d) else None
    return dict(nA=len(A), A_focus=f(A, "nf"), A_energy=f(A, "ne"), nB=len(B), B_focus=f(B, "nf"), B_energy=f(B, "ne"))
def evidence(df):
    t = df.iloc[-1]; n, c = similar(df); b = baseline(df, 7); note = (t.note or "").lower()
    return {"current_state": {k: float(t[k]) for k in MET}, "user_note": t.note or "", "baseline_7d": {k: round(float(b[k]["mean"]), 2) for k in MET},
            "deviations": deviations(df), "similar_days": n, "factor_counts": c, "pattern_signal": {k: signal(n, v) for k, v in c.items()},
            "decision_simulation": simulate(df), "safety_flags": [w for w in URGENT if w in note]}

# ---------------- AI explanation layer ----------------
SYS = ("You are a student wellness explainer. Use ONLY the supplied evidence; never invent history. Correlation is not causation: say 'possible contributor', "
       "'observed pattern', 'based on your records'. No diagnosis, no medication advice. Return STRICT JSON with keys: summary (string), "
       "possible_contributors (list of {factor,evidence,signal}), suggested_routine_actions (list of strings), safety_note (string).")
def fallback(ev, q):
    sig = [d for d in ev["deviations"] if d["sig"]]
    s = ("Compared with your own 7-day baseline, " + "; ".join(f"{d['label']} is {abs(d['pct']):.0f}% {'lower' if d['pct'] < 0 else 'higher'}" for d in sig[:4]) + ".") if sig else "Today is close to your usual personal baseline."
    sm = ev["decision_simulation"]
    if "sleep" in q.lower() and "study" in q.lower() and sm["nA"] >= 1 and sm["nB"] >= 1:
        s += f" Based on your records, after {sm['nA']} similar late/low-sleep study days your next-day focus averaged {sm['A_focus']}/10, versus {sm['B_focus']}/10 after {sm['nB']} days with sleep near baseline. This is an observed pattern, not a guarantee."
    pc = [dict(factor=MET[k][0], evidence=f"{c}/{ev['similar_days']} similar low-energy/focus days showed this", signal=ev["pattern_signal"][k]) for k, c in sorted(ev["factor_counts"].items(), key=lambda x: -x[1]) if c]
    return dict(summary=s, possible_contributors=pc[:3], suggested_routine_actions=["Consider an earlier wind-down tonight", "Take a short break between study blocks", "Reduce screen time before bed"], safety_note=SAFETY)
MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash"]  # tried in order; old/retired names just get skipped
def gem(sysmsg, ev, q, need):
    key = (os.getenv("GEMINI_API_KEY") or "").strip().strip("\"'")
    if not key or key == "your_api_key_here":
        st.session_state["ai_err"] = "GEMINI_API_KEY not found - create a file named .env (not .env.example) next to app.py and restart"; return None
    body = {"contents": [{"parts": [{"text": sysmsg + "\nEVIDENCE:" + json.dumps(ev, default=float) + "\nQUESTION: " + q}]}], "generationConfig": {"responseMimeType": "application/json"}}
    pref = [x for x in [st.session_state.get("ai_model"), (os.getenv("GEMINI_MODEL") or "").strip().strip("\"'")] if x]; err = ""
    for m in pref + [x for x in MODELS if x not in pref]:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", headers={"x-goog-api-key": key}, json=body, timeout=45)
            if r.status_code == 404: err = "404 model not available"; continue
            r.raise_for_status(); parts = r.json()["candidates"][0]["content"]["parts"]
            d = json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))
            if all(k in d for k in need): st.session_state["ai_err"] = ""; st.session_state["ai_model"] = m; return d
            err = "unexpected AI format"; break
        except Exception as e:
            c = getattr(getattr(e, "response", None), "status_code", ""); err = f"{type(e).__name__} {c}".strip()
            err += {400: " (API key invalid ya galat format)", 401: " (API key invalid)", 403: " (key ko Gemini API ki permission nahi / key leak ho kar block)", 429: " (free quota khatam - thoda wait karo)"}.get(c, "")
            if c in (400, 401, 403, 429): break
    st.session_state["ai_err"] = err; return None
def ask_ai(ev, q):
    d = gem(SYS, ev, q, ("summary", "possible_contributors", "suggested_routine_actions"))
    if d and isinstance(d["summary"], str) and isinstance(d["possible_contributors"], list) and isinstance(d["suggested_routine_actions"], list):
        d["safety_note"] = d.get("safety_note") or SAFETY; return d, False  # validated before display
    return fallback(ev, q), True
def fmt(d):
    o = d["summary"]
    if d["possible_contributors"]: o += "\n\n**Possible contributors**\n" + "\n".join(f"- {c['factor']} — {c['evidence']} (*{c['signal']}*)" for c in d["possible_contributors"])
    if d["suggested_routine_actions"]: o += "\n\n**You could consider**\n" + "\n".join(f"- {a}" for a in d["suggested_routine_actions"])
    return o + f"\n\n*{d['safety_note']}*"

# ---------------- PERSONAL AI: emoji/mood detection + decision engine ----------------
EMO2 = {"😊": "Positive", "😄": "Positive", "😁": "Positive", "🙂": "Positive", "🥳": "Positive", "😐": "Neutral", "😑": "Neutral", "😴": "Tired", "😪": "Tired", "🥱": "Tired",
        "😟": "Concerned", "😰": "Concerned", "😥": "Concerned", "😢": "Low", "😭": "Low", "😞": "Low", "😩": "Low Motivation", "😫": "Low Motivation", "🙄": "Low Motivation",
        "😡": "Stressed", "😤": "Stressed", "🤯": "Stressed", "🤒": "Unwell", "🤕": "Unwell"}
WORDS = {"Positive": ["happy", "great", "good", "excited", "motivated", "calm", "khush", "accha", "mast"], "Tired": ["tired", "sleepy", "exhausted", "drained", "thak", "neend", "sust"],
         "Concerned": ["worried", "anxious", "nervous", "tension", "chinta"], "Stressed": ["stressed", "pressure", "overwhelmed", "deadline", "exam"],
         "Low Motivation": ["bored", "unmotivated", "lazy", "bore", "mann nahi", "can't focus", "cant focus", "concentrate"], "Low": ["sad", "down", "lonely", "udaas"], "Unwell": ["headache", "fever", "sick", "dard"]}
ICON = {"Positive": "😊", "Neutral": "😐", "Tired": "😴", "Concerned": "😟", "Low": "😞", "Low Motivation": "😩", "Stressed": "😤", "Unwell": "🤒"}
HING = {"kya", "karu", "karun", "hai", "nahi", "mujhe", "mera", "meri", "thak", "thaka", "neend", "padhna", "padhu", "padhai", "sona", "soun", "chahiye", "aaj", "bahut", "abhi", "kal", "mann", "raha", "rahi", "ya", "lun"}
def is_hing(t): return bool(HING & set(__import__("re").findall(r"[a-z']+", t.lower()))) or any("\u0900" <= c <= "\u097f" for c in t)
def detect_mood(text):
    t = text.lower(); sc = {}; em = []; wd = []
    for ch in text:
        if ch in EMO2: sc[EMO2[ch]] = sc.get(EMO2[ch], 0) + 1.5; em.append(f"{ch} → {EMO2[ch]}")
    for k, ws in WORDS.items():
        for w in ws:
            if w in t: sc[k] = sc.get(k, 0) + 1; wd.append(w)
    if not sc: return dict(signal="Neutral", confidence=40, emojis=[], words=[])
    k, v = max(sc.items(), key=lambda x: x[1]); return dict(signal=k, confidence=int(min(95, 50 + v * 15)), emojis=list(dict.fromkeys(em)), words=wd)
def is_decision(q): return bool(__import__("re").search(r"should i|kya karu|karun|\bor\b|\bya\b|\bvs\b|better|decide|continue|chahiye", q.lower()))
def nextday(df, mask, same=False):
    h = df.copy(); h["nf"] = h.focus if same else h.focus.shift(-1); h["ne"] = h.energy if same else h.energy.shift(-1); h = h.iloc[:-1]; x = h[mask(h)]
    return len(x), (round(float(x["nf"].mean()), 1) if len(x) else None), (round(float(x["ne"].mean()), 1) if len(x) else None)
def decide(q, df):
    s = q.lower(); t = df.iloc[-1]; b = baseline(df, 30); bs, bst, bsc, ba = (b[k]["mean"] for k in ("sleep", "study", "screen", "activity")); br = float(df.breaks.median())
    has = lambda *w: any(x in s for x in w)
    if has("study", "padh") and has("sleep", "sona", "neend", "soun"): kind = "study_sleep"
    elif has("break", "rest", "aaram") and has("study", "padh", "continue"): kind = "study_break"
    elif has("gym", "workout", "exercise", "walk", "run"): kind = "exercise_rest"
    elif has("screen", "phone", "reels", "youtube", "game", "netflix"): kind = "screen_sleep"
    else: kind = "general"
    if kind == "study_sleep": L = ("Study more", "Sleep now"); A = nextday(df, lambda h: (h.sleep < bs - 1) & (h.study > bst + 1)); B = nextday(df, lambda h: h.sleep >= bs - .5)
    elif kind == "study_break": L = ("Keep studying without a break", "Take a short break"); A = nextday(df, lambda h: h.breaks < br, True); B = nextday(df, lambda h: h.breaks >= br, True)
    elif kind == "exercise_rest": L = ("Workout / activity", "Rest today"); A = nextday(df, lambda h: h.activity >= ba); B = nextday(df, lambda h: h.activity < ba * .7)
    elif kind == "screen_sleep": L = ("Keep using screen", "Sleep now"); A = nextday(df, lambda h: h.screen > bsc + 1.5); B = nextday(df, lambda h: h.screen <= bsc)
    else: L = ("Option A", "Option B"); A = B = (0, None, None)
    hist = df.iloc[:-1]; fat = int(sum([t.sleep < bs - 1, t.energy < hist.energy.mean() - 1.5, t.focus < hist.focus.mean() - 1.5, t.study > bst + 1.5]))
    gap = (B[1] - A[1]) if (A[1] is not None and B[1] is not None) else None
    if gap is not None and abs(gap) >= .5: lean = "B" if gap > 0 else "A"
    elif kind == "general": lean = "balanced"
    elif kind == "exercise_rest": lean = "B" if fat >= 3 else "A"
    else: lean = "B" if fat >= 2 else "balanced"
    return dict(kind=kind, A_label=L[0], B_label=L[1], nA=A[0], A_focus=A[1], A_energy=A[2], nB=B[0], B_focus=B[1], B_energy=B[2], lean=lean, fatigue=fat,
                same_day=kind == "study_break", current=dict(sleep=float(t.sleep), sleep_base=round(float(bs), 1), energy=int(t.energy), focus=int(t.focus), study=float(t.study)))
SYSP = ("You are PERSONAL AI, a warm, concise companion for a student. Use ONLY the evidence JSON (current_state, baseline_7d, deviations, detected_mood, decision_analysis). "
        "Reply in the SAME language/style as the student (Hinglish is fine). Gently acknowledge detected_mood as a self-reported signal, never a diagnosis. If decision_analysis is present, "
        "compare Option A vs Option B using its numbers and the student's current data, then give a soft recommendation ('based on your data ... looks slightly better'), never certainty. "
        "No diagnosis, no medication advice. Return STRICT JSON: {\"reply\": string}.")
def pa_fallback(ev, mood, dec, hing, q=""):
    t = ev["current_state"]; T = lambda en, hi: hi if hing else en; out = []
    if mood["emojis"] or mood["words"]:
        out.append(T(f"I picked up a **{mood['signal']}** signal from your message {' '.join(e.split(' ')[0] for e in mood['emojis'])}. It's only a self-reported mood signal, not a diagnosis.",
                     f"Tumhare message se mujhe **{mood['signal']}** signal mila {' '.join(e.split(' ')[0] for e in mood['emojis'])}. Ye sirf self-reported mood signal hai, diagnosis nahi."))
    out.append(T(f"Today: sleep {t['sleep']:.1f} h (7-day baseline {ev['baseline_7d']['sleep']} h), energy {t['energy']:.0f}/10, focus {t['focus']:.0f}/10, study {t['study']:.1f} h.",
                 f"Aaj: neend {t['sleep']:.1f} ghante (baseline {ev['baseline_7d']['sleep']}), energy {t['energy']:.0f}/10, focus {t['focus']:.0f}/10, study {t['study']:.1f} ghante."))
    if dec:
        pick = {"A": dec["A_label"], "B": dec["B_label"]}.get(dec["lean"])
        out.append(T(f"Based on your data, **{pick}** looks slightly better right now." if pick else "Based on your data, both options look fairly balanced right now.",
                     f"Tumhare data ke hisaab se abhi **{pick}** thoda behtar lag raha hai." if pick else "Tumhare data ke hisaab se dono options abhi lagbhag barabar hain."))
        out.append(T("This is an observed pattern from your own history, not a guarantee.", "Ye tumhari apni history ka pattern hai, guarantee nahi."))
    else:
        sig = [d for d in ev["deviations"] if d["sig"]]
        if sig: out.append(alert_text(sig[0]))
        top = [(k, c) for k, c in sorted(ev["factor_counts"].items(), key=lambda x: -x[1]) if c][:2]
        if top: out.append(T("Possible contributors seen on similar past days: ", "Pichle similar dinon mein ye factors dikhe: ") + "; ".join(f"{MET[k][0]} ({c}/{ev['similar_days']})" for k, c in top) + ".")
        y = ev.get("yesterday")
        if y and ("yesterday" in q.lower() or "kal" in q.lower().split()):
            out.append(T("Compared with yesterday: ", "Kal ke mukable: ") + ", ".join(f"{MET[k][0]} {t[k] - y[k]:+.1f}" for k in ("sleep", "study", "screen", "activity", "energy", "focus")))
        out.append(T("Ask a decision like 'Should I study or sleep?' and I'll compare using your records.", "Koi decision poochho, jaise 'padhai karu ya sona?', main tumhare records se compare kar dunga."))
    return "\n\n".join(out)
def ask_personal(ev, q, mood, dec, hing):
    d = gem(SYSP, ev, q, ("reply",))
    if d and isinstance(d["reply"], str): return d["reply"], False
    return pa_fallback(ev, mood, dec, hing, q), True

# ---------------- AI report engine ----------------
THEORY = {"sleep": ("Less sleep than usual is commonly associated with lower focus and energy.", "More sleep than usual often follows a short-sleep stretch and can support recovery."),
          "screen": ("Less screen time can free time for rest, movement or study.", "Higher screen time, especially late in the day, is commonly associated with delayed sleep and eye strain."),
          "study": ("A lighter study load may mean less workload or less consistency.", "A heavier study load can raise fatigue and squeeze sleep and breaks if not balanced."),
          "activity": ("Less physical activity is commonly linked with lower energy and mood.", "More activity is generally linked with better energy and mood when recovery is adequate."),
          "water": ("Lower hydration is commonly linked with tiredness and reduced concentration.", "Higher hydration supports steadier energy and focus."),
          "energy": ("Lower self-reported energy may reflect changes in sleep, workload or routine.", "Higher self-reported energy suggests your routine is working better than usual."),
          "focus": ("Lower self-reported focus often appears alongside less sleep, more screen time or heavy workload.", "Higher focus suggests recent habits are supporting concentration."),
          "mood": ("A lower self-reported mood score can accompany stress, fatigue or workload.", "A higher mood score suggests a more positive recent stretch."),
          "stress": ("Lower stress is generally a good sign for recovery.", "Higher stress can accompany heavy workload or short sleep.")}
MODES = ["Today vs 7-day baseline", "Last 2 days vs previous 2 days", "Last 7 days vs previous 7 days", "Last 14 days vs previous 14 days"]
def changes(df, mode):
    ks = list(MET); n = {0: 1, 1: 2, 2: 7, 3: 14}[mode]
    if mode == 0: now = df.iloc[-1][ks].astype(float); bef = df.iloc[:-1].tail(7)[ks].mean()
    else: now = df.tail(n)[ks].mean(); bef = df.iloc[:-n].tail(n)[ks].mean()
    out = []
    for k in ks:
        p = (now[k] - bef[k]) / bef[k] * 100 if (bef[k] and bef[k] == bef[k]) else 0.0
        out.append(dict(k=k, label=MET[k][0], unit=MET[k][1], now=round(float(now[k]), 1), before=round(float(bef[k]), 1) if bef[k] == bef[k] else 0.0, pct=round(float(p), 1), dir="increased" if p >= 5 else "decreased" if p <= -5 else "stable"))
    return out
def report_ev(u, df, mode):
    ch = changes(df, mode); ev = evidence(df); l7 = df.tail(7); al = [alert_text(d) for d in ev["deviations"] if d["sig"]]
    low = int((l7.sleep < u["sleep_target"] - 1).sum()); hi = int((l7.screen > u["screen_target"] + 1).sum()); wl = int((l7.water < u["water_goal"] * .8).sum())
    if low >= 3: al.append(f"Sleep was more than 1 h below your planned {u['sleep_target']} h on {low} of the last 7 days.")
    if hi >= 3: al.append(f"Screen time was above your target on {hi} of the last 7 days.")
    if wl >= 3: al.append(f"Hydration was well below your goal on {wl} of the last 7 days.")
    return dict(student=u["name"], date=str(dt.date.today()), comparison=MODES[mode], increased=[c for c in ch if c["dir"] == "increased"], decreased=[c for c in ch if c["dir"] == "decreased"],
                stable=[c["label"] for c in ch if c["dir"] == "stable"], alerts=al, similar_days=ev["similar_days"], factor_counts=ev["factor_counts"], pattern_signal=ev["pattern_signal"], safety_flags=ev["safety_flags"], all=ch)
SYSR = ("You write a student wellness report using ONLY the supplied evidence (increased, decreased, stable, alerts, patterns). Return STRICT JSON: {\"overview\": string (3-5 sentence narrative), "
        "\"alerts\": [string], \"increased\": [{\"metric\": string, \"detail\": string}], \"decreased\": [{\"metric\": string, \"detail\": string}], \"theory\": string (two short paragraphs of general wellness theory on why these "
        "changes may matter for focus, energy and routine; hedged, no diagnosis, no medication), \"patterns\": [string], \"suggestions\": [string], \"safety_note\": string}. Correlation is not causation.")
def report_fallback(r):
    det = lambda c: f"{c['before']} → {c['now']} {c['unit']} ({c['pct']:+.0f}%)"
    inc = [dict(metric=c["label"], detail=det(c)) for c in r["increased"]]; dec = [dict(metric=c["label"], detail=det(c)) for c in r["decreased"]]
    top = max(r["increased"], key=lambda c: c["pct"], default=None); low = min(r["decreased"], key=lambda c: c["pct"], default=None)
    ov = f"Comparison: {r['comparison']}. {len(inc)} measures increased, {len(dec)} decreased and {len(r['stable'])} stayed about the same."
    if top: ov += f" The largest increase was {top['label']} ({top['pct']:+.0f}%)."
    if low: ov += f" The largest decrease was {low['label']} ({low['pct']:+.0f}%)."
    th = [THEORY[c["k"]][0 if c["dir"] == "decreased" else 1] for c in sorted(r["decreased"] + r["increased"], key=lambda c: -abs(c["pct"]))[:5]]
    pat = [f"{MET[k][0]} was off-baseline on {c}/{r['similar_days']} similar low-energy/focus days ({r['pattern_signal'][k]})." for k, c in r["factor_counts"].items() if c]
    return dict(overview=ov, alerts=r["alerts"], increased=inc, decreased=dec, theory=" ".join(th) or "Your measures are close to your usual pattern.", patterns=pat,
                suggestions=["Aim to keep sleep close to your own baseline.", "Take short breaks between study blocks.", "Reduce screen time before bed and keep a water bottle nearby."], safety_note=SAFETY)
def ask_report(r):
    d = gem(SYSR, r, "Write the report", ("overview", "theory", "suggestions"))
    if d and all(isinstance(d.get(k), list) for k in ("increased", "decreased")) and isinstance(d["overview"], str) and isinstance(d["theory"], str):
        d.setdefault("alerts", r["alerts"]); d.setdefault("patterns", []); d["safety_note"] = d.get("safety_note") or SAFETY; return d, False
    return report_fallback(r), True
fx = lambda x: x if isinstance(x, str) else f"**{x.get('metric', '')}** — {x.get('detail', '')}"
def report_text(d, r):
    L = lambda t, xs: f"\n{t}\n" + "\n".join("- " + fx(x).replace("**", "") for x in xs)
    return (f"AI HEALTH ASSISTANT REPORT\nStudent: {r['student']}  Date: {r['date']}\nComparison: {r['comparison']}\n\nOVERVIEW\n{d['overview']}\n" + L("ALERTS", d.get("alerts") or ["No alerts"]) +
            L("WHAT INCREASED", d["increased"] or ["Nothing notable"]) + L("WHAT DECREASED", d["decreased"] or ["Nothing notable"]) + f"\n\nTHEORY\n{d['theory']}\n" +
            L("PATTERNS FROM YOUR HISTORY", d.get("patterns") or ["Not enough similar days"]) + L("SUGGESTIONS", d["suggestions"]) + f"\n\n{d['safety_note']}\n")
def show_report(d, r):
    st.subheader("Overview"); st.write(d["overview"]); c1, c2 = st.columns(2)
    c1.subheader("▲ What Increased")
    for x in d["increased"] or ["Nothing notable"]: c1.markdown("- " + fx(x))
    c2.subheader("▼ What Decreased")
    for x in d["decreased"] or ["Nothing notable"]: c2.markdown("- " + fx(x))
    f = go.Figure(go.Bar(x=[c["label"] for c in r["all"]], y=[c["pct"] for c in r["all"]], marker_color=["#0b5cff" if c["pct"] >= 0 else "#e0475b" for c in r["all"]])); st.plotly_chart(lay(f.update_layout(yaxis_title="% change"), 280))
    st.subheader("Alerts")
    for a in d.get("alerts") or ["No alerts — your routine is close to your usual pattern."]: st.warning(a)
    st.subheader("Theory"); st.write(d["theory"])
    if d.get("patterns"):
        st.subheader("Patterns in your history")
        for p in d["patterns"]: st.markdown("- " + p)
    st.subheader("Suggestions")
    for p in d["suggestions"]: st.markdown("- " + p)
    st.caption(d["safety_note"])

# ---------------- PDF report (with graphs) ----------------
def report_pdf(d, r, df, u):
    import io, re
    from xml.sax.saxutils import escape
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    def clean(t): return str(t).replace("→", "->").replace("↔", "<->").replace("≥", ">=").replace("≤", "<=").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'").encode("cp1252", "replace").decode("cp1252")
    ss = getSampleStyleSheet(); NAVY = colors.HexColor("#0b2a6f"); BLUE = colors.HexColor("#0b5cff")
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=22, textColor=NAVY, alignment=0, spaceAfter=2); H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, textColor=BLUE, spaceBefore=12, spaceAfter=4)
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=14, textColor=colors.HexColor("#1a2a4a")); SM = ParagraphStyle("sm", parent=B, fontSize=8, textColor=colors.grey)
    P = lambda t, st=B: Paragraph(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(clean(t))), st)
    def item(x): return Paragraph(f"<b>{escape(clean(x.get('metric', '')))}</b> - {escape(clean(x.get('detail', '')))}", B) if isinstance(x, dict) else P(x)
    def bullets(xs, empty):
        return [Paragraph("&bull; ", B) if False else Table([[Paragraph("&bull;", B), item(x)]], colWidths=[0.5 * cm, 16 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1)]) for x in (xs or [empty])]
    def img(fig, w):
        b = io.BytesIO(); fig.savefig(b, format="png", dpi=150, bbox_inches="tight"); plt.close(fig); b.seek(0); iw, ih = ImageReader(b).getSize(); b.seek(0); return Image(b, width=w, height=w * ih / iw)
    W = 17 * cm; S = []
    S += [P("AI HEALTH ASSISTANT", H1), P("Student Health & Routine Report", B), Spacer(1, 6), P(f"Student: {r['student']}   |   Date: {r['date']}   |   Comparison: {r['comparison']}", SM)]
    if bool(df.iloc[-1].synthetic): S.append(P("Note: this report uses synthetic demo data.", SM))
    S += [P("Overview", H2), P(d["overview"]), P("Metric Summary", H2)]
    rows = [["Metric", "Before", "Now", "Change %", "Direction"]] + [[c["label"], f"{c['before']} {c['unit']}", f"{c['now']} {c['unit']}", f"{c['pct']:+.1f}%", c["dir"].capitalize()] for c in r["all"]]
    t = Table(rows, colWidths=[4.6 * cm, 3.3 * cm, 3.3 * cm, 2.9 * cm, 2.9 * cm], repeatRows=1)
    st_ = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c8d4ee")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f8ff")])]
    for i, c in enumerate(r["all"], 1):
        if c["dir"] != "stable": st_.append(("TEXTCOLOR", (4, i), (4, i), BLUE if c["dir"] == "increased" else colors.HexColor("#c0293f")))
    t.setStyle(TableStyle(st_)); S.append(t)
    fig, a = plt.subplots(figsize=(8, 3.2)); xs = [c["label"] for c in r["all"]]; ys = [c["pct"] for c in r["all"]]
    a.bar(xs, ys, color=["#0b5cff" if y >= 0 else "#e0475b" for y in ys]); a.axhline(0, color="#444", lw=.8); a.set_ylabel("% change", fontsize=8); a.set_title("What changed: " + r["comparison"], fontsize=9)
    plt.setp(a.get_xticklabels(), rotation=30, ha="right", fontsize=7); a.tick_params(axis="y", labelsize=7); fig.tight_layout(); S += [Spacer(1, 8), img(fig, W)]
    S += [P("What Increased", H2)] + bullets(d["increased"], "Nothing notable.") + [P("What Decreased", H2)] + bullets(d["decreased"], "Nothing notable.")
    S += [P("Alerts", H2)] + bullets(d.get("alerts"), "No alerts - your routine is close to your usual pattern.")
    S.append(P("Theory", H2))
    for para in str(d["theory"]).split("\n\n"): S += [P(para), Spacer(1, 4)]
    S.append(P("Trends (last 14 days, dashed line = personal baseline)", H2)); dd = df.tail(14); ks = ["sleep", "focus", "energy", "screen", "study", "water"]
    fig, ax = plt.subplots(3, 2, figsize=(8, 7))
    for a, k in zip(ax.flat, ks):
        a.plot(range(len(dd)), dd[k], color="#0b5cff", marker="o", ms=3, lw=1.6); a.axhline(dd[k].iloc[:-1].mean(), ls="--", color="#888", lw=1); a.set_title(f"{MET[k][0]} ({MET[k][1]})", fontsize=9)
        a.set_xticks([0, len(dd) - 1]); a.set_xticklabels([dd.date.iloc[0][5:], dd.date.iloc[-1][5:]], fontsize=7); a.tick_params(axis="y", labelsize=7); a.grid(alpha=.2)
    fig.tight_layout(); S.append(img(fig, W))
    S += [P("Patterns in your history", H2)] + bullets(d.get("patterns"), "Not enough similar days yet.") + [P("Suggestions", H2)] + bullets(d["suggestions"], "Keep tracking daily.")
    S += [Spacer(1, 10), P(d["safety_note"] + " Correlation is not causation: patterns shown are observed associations in your own records.", SM)]
    def foot(c, doc):
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey); c.drawString(2 * cm, 1.1 * cm, "AI HEALTH ASSISTANT - Student Health Report"); c.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {doc.page}")
    buf = io.BytesIO(); SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm, title="AI HEALTH ASSISTANT Report").build(S, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()

# ---------------- UI helpers ----------------
def lay(fig, h=320):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter", color="#0b2a6f")); return fig
def alert_text(d): return f"{d['label']} is {abs(d['pct']):.0f}% {'below' if d['pct'] < 0 else 'above'} your 7-day personal baseline."

def hero_html():
    import re
    h = open(os.path.join(BASE, "hero", "index.html"), encoding="utf-8").read(); css = open(os.path.join(BASE, "hero", "style.css"), encoding="utf-8").read()
    h = h.replace('<link rel="stylesheet" href="css/style.css">', f"<style>{css}</style>")
    h = re.sub(r'<div class="btns">.*?</div>', '<div class="btns" style="height:44px"></div>', h, flags=re.S)  # real buttons are Streamlit buttons placed here
    for a, b in [("NeuralKinetics", "AI HEALTH ASSISTANT"), ("Advanced Bionics", "Routine Intelligence"), ("Cognitive AI", "SDG 3 · Well-being"), ("Adaptive Systems", "Student Wellness"),
                 ("Best digital banking card 2026", "Personal-history-first student health"), ("One Card, Zero<br>Limits. Worldwide.", "Understand Your Routine.<br>Understand What Changed."),
                 ("Neuromorphic", "Baseline"), ("AGI", "Drift"), ("Cybernetics", "Decisions")]:
        h = h.replace(a, b)
    return h

# ---------------- pages ----------------
def p_landing():
    st.markdown("""<style>
    header[data-testid="stHeader"]{display:none}.block-container{padding:0!important;max-width:100%!important}[data-testid="stVerticalBlock"]{gap:0!important}.stApp{overflow:hidden}
    iframe{height:100vh!important;width:100%!important;border:0!important;display:block}
    .st-key-btn_start,.st-key-btn_demo{position:fixed;z-index:1000;bottom:70px}.st-key-btn_start{left:16px}.st-key-btn_demo{left:150px}
    @media(min-width:768px){.st-key-btn_start,.st-key-btn_demo{bottom:32px}.st-key-btn_start{left:32px}.st-key-btn_demo{left:166px}}
    .st-key-btn_start button,.st-key-btn_demo button{padding:12px 22px!important;min-height:0!important;font-size:13px!important}
    .st-key-btn_start button p{color:#fff!important}.st-key-btn_demo button{background:transparent!important;border:1px solid rgba(0,0,0,.35)!important}.stApp div.st-key-btn_demo div.stButton button p{color:#000!important}.stApp div.st-key-btn_demo div.stButton button{background:rgba(255,255,255,.7)!important}
    </style>""", unsafe_allow_html=True)
    components.html(hero_html(), height=700, scrolling=False)
    with st.container(key="btn_start"):
        if st.button("Get Started"): st.session_state.page = "auth"; st.rerun()
    with st.container(key="btn_demo"):
        demo = st.button("Explore Demo")
    if demo:
        u = login("demo@student.dev", "demo1234")
        if not u:
            try: register("Demo Student", "demo@student.dev", "demo1234", demo=True)
            except sqlite3.IntegrityError: pass
            u = login("demo@student.dev", "demo1234")
        with st.spinner("Preparing demo data..."): make_demo(u["id"], "Surprise me")
        st.session_state.pop("pa", None); st.session_state.pop("rep", None)
        st.session_state.user = u; st.session_state.page = "DASHBOARD"; st.rerun()

def p_auth():
    st.title("AI HEALTH ASSISTANT"); st.caption("Understand your routine. Understand what changed.")
    a, b = st.tabs(["Login", "Create Account"])
    with a:
        e = st.text_input("Email", key="le"); p = st.text_input("Password", type="password", key="lp")
        if st.button("Login"):
            u = login(e, p)
            if u: st.session_state.user = u; st.session_state.page = "DASHBOARD"; st.rerun()
            else: st.error("Invalid email or password.")
    with b:
        n = st.text_input("Full Name"); e2 = st.text_input("Email", key="re"); p1 = st.text_input("Password", type="password", key="rp"); p2 = st.text_input("Confirm Password", type="password")
        if st.button("Create Account"):
            if not (n and e2 and p1): st.error("All fields are required.")
            elif "@" not in e2: st.error("Enter a valid email.")
            elif len(p1) < 6: st.error("Password needs 6+ characters.")
            elif p1 != p2: st.error("Passwords do not match.")
            else:
                try: register(n, e2, p1); st.success("Account created. Please log in.")
                except sqlite3.IntegrityError: st.error("Email already registered.")
    if st.button("← Back"): st.session_state.page = "landing"; st.rerun()

def p_dash(u, df):
    t = df.iloc[-1]; b = baseline(df, 7); h = dt.datetime.now().hour
    st.title(f"Good {'morning' if h < 12 else 'afternoon' if h < 17 else 'evening'}, {u['name'].split()[0]}")
    st.caption(f"{dt.date.today():%A, %d %B %Y} · Your personal health intelligence" + (" · latest record is synthetic demo data" if t.synthetic else ""))
    if df.attrs.get("new"): st.info("No data yet. Everything shows 0 until you save your first entry in Daily Log.")
    for col, k in zip(st.columns(5), ["sleep", "screen", "study", "activity", "energy"]):
        col.metric(MET[k][0], f"{t[k]:.1f} {MET[k][1]}", f"{t[k] - b[k]['mean']:+.1f} vs baseline", delta_color="inverse" if k in ("screen", "study") else "normal")
    l, r = st.columns(2)
    with l:
        st.subheader("Today vs Personal Baseline"); ks = ["sleep", "activity", "water", "screen", "study", "mood"]
        v = [t[k] / b[k]["mean"] * 100 if b[k]["mean"] else 0 for k in ks]
        f = go.Figure([go.Scatterpolar(r=[100] * 7, theta=ks + ks[:1], name="Baseline", line_color="#999"), go.Scatterpolar(r=v + v[:1], theta=ks + ks[:1], name="Today", fill="toself", line_color="#000")])
        st.plotly_chart(lay(f, 340))
    with r:
        st.subheader("Trend"); n = st.radio("Range", [7, 14, 30], horizontal=True); k = st.selectbox("Metric", list(MET), format_func=lambda x: MET[x][0])
        d = df.tail(n); f = go.Figure(go.Scatter(x=d.date, y=d[k], mode="lines+markers", line_color="#000")); f.add_hline(y=baseline(df, n)[k]["mean"], line_dash="dot", annotation_text="baseline")
        st.plotly_chart(lay(f, 280))
    st.subheader("Smart Alerts"); ev = evidence(df); sig = [d for d in ev["deviations"] if d["sig"]]
    if not sig: st.success("No significant routine drift today.")
    for d in sig:
        with st.expander("⚠ " + alert_text(d)):
            st.write(f"Why am I seeing this? Today {d['today']:.1f} vs baseline {d['base']:.1f} ({d['pct']:+.0f}%), beyond your configured {THRESH[d['k']]:+d}% threshold.")
            if ev["similar_days"]: st.write(f"On {ev['factor_counts'].get(d['k'], 0)} of {ev['similar_days']} similar low-energy/focus days this factor was also off.")
    if not df.attrs.get("new") and st.button("Generate AI Insight"):
        a, demo = ask_ai(ev, "Give a short insight about today."); st.info(fmt(a))

def p_log(u, df):
    st.title("Daily Log"); t = df.iloc[-1]
    with st.form("log"):
        c = st.columns(3)
        sleep = c[0].number_input("Sleep (h)", 0.0, 14.0, float(t.sleep), .5); water = c[1].number_input("Hydration (ml)", 0, 6000, int(t.water), 100); act = c[2].number_input("Activity (min)", 0, 300, int(t.activity), 5)
        screen = c[0].number_input("Screen (h)", 0.0, 18.0, float(t.screen), .5); study = c[1].number_input("Study (h)", 0.0, 16.0, float(t.study), .5); br = c[2].number_input("Breaks", 0, 20, int(t.breaks))
        en = c[0].slider("Energy", 1, 10, max(1, int(t.energy))); fo = c[1].slider("Focus", 1, 10, max(1, int(t.focus))); mo = c[2].slider("Mood", 1, 10, max(1, int(t.mood))); stt = c[0].slider("Stress", 1, 10, max(1, int(t.stress)))
        note = st.text_area("How are you feeling? (e.g. 'low energy, cannot concentrate')")
        if st.form_submit_button("Save Today's Record"):
            with db() as cn: cn.execute("insert or replace into logs values(?,?,?,?,?,?,?,?,?,?,?,?,?,0)", (u["id"], str(dt.date.today()), sleep, act, water, screen, study, br, en, fo, mo, stt, note))
            st.success("Daily record saved. Baseline and drift updated."); st.rerun()

def p_changed(u, df):
    st.title("What Changed?"); ev = evidence(df); dv = ev["deviations"]
    f = go.Figure(go.Bar(x=[d["pct"] for d in dv], y=[d["label"] for d in dv], orientation="h", marker_color=["#000" if d["sig"] else "#bbb" for d in dv]))
    st.plotly_chart(lay(f.update_layout(xaxis_title="% vs 7-day personal baseline"), 360))
    st.dataframe(pd.DataFrame([{"Metric": d["label"], "Today": round(d["today"], 1), "Baseline": round(d["base"], 1), "Change %": round(d["pct"], 1), "Significant": d["sig"]} for d in dv]), hide_index=True)
    st.subheader("Historical Evidence"); n = ev["similar_days"]; st.write(f"{n} similar historical days found (low energy/focus).")
    for k, c in ev["factor_counts"].items(): st.write(f"- {MET[k][0]} off-baseline on **{c}/{n}** similar days — *{ev['pattern_signal'][k]}*")
    st.subheader("Routine Drift vs Planned Routine"); t = df.iloc[-1]
    st.write(f"Sleep {t.sleep:.1f}h vs planned {u['sleep_target']}h · Screen {t.screen:.1f}h vs target {u['screen_target']}h · Water {t.water:.0f} vs goal {u['water_goal']:.0f} ml")
    st.caption("Correlation ≠ causation: these are possible contributors based on your own records.")
    if st.button("Explain with AI"):
        a, demo = ask_ai(ev, "What changed today?"); st.info(fmt(a))

def p_sim(u, df):
    st.subheader("Decision Simulator"); q = st.text_input("Situation", "It's 1 AM. Should I study 2 more hours or sleep now?")
    if st.button("Compare options"):
        dec = decide(q, df); ev = evidence(df); mood = detect_mood(q); ev["decision_analysis"] = dec; ev["detected_mood"] = mood
        with db() as cn: cn.execute("insert into decisions values(?,?,?,?)", (u["id"], str(dt.datetime.now()), q, json.dumps(dec)))
        show_dec(dec); r, demo = ask_personal(ev, q, mood, dec, is_hing(q)); st.info(r)

def p_replay(u, df):
    st.title("Health Replay"); t = df.iloc[-1]
    ev = [("Sleep", 23, t.sleep, f"{t.sleep:.1f} h"), ("Study", 17, t.study, f"{t.study:.1f} h"), ("Screen", 14, t.screen, f"{t.screen:.1f} h"), ("Activity", 16, t.activity / 60, f"{t.activity:.0f} min")]
    f = go.Figure([go.Barpolar(r=[.8], base=[i + 1], theta=[((s + d / 2) % 24) * 15], width=[d * 15], name=n, hovertext=f"{n}: starts {int(s)}:00 · {txt}", hoverinfo="text") for i, (n, s, d, txt) in enumerate(ev)])
    f.update_layout(polar=dict(angularaxis=dict(tickmode="array", tickvals=[h * 15 for h in range(0, 24, 2)], ticktext=[f"{h}:00" for h in range(0, 24, 2)], direction="clockwise", rotation=90), radialaxis=dict(visible=False)))
    st.plotly_chart(lay(f, 520)); st.caption("Estimated 24-hour view from today's log; hover a ring for details.")

def p_const(u, df):
    
    st.subheader("Health Constellation"); ks = list(MET); corr = df[ks].corr(); n = len(ks)
    pos = {k: (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i, k in enumerate(ks)}; f = go.Figure(); mx, my, mt = [], [], []
    for i in range(n):
        for j in range(i + 1, n):
            r = corr.iloc[i, j]
            if abs(r) >= .35:
                (x0, y0), (x1, y1) = pos[ks[i]], pos[ks[j]]; f.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", line=dict(width=abs(r) * 6, color="#000" if r > 0 else "#aaa"), hoverinfo="skip", showlegend=False))
                mx.append((x0 + x1) / 2); my.append((y0 + y1) / 2); mt.append(f"{MET[ks[i]][0]} ↔ {MET[ks[j]][0]}: r={r:+.2f} over {len(df)} days (observed association, not causation)")
    f.add_trace(go.Scatter(x=mx, y=my, mode="markers", marker=dict(size=10, color="#fff", line=dict(width=1, color="#000")), hovertext=mt, hoverinfo="text", showlegend=False))
    f.add_trace(go.Scatter(x=[pos[k][0] for k in ks], y=[pos[k][1] for k in ks], mode="markers+text", text=[MET[k][0] for k in ks], textposition="top center", marker=dict(size=22, color="#000"), showlegend=False))
    f.update_xaxes(visible=False); f.update_yaxes(visible=False); st.plotly_chart(lay(f, 560)); st.caption("Black = positive association, grey = negative. Hover the white dots.")

def p_hist(u, df):
    st.title("History & Reports"); ss = st.session_state; ta, tb = st.tabs(["📈 History", "📝 AI Report"])
    with ta:
        st.dataframe(df.drop(columns=["user_id"]), hide_index=True); st.download_button("Download History (.csv)", df.to_csv(index=False), "history.csv")
    with tb:
        m = st.selectbox("Compare", MODES)
        if st.button("Generate AI Report"):
            rev = report_ev(u, df, MODES.index(m)); d, demo = ask_report(rev)
            try: pdf, perr = report_pdf(d, rev, df, u), ""
            except Exception as e: pdf, perr = None, f"{type(e).__name__}: {str(e)[:120]}"
            ss.rep = (rev, d, demo, pdf, perr)
        if ss.get("rep"):
            rev, d, demo, pdf, perr = ss.rep; show_report(d, rev)
            if pdf: st.download_button("Download Report (PDF)", pdf, "AI_HEALTH_ASSISTANT_Report.pdf", mime="application/pdf")
            else: st.error(f"PDF could not be created ({perr}). Run: python -m pip install reportlab matplotlib")

def p_profile(u, df):
    st.title("Profile & Planned Routine")
    with st.form("pf"):
        n = st.text_input("Name", u["name"]); s = st.number_input("Planned sleep (h)", 4.0, 12.0, float(u["sleep_target"]), .5); w = st.number_input("Water goal (ml)", 500, 6000, int(u["water_goal"]), 100); sc = st.number_input("Screen target (h)", 1.0, 16.0, float(u["screen_target"]), .5)
        if st.form_submit_button("Save"):
            with db() as c: c.execute("update users set name=?,sleep_target=?,water_goal=?,screen_target=? where id=?", (n, s, w, sc, u["id"]))
            with db() as c: st.session_state.user = dict(c.execute("select * from users where id=?", (u["id"],)).fetchone())
            st.success("Saved."); st.rerun()

def show_dec(d):
    st.markdown("**Decision Simulator**"); c = st.columns(2)
    for col, k in ((c[0], "A"), (c[1], "B")):
        n, f, e = d["n" + k], d[k + "_focus"], d[k + "_energy"]
        col.markdown(f"**Option {k} · {d[k + '_label']}**" + (" ✅" if d["lean"] == k else ""))
        col.write(f"Based on {n} similar past days: {'same-day' if d['same_day'] else 'next-day'} focus {f}/10, energy {e}/10." if n and f is not None else "Not enough similar past days in your history.")
    st.caption("Observed patterns from your own records — not a guarantee or medical advice.")

def chat_tab(u, df):
    ss = st.session_state; ss.setdefault("pa", []); ec = st.columns(10)
    for i, e in enumerate(["😊", "😐", "😴", "😟", "😩"]):
        if ec[i].button(e, key=f"em{i}"): ss.pq = e
    P = ["What changed today?", "Why am I tired?", "Compare today with yesterday", "Should I study 2 more hours or sleep now?", "Break lun ya padhai continue karu?", "Should I workout or rest today?"]
    for r in range(2):
        pc = st.columns(3)
        for j in range(3):
            if pc[j].button(P[r * 3 + j], key=f"pq{r}{j}"): ss.pq = P[r * 3 + j]
    for m in ss.pa:
        with st.chat_message(m["r"]):
            if m.get("urgent"): st.error("Your message mentions possibly serious symptoms. Please seek professional medical help.")
            st.markdown(m["t"])
            if m["r"] == "user" and m.get("mood"): st.caption(f"{ICON.get(m['mood']['signal'], '')} Mood signal: {m['mood']['signal']} · {m['mood']['confidence']}% · {', '.join(m['mood']['emojis']) or 'text only'} (self-reported, not a diagnosis)")
            if m.get("dec"): show_dec(m["dec"])
    q = st.chat_input("Message PERSONAL AI 😊") or ss.pop("pq", None)
    if q:
        mood = detect_mood(q); hing = is_hing(q); dec = decide(q, df) if is_decision(q) else None; ev = evidence(df); ev["detected_mood"] = mood; ev["decision_analysis"] = dec
        if len(df) > 1: ev["yesterday"] = {k: float(df.iloc[-2][k]) for k in MET}
        r, demo = ask_personal(ev, q, mood, dec, hing)
        if dec:
            with db() as cn: cn.execute("insert into decisions values(?,?,?,?)", (u["id"], str(dt.datetime.now()), q, json.dumps(dec)))
        ss.pa += [{"r": "user", "t": q, "mood": mood, "urgent": any(w in q.lower() for w in URGENT)}, {"r": "assistant", "t": r, "dec": dec}]; st.rerun()

def p_personal(u, df):
    st.title("PERSONAL AI"); st.caption("Chat in English or Hinglish with emojis 😴😊😩 — I detect your mood, run decision simulations and explain your data using YOUR records.")
    t1, t2, t3 = st.tabs(["💬 Chat", "⚖ Decision Simulator", "🌌 Health Constellation"])
    with t1: chat_tab(u, df)
    with t2: p_sim(u, df)
    with t3:
        p_const(u, df)
        if st.button("Explain connections with AI"):
            ev = evidence(df); r, demo = ask_personal(ev, "Explain which of my habits move together, as observed associations only.", detect_mood(""), None, False); st.info(r)

PAGES = {"DASHBOARD": p_dash, "PERSONAL AI": p_personal, "DAILY LOG": p_log, "WHAT CHANGED": p_changed, "HISTORY AND REPORTS": p_hist, "PROFILE": p_profile, "HEALTH REPLAY": p_replay}

STYLE = """<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet"><style>
@keyframes shimmer{to{background-position:200% center}}@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes pulseGlow{0%,100%{text-shadow:0 0 4px rgba(11,92,255,.2)}50%{text-shadow:0 0 14px rgba(0,166,166,.5)}}
html,body,[class*="css"]{font-family:'Inter',sans-serif}.stApp{background:#fff;color:#0b2a6f}header[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#f2f6ff,#e6efff)}
.stApp h1,.stApp h2,.stApp h3,.stApp h4{background:linear-gradient(90deg,#0b2a6f,#0b5cff,#00a6a6,#7a3cff,#0b2a6f);background-size:200% auto;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;animation:shimmer 6s linear infinite;font-weight:500;letter-spacing:-.02em}
.stApp label,.stApp [data-testid="stWidgetLabel"] *,.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li,.stApp summary *,.stApp .stTabs [data-baseweb="tab"] p,.stApp [data-testid="stSidebar"] p{color:#0b2a6f!important}
.stApp [data-testid="stCaptionContainer"] *{color:#35508f!important}
.stApp [data-testid="stMetricValue"] *{color:#0b5cff!important;animation:pulseGlow 3s ease-in-out infinite;font-weight:600}.stApp [data-testid="stMetricLabel"] *{color:#0b2a6f!important}
.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMetric"],.stApp [data-testid="stChatMessage"],.stApp [data-testid="stExpander"],.stApp [data-testid="stPlotlyChart"],.stApp [data-testid="stAlert"]{animation:fadeUp .6s ease both}
input,textarea{color:#0b2a6f!important;background:#fff!important}[data-baseweb="select"] *{color:#0b2a6f!important}
[data-baseweb="popover"] *,[data-baseweb="menu"] *{color:#0b2a6f!important;background-color:#fff!important}[data-baseweb="menu"] li:hover,[role="option"]:hover{background-color:#e8f0ff!important}
[data-testid="stChatMessage"]{background:#f4f8ff;border-radius:16px}
div.stButton>button,div.stDownloadButton>button,div[data-testid="stFormSubmitButton"]>button{border-radius:999px;background:#000;border:0;padding:.45rem 1.4rem;font-weight:500;transition:.25s}
div.stButton>button:hover,div.stDownloadButton>button:hover,div[data-testid="stFormSubmitButton"]>button:hover{transform:translateY(-2px);background:linear-gradient(90deg,#0b2a6f,#0b5cff);box-shadow:0 6px 18px rgba(11,92,255,.35)}
.stApp div.stButton button p,.stApp div.stDownloadButton button p,.stApp div[data-testid="stFormSubmitButton"] button p{color:#fff!important}
.stApp [data-testid="stSidebar"] [role="radiogroup"] label{padding:.55rem .9rem;border-radius:12px;transition:.25s;margin-bottom:2px}
.stApp [data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{display:none}
.stApp [data-testid="stSidebar"] [role="radiogroup"] label:hover{background:#dbe8ff;transform:translateX(5px)}
.stApp [data-testid="stSidebar"] [role="radiogroup"] label p{letter-spacing:.08em;font-weight:500;font-size:13px}
.stApp [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:linear-gradient(90deg,#0b2a6f,#0b5cff)}
.stApp [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{color:#fff!important}
</style>"""

def main():
    st.set_page_config(page_title="AI HEALTH ASSISTANT", layout="wide", initial_sidebar_state="auto"); init(); ss = st.session_state
    st.markdown(STYLE, unsafe_allow_html=True); ss.setdefault("page", "landing")
    if "user" not in ss:
        if ss.page == "auth": p_auth()
        else: ss.page = "landing"; p_landing()
        return
    u = ss.user; sb = st.sidebar; sb.markdown(f"### AI HEALTH ASSISTANT\n{u['name']}")
    if u["email"] == DEMO_EMAIL:
        sb.markdown("**Demo mode**"); scn = sb.selectbox("Scenario", SCEN, key="scn")
        if sb.button("Generate new demo data"):
            with st.spinner("Creating demo data..."): make_demo(u["id"], scn)
            ss.pop("pa", None); ss.pop("rep", None); st.rerun()
    page = sb.radio("Menu", list(PAGES), index=list(PAGES).index(ss.page) if ss.page in PAGES else 0, label_visibility="collapsed"); ss.page = page
    if ss.get("ai_err"): sb.caption(f"Last AI call failed: {ss.ai_err}. Showing demo answer.")
    if sb.button("Logout"): ss.clear(); st.rerun()
    df = load(u["id"])
    if df.attrs.get("new") and page not in ("DASHBOARD", "DAILY LOG", "PROFILE"):
        st.title(page); st.info("No data yet. Everything shows 0 until you save your first entry in Daily Log."); return
    PAGES[page](u, df)

if __name__ == "__main__":
    main()
