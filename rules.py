"""Stage 2 rules engine. Pure Python, no LLM: every number the coach quotes comes from here."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PROFILE_FILE = DATA_DIR / "profile.json"
DEFAULT_PROFILE = {"goal": "bulk", "experience": "beginner", "bodyweight_kg": None}
FALLBACK_BODYWEIGHT = 70.0

# --------------------------------------------------------------------------- food table
# name: (default unit, grams per unit, protein g, kcal). Typical hostel-mess portions, approximate.
FOODS = {
    # breads / rice
    "roti": ("piece", 40, 3.0, 100), "paratha": ("piece", 80, 5.5, 240), "paneer paratha": ("piece", 110, 9.0, 290),
    "naan": ("piece", 90, 8.0, 260), "puri": ("piece", 30, 2.0, 110), "bread": ("slice", 30, 3.0, 80),
    "pav": ("piece", 40, 3.0, 140), "rice": ("bowl", 150, 4.0, 200), "jeera rice": ("bowl", 150, 4.0, 220),
    "khichdi": ("bowl", 200, 8.0, 230), "curd rice": ("bowl", 200, 6.0, 250),
    "veg biryani": ("plate", 300, 8.0, 420), "chicken biryani": ("plate", 300, 20.0, 500),
    # dals / legumes
    "dal": ("bowl", 150, 9.0, 160), "dal makhani": ("bowl", 150, 9.0, 260), "rajma": ("bowl", 150, 12.0, 220),
    "chana": ("bowl", 150, 13.0, 240), "sprouts": ("bowl", 100, 7.0, 90), "sambar": ("bowl", 150, 5.0, 100),
    "kadhi": ("bowl", 150, 5.0, 150), "soya chunks": ("serving", 30, 15.5, 100), "sattu": ("glass", 250, 6.0, 105),
    # sabzis
    "aloo gobi": ("bowl", 150, 3.5, 150), "aloo sabzi": ("bowl", 150, 3.0, 170), "mixed veg": ("bowl", 150, 3.0, 110),
    "bhindi": ("bowl", 150, 3.0, 130), "palak paneer": ("bowl", 180, 12.0, 290), "paneer bhurji": ("bowl", 150, 14.0, 280),
    "matar paneer": ("bowl", 150, 11.0, 270),
    # paneer / tofu / dairy
    "paneer": ("serving", 60, 11.0, 160), "tofu": ("serving", 100, 8.0, 76), "milk": ("glass", 250, 8.0, 150),
    "dahi": ("bowl", 150, 5.0, 90), "lassi": ("glass", 250, 6.0, 160), "chaas": ("glass", 200, 2.0, 40),
    "chai": ("cup", 150, 2.0, 70),
    # eggs / meat / fish
    "egg": ("piece", 50, 6.3, 75), "egg white": ("piece", 33, 3.6, 17), "omelette": ("piece", 110, 12.0, 190),
    "egg curry": ("bowl", 200, 14.0, 260), "chicken": ("serving", 100, 25.0, 165), "chicken curry": ("bowl", 200, 25.0, 280),
    "fish": ("serving", 100, 22.0, 140),
    # breakfast / snacks
    "poha": ("plate", 150, 4.0, 250), "upma": ("plate", 150, 5.0, 240), "idli": ("piece", 40, 2.0, 60),
    "dosa": ("piece", 90, 3.0, 140), "uttapam": ("piece", 100, 4.0, 160), "besan chilla": ("piece", 60, 5.0, 120),
    "oats": ("bowl", 40, 5.0, 150), "maggi": ("pack", 70, 8.0, 360), "samosa": ("piece", 70, 4.0, 260),
    "vada pav": ("piece", 120, 5.0, 290),
    # supplements / fruit / nuts
    "whey": ("scoop", 30, 24.0, 120), "peanuts": ("serving", 30, 8.0, 170), "peanut butter": ("tbsp", 16, 4.0, 95),
    "almonds": ("serving", 15, 3.0, 90), "banana": ("piece", 120, 1.3, 105), "apple": ("piece", 180, 0.5, 95),
}

ALIASES = {
    "chapati": "roti", "phulka": "roti", "chapatti": "roti", "parantha": "paratha", "aloo paratha": "paratha",
    "chawal": "rice", "plain rice": "rice", "steamed rice": "rice", "pulao": "jeera rice",
    "toor dal": "dal", "moong dal": "dal", "masoor dal": "dal", "arhar dal": "dal", "dal tadka": "dal", "dal fry": "dal",
    "daal": "dal", "lentils": "dal", "kidney beans": "rajma", "chole": "chana", "chana masala": "chana",
    "chickpeas": "chana", "kala chana": "chana", "soya": "soya chunks", "soy chunks": "soya chunks", "nutrela": "soya chunks",
    "soybean": "soya chunks", "soyabean": "soya chunks", "gobi": "aloo gobi", "aloo": "aloo sabzi", "sabzi": "mixed veg",
    "sabji": "mixed veg", "vegetables": "mixed veg", "veg": "mixed veg", "okra": "bhindi", "cottage cheese": "paneer",
    "curd": "dahi", "yogurt": "dahi", "yoghurt": "dahi", "raita": "dahi", "buttermilk": "chaas", "tea": "chai",
    "eggs": "egg", "boiled egg": "egg", "boiled eggs": "egg", "anda": "egg", "ande": "egg", "omelet": "omelette",
    "bread omelette": "omelette", "protein powder": "whey", "protein shake": "whey", "whey protein": "whey",
    "groundnuts": "peanuts", "moongfali": "peanuts", "chicken breast": "chicken", "chilla": "besan chilla",
    "noodles": "maggi", "oatmeal": "oats", "porridge": "oats", "paneer sabzi": "paneer", "idly": "idli",
}

SUGGESTIONS = [
    [("egg", 2), ("dal", 1)], [("paneer", 1), ("roti", 2)], [("chana", 1), ("dahi", 1)],
    [("soya chunks", 1), ("rice", 1)], [("milk", 1), ("peanuts", 1)], [("whey", 1)],
    [("rajma", 1), ("rice", 1)], [("egg", 3)], [("chicken", 1), ("roti", 2)], [("sprouts", 1), ("dahi", 1)],
    [("omelette", 1), ("milk", 1)], [("palak paneer", 1), ("roti", 2)],
]


def _canon_food(item):
    k = " ".join(str(item).lower().replace("-", " ").replace("_", " ").split())
    for cand in (k, ALIASES.get(k)):
        if cand in FOODS:
            return cand
    if k in ALIASES and ALIASES[k] in FOODS:
        return ALIASES[k]
    for suffix in ("es", "s"):
        if k.endswith(suffix):
            k2 = k[: -len(suffix)]
            if k2 in FOODS:
                return k2
            if ALIASES.get(k2) in FOODS:
                return ALIASES[k2]
    return None


def food_nutrition(item, qty=None, unit=None):
    """Returns {"protein_g", "kcal", "assumed"} or None for an unknown food. Never guesses unknown foods."""
    name = _canon_food(item)
    if name is None:
        return None
    default_unit, grams, protein, kcal = FOODS[name]
    n = 1.0 if qty is None else float(qty)
    assumed = qty is None
    if unit == "g":
        n = n / grams
        assumed = False
    elif unit not in (None, default_unit) and unit not in ("piece", "serving"):
        assumed = True  # e.g. user said "2 bowls" of roti: count as 2 default units
    return {"food": name, "protein_g": round(protein * n, 1), "kcal": round(kcal * n), "assumed": assumed}


# --------------------------------------------------------------------------- profile / bodyweight
def load_profile():
    p = dict(DEFAULT_PROFILE)
    if PROFILE_FILE.exists():
        p.update(json.loads(PROFILE_FILE.read_text()))
    return p


def save_profile(update):
    DATA_DIR.mkdir(exist_ok=True)
    p = load_profile()
    if update.get("goal") in ("bulk", "cut", "maintain"):
        p["goal"] = update["goal"]
    if update.get("experience") in ("beginner", "intermediate"):
        p["experience"] = update["experience"]
    if update.get("bodyweight_kg") is not None:
        p["bodyweight_kg"] = float(update["bodyweight_kg"])
    PROFILE_FILE.write_text(json.dumps(p, indent=2))
    return p


def latest_bodyweight(log, profile):
    for e in reversed(log):
        if e.get("bodyweight_kg"):
            return e["bodyweight_kg"], False
    if profile.get("bodyweight_kg"):
        return profile["bodyweight_kg"], False
    return FALLBACK_BODYWEIGHT, True


def protein_target(bodyweight, goal):
    per_kg = {"bulk": 1.8, "cut": 2.0, "maintain": 1.6}.get(goal, 1.8)
    return round(bodyweight * per_kg)


def calorie_target(bodyweight, goal):
    return round(bodyweight * 33 + {"bulk": 300, "cut": -400, "maintain": 0}.get(goal, 0))


def bodyweight_trend(log, goal):
    """kg/week from first to last logged weight (needs >= 7 days of spread) and a calorie adjustment."""
    pts = [(datetime.fromisoformat(e["ts"]), e["bodyweight_kg"]) for e in log if e.get("bodyweight_kg")]
    if len(pts) < 2 or (pts[-1][0] - pts[0][0]).days < 7:
        return {"rate_kg_per_week": None, "kcal_adjust": 0, "message": "Log bodyweight over 7+ days to see a trend."}
    days = (pts[-1][0] - pts[0][0]).total_seconds() / 86400
    rate = round((pts[-1][1] - pts[0][1]) / days * 7, 2)
    adjust, msg = 0, "On track."
    if goal == "bulk":
        if rate < 0.1:
            adjust, msg = 200, f"Gaining {rate} kg/week, too slow for a bulk. Add ~200 kcal/day."
        elif rate > 0.6:
            adjust, msg = -200, f"Gaining {rate} kg/week, too fast (extra fat). Cut ~200 kcal/day."
    elif goal == "cut":
        if rate > -0.2:
            adjust, msg = -200, f"Losing only {abs(rate)} kg/week. Cut ~200 kcal/day more."
        elif rate < -1.0:
            adjust, msg = 200, f"Losing {abs(rate)} kg/week, too fast (muscle loss). Add ~200 kcal/day."
    elif abs(rate) > 0.3:
        adjust = -200 if rate > 0 else 200
        msg = f"Weight drifting {rate:+} kg/week. Adjust {adjust:+d} kcal/day."
    return {"rate_kg_per_week": rate, "kcal_adjust": adjust, "message": msg}


def _today_meals(log, today):
    return [m for e in log if e["ts"][:10] == today.isoformat() for m in e.get("meals") or []]


def nutrition_status(log, profile, today):
    bw, assumed_bw = latest_bodyweight(log, profile)
    trend = bodyweight_trend(log, profile["goal"])
    target_p = protein_target(bw, profile["goal"])
    target_k = calorie_target(bw, profile["goal"]) + trend["kcal_adjust"]
    protein = kcal = 0.0
    unknown, assumed_items = [], []
    for m in _today_meals(log, today):
        n = food_nutrition(m["item"], m.get("qty"), m.get("unit"))
        if n is None:
            unknown.append(m["item"])
            continue
        protein += n["protein_g"]
        kcal += n["kcal"]
        if n["assumed"]:
            assumed_items.append(m["item"])
    remaining = round(target_p - protein, 1)
    return {
        "bodyweight_kg": bw, "bodyweight_assumed": assumed_bw, "trend": trend,
        "protein": {"target_g": target_p, "eaten_g": round(protein, 1), "remaining_g": max(remaining, 0),
                    "unknown_foods": unknown, "assumed_portions": assumed_items},
        "calories": {"target": target_k, "eaten": round(kcal)},
        "suggestions": suggest_protein(remaining),
    }


def suggest_protein(remaining_g):
    if remaining_g <= 0:
        return []
    scored = []
    for combo in SUGGESTIONS:
        total = sum(food_nutrition(f, q)["protein_g"] for f, q in combo)
        label = " + ".join(f"{q} {f}" if q != 1 else f"1 {f}" for f, q in combo)
        scored.append((abs(remaining_g - total) if total <= remaining_g + 5 else 999, label, round(total)))
    scored.sort()
    return [{"meal": label, "protein_g": p} for d, label, p in scored[:3] if d < 999]


# --------------------------------------------------------------------------- progression
LOWER_BODY = ("squat", "deadlift", "leg press", "lunge", "hip thrust")
COMPOUND_KEYS = ("bench", "squat", "deadlift", "overhead press", "shoulder press", "row", "pull-up", "pull up",
                 "chin-up", "dip", "leg press", "lunge", "hip thrust", "press")


def canonical_exercise(name):
    n = " ".join(str(name).lower().replace("-", " ").split())
    if n.endswith("s") and not n.endswith("press"):
        n = n[:-1]
    return {"bench": "bench press", "ohp": "overhead press", "pull up": "pull up", "push up": "push up"}.get(n, n)


def rep_range(exercise, bodyweight_mode=False):
    if bodyweight_mode:
        return 8, 15
    if any(k in exercise for k in COMPOUND_KEYS):
        return 6, 10
    return 10, 15


def _round(x, step=2.5):
    return round(x / step) * step


def weight_step(exercise, experience):
    base = 5.0 if any(k in exercise for k in LOWER_BODY) else 2.5
    return base if experience == "beginner" else max(base / 2, 1.25)


def sessions_for(log, exercise):
    target = canonical_exercise(exercise)
    by_day = {}
    for e in log:
        for w in e.get("workouts") or []:
            if canonical_exercise(w["exercise"]) == target:
                by_day.setdefault(e["ts"][:10], []).extend(w["sets"])
    return [by_day[d] for d in sorted(by_day)]


def progression(sessions, exercise, experience="beginner"):
    ex = canonical_exercise(exercise)
    if not sessions:
        return {"exercise": ex, "action": "log_more", "message": f"No {ex} logged yet. Log a session to get a target."}
    last = sessions[-1]
    weights = [s["kg"] for s in last if s.get("kg")]
    if not weights:  # bodyweight movement
        lo, hi = rep_range(ex, bodyweight_mode=True)
        reps = [s["reps"] for s in last]
        if min(reps) >= hi:
            return {"exercise": ex, "action": "add_weight", "next_kg": 2.5, "target_reps": lo, "plateau": False,
                    "message": f"All sets hit {hi}+ reps. Add weight (2.5 kg) and drop back to {lo} reps."}
        return {"exercise": ex, "action": "add_reps", "next_kg": None, "target_reps": min(min(reps) + 1, hi), "plateau": False,
                "message": f"Aim for {min(min(reps) + 1, hi)} reps on every set."}
    lo, hi = rep_range(ex)
    w = max(weights)
    reps = [s["reps"] for s in last if s.get("kg") == w]
    step = weight_step(ex, experience)
    if all(r >= hi for r in reps):
        res = {"action": "increase", "next_kg": w + step, "target_reps": lo,
               "message": f"Hit {hi}+ on every set at {w:g} kg. Go up to {w + step:g} kg for {lo} reps."}
    elif any(r < lo for r in reps):
        prev = sessions[-2] if len(sessions) >= 2 else []
        prev_reps = [s["reps"] for s in prev if s.get("kg") == w]
        if prev_reps and any(r < lo for r in prev_reps):
            nxt = _round(w * 0.9)
            res = {"action": "deload", "next_kg": nxt, "target_reps": hi,
                   "message": f"Missed {lo} reps at {w:g} kg twice. Drop to {nxt:g} kg and rebuild."}
        else:
            res = {"action": "repeat", "next_kg": w, "target_reps": lo,
                   "message": f"Below {lo} reps at {w:g} kg. Repeat the weight, aim for {lo}+ on every set."}
    else:
        t = min(min(reps) + 1, hi)
        res = {"action": "add_rep", "next_kg": w, "target_reps": t,
               "message": f"Stay at {w:g} kg and aim for {t} reps on every set."}
    plateau = False
    if len(sessions) >= 3 and res["action"] != "increase":
        sig = []
        for sess in sessions[-3:]:
            ws = [s["kg"] for s in sess if s.get("kg")]
            top = max(ws) if ws else None
            sig.append((top, sum(s["reps"] for s in sess if s.get("kg") == top)))
        plateau = len(set(sig)) == 1
    if plateau:
        res["message"] += " Plateau: same weight and reps for 3 sessions. Consider a small deload or a different rep range."
    return {"exercise": ex, "plateau": plateau, **res}


# --------------------------------------------------------------------------- recovery / volume / exam
def recovery_state(log):
    by_day = {}
    for e in log:
        if e.get("sleep_hours") is not None:
            by_day[e["ts"][:10]] = e["sleep_hours"]
    recent = [by_day[d] for d in sorted(by_day)][-3:]
    if len(recent) >= 3 and all(h < 5 for h in recent):
        return {"state": "deload", "volume_factor": 0.6, "weight_factor": 1.0, "recent_sleep": recent,
                "message": "3 short nights in a row. Deload: ~60% volume, same weights."}
    if len(recent) >= 2 and all(h < 5 for h in recent[-2:]):
        return {"state": "light", "volume_factor": 0.85, "weight_factor": 0.9, "recent_sleep": recent,
                "message": "2 short nights in a row. Go light: ~90% weights and one fewer set."}
    return {"state": "normal", "volume_factor": 1.0, "weight_factor": 1.0, "recent_sleep": recent, "message": "Recovery OK."}


MUSCLES = [("bench", "chest"), ("fly", "chest"), ("push up", "chest"), ("dip", "chest"), ("overhead", "shoulders"),
           ("shoulder", "shoulders"), ("lateral", "shoulders"), ("row", "back"), ("pull", "back"), ("deadlift", "back"),
           ("curl", "arms"), ("tricep", "arms"), ("squat", "legs"), ("leg", "legs"), ("lunge", "legs"), ("calf", "legs"),
           ("hip thrust", "legs")]


def muscle_of(exercise):
    ex = canonical_exercise(exercise)
    for key, group in MUSCLES:
        if key in ex:
            return group
    return "other"


def weekly_volume(log, today):
    cutoff = today - timedelta(days=7)
    sets = {}
    for e in log:
        if date.fromisoformat(e["ts"][:10]) <= cutoff:
            continue
        for w in e.get("workouts") or []:
            g = muscle_of(w["exercise"])
            sets[g] = sets.get(g, 0) + len(w["sets"])
    first = min((date.fromisoformat(e["ts"][:10]) for e in log), default=today)
    warnings = []
    for g, n in sets.items():
        if g != "other" and n > 20:
            warnings.append(f"{g}: {n} sets this week is high (over 20). Watch recovery.")
        elif g != "other" and n < 8 and (today - first).days >= 5:
            warnings.append(f"{g}: only {n} sets this week (under 8).")
    return {"sets_by_muscle": sets, "warnings": warnings}


def exam_state(log, today):
    for e in reversed(log):
        if e.get("exam_in_days") is not None:
            days = e["exam_in_days"] - (today - date.fromisoformat(e["ts"][:10])).days
            break
    else:
        return {"phase": "none", "days_to_exam": None, "volume_factor": 1.0, "sessions_per_week": None, "message": "No exam coming up."}
    if days > 7:
        return {"phase": "normal", "days_to_exam": days, "volume_factor": 1.0, "sessions_per_week": None,
                "message": f"Exam in {days} days. Train normally."}
    if days >= 4:
        return {"phase": "taper", "days_to_exam": days, "volume_factor": 0.7, "sessions_per_week": 3,
                "message": f"Exam in {days} days. 3 sessions/week, ~70% volume, no failure sets."}
    if days >= 2:
        return {"phase": "maintenance", "days_to_exam": days, "volume_factor": 0.4, "sessions_per_week": 2,
                "message": f"Exam in {days} days. Maintenance only: 2 short full-body sessions (20-30 min), same weights."}
    if days >= 0:
        return {"phase": "rest", "days_to_exam": days, "volume_factor": 0.0, "sessions_per_week": 0,
                "message": "Exam is today or tomorrow. Rest or a walk. Protein and sleep come first."}
    since = -days
    if since <= 7:
        return {"phase": "ramp_back", "days_to_exam": days, "volume_factor": 0.7, "sessions_per_week": 3,
                "message": "Exam done. Ramp back: ~70% volume this week."}
    if since <= 14:
        return {"phase": "ramp_back", "days_to_exam": days, "volume_factor": 0.85, "sessions_per_week": 4,
                "message": "Almost back: ~85% volume this week."}
    return {"phase": "none", "days_to_exam": None, "volume_factor": 1.0, "sessions_per_week": None, "message": "No exam coming up."}


# --------------------------------------------------------------------------- everything together
def daily_status(log, profile=None, today=None):
    profile = profile or load_profile()
    today = today or date.today()
    exam = exam_state(log, today)
    rec = recovery_state(log)
    volume_factor = min(exam["volume_factor"], rec["volume_factor"])
    weight_factor = rec["weight_factor"]
    exercises = sorted({canonical_exercise(w["exercise"]) for e in log for w in e.get("workouts") or []})
    next_targets = []
    for ex in exercises:
        p = progression(sessions_for(log, ex), ex, profile["experience"])
        if weight_factor < 1 and p.get("next_kg"):
            p["today_kg"] = _round(p["next_kg"] * weight_factor)
        next_targets.append(p)
    return {
        "date": today.isoformat(), "profile": profile, "exam": exam, "recovery": rec,
        "modifiers": {"volume_factor": volume_factor, "weight_factor": weight_factor,
                      "sessions_per_week": exam["sessions_per_week"]},
        "nutrition": nutrition_status(log, profile, today),
        "volume": weekly_volume(log, today),
        "next_targets": next_targets,
    }
