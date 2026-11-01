"""Run: .venv/bin/python test_rules.py   (prints PASS/FAIL per rule, exits 1 on any failure)"""
import sys
from datetime import date, timedelta

import rules

TODAY = date(2026, 11, 10)
results = []


def day(n):  # n days before TODAY, as an ISO timestamp
    return (TODAY - timedelta(days=n)).isoformat() + "T10:00:00"


def entry(n, workouts=None, meals=None, sleep=None, exam=None, bw=None):
    return {"ts": day(n), "workouts": workouts or [], "meals": meals or [], "sleep_hours": sleep,
            "exam_in_days": exam, "bodyweight_kg": bw, "notes": ""}


def lift(name, kg, *reps):
    return {"exercise": name, "sets": [{"kg": kg, "reps": r} for r in reps]}


def check(name, cond, detail=""):
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"   -> {detail}" if detail and not cond else ""))


def prog(sessions_reps, name="bench press", kg=60, exp="beginner"):
    sessions = [[{"kg": k if isinstance(k, (int, float)) else kg, "reps": r} for r in reps] for k, reps in sessions_reps]
    return rules.progression(sessions, name, exp)


print("--- Progression")
p = prog([(60, [10, 10, 10])])
check("all sets at top of range -> +2.5 kg (upper body)", p["action"] == "increase" and p["next_kg"] == 62.5, p)
p = prog([(100, [10, 10, 10])], "squat", 100)
check("squat top of range -> +5 kg", p["action"] == "increase" and p["next_kg"] == 105, p)
p = prog([(60, [10, 10, 10])], exp="intermediate")
check("intermediate uses half step (+1.25)", p["next_kg"] == 61.25, p)
p = prog([(60, [8, 8, 7])])
check("in range, not top -> same weight, +1 rep", p["action"] == "add_rep" and p["next_kg"] == 60 and p["target_reps"] == 8, p)
p = prog([(60, [8, 5, 5])])
check("below range once -> repeat weight", p["action"] == "repeat" and p["next_kg"] == 60, p)
p = prog([(60, [8, 5, 5]), (60, [6, 5, 4])])
check("below range twice -> deload ~10%", p["action"] == "deload" and p["next_kg"] == 55, p)
p = prog([(60, [8, 8, 8]), (60, [8, 8, 8]), (60, [8, 8, 8])])
check("3 identical sessions -> plateau flag", p["plateau"] is True, p)
p = prog([(60, [7, 7, 7]), (60, [8, 8, 8]), (60, [9, 8, 8])])
check("improving reps -> no plateau", p["plateau"] is False, p)
p = rules.progression([], "bench press")
check("no history -> log_more", p["action"] == "log_more", p)
p = rules.progression([[{"kg": None, "reps": 10}, {"kg": None, "reps": 8}]], "pull-up")
check("bodyweight lift -> add reps", p["action"] == "add_reps" and p["target_reps"] == 9, p)
p = rules.progression([[{"kg": None, "reps": 15}, {"kg": None, "reps": 16}]], "pull-up")
check("bodyweight lift at 15+ -> add weight", p["action"] == "add_weight", p)
p = prog([(60, [10, 10]), ], "lateral raise")
check("isolation uses 10-15 range (10 reps not top)", p["action"] == "add_rep", p)
check("exercise name aliases ('bench', 'Pull-ups')", rules.canonical_exercise("bench") == "bench press"
      and rules.canonical_exercise("Pull-ups") == "pull up")

print("--- Protein / calories / foods")
check("protein target bulk 70kg = 126g", rules.protein_target(70, "bulk") == 126)
check("protein target cut 70kg = 140g", rules.protein_target(70, "cut") == 140)
check("protein target maintain 70kg = 112g", rules.protein_target(70, "maintain") == 112)
check("calories bulk 70kg = 2610", rules.calorie_target(70, "bulk") == 2610)
for food in ["chana", "rajma", "dahi", "aloo gobi", "dal", "paneer", "roti", "rice", "soya chunks", "egg", "chole",
             "curd", "chapati", "idli", "poha", "palak paneer", "khichdi", "sambar", "samosa", "whey", "chicken curry",
             "paneer bhurji", "lassi", "bhindi", "sattu", "maggi", "oats", "peanuts", "banana"]:
    check(f"food known: {food}", rules.food_nutrition(food) is not None)
check(f"food table size >= 55 (has {len(rules.FOODS)})", len(rules.FOODS) >= 55)
check("plural + alias: 'rotis' x4 = 12g", rules.food_nutrition("rotis", 4)["protein_g"] == 12.0)
check("eggs x3 = 18.9g", rules.food_nutrition("eggs", 3)["protein_g"] == 18.9)
check("paneer 100g = ~18g", abs(rules.food_nutrition("paneer", 100, "g")["protein_g"] - 18.3) < 0.2)
check("unknown food -> None, never guessed", rules.food_nutrition("quantum burger") is None)
check("qty missing -> flagged as assumed", rules.food_nutrition("dal")["assumed"] is True)

n = rules.nutrition_status([entry(0, meals=[{"item": "roti", "qty": 4, "unit": "piece"}, {"item": "dal", "qty": None},
                                            {"item": "unicorn stew", "qty": 1}])],
                           {"goal": "bulk", "experience": "beginner", "bodyweight_kg": 70}, TODAY)
check("daily tally = 4 roti + dal = 21g", n["protein"]["eaten_g"] == 21.0, n["protein"])
check("unknown foods listed, not counted", n["protein"]["unknown_foods"] == ["unicorn stew"])
check("remaining = 126 - 21 = 105", n["protein"]["remaining_g"] == 105.0)
check("suggestions returned when protein is short", len(n["suggestions"]) > 0)
n2 = rules.nutrition_status([entry(1, meals=[{"item": "whey", "qty": 10}])],
                            {"goal": "bulk", "experience": "beginner", "bodyweight_kg": 70}, TODAY)
check("yesterday's meals don't count today", n2["protein"]["eaten_g"] == 0)
check("no suggestions once target is hit", rules.suggest_protein(0) == [])

print("--- Bodyweight")
log = [entry(0, bw=72)]
check("latest logged bodyweight wins over profile", rules.latest_bodyweight(log, {"bodyweight_kg": 65})[0] == 72)
check("profile used when nothing logged", rules.latest_bodyweight([], {"bodyweight_kg": 65}) == (65, False))
check("fallback flagged as assumed", rules.latest_bodyweight([], {}) == (70.0, True))
t = rules.bodyweight_trend([entry(14, bw=70), entry(0, bw=70.1)], "bulk")
check("bulk, +0.05 kg/week -> add ~200 kcal", t["kcal_adjust"] == 200, t)
t = rules.bodyweight_trend([entry(14, bw=70), entry(0, bw=72)], "bulk")
check("bulk, +1 kg/week -> cut ~200 kcal", t["kcal_adjust"] == -200, t)
t = rules.bodyweight_trend([entry(14, bw=70), entry(0, bw=70.7)], "bulk")
check("bulk, +0.35 kg/week -> on track", t["kcal_adjust"] == 0, t)
t = rules.bodyweight_trend([entry(14, bw=75), entry(0, bw=75)], "cut")
check("cut, no loss -> eat ~200 kcal less", t["kcal_adjust"] == -200, t)
t = rules.bodyweight_trend([entry(2, bw=70), entry(0, bw=71)], "bulk")
check("under 7 days of data -> no trend", t["rate_kg_per_week"] is None, t)

print("--- Recovery")
check("1 short night -> normal", rules.recovery_state([entry(0, sleep=4)])["state"] == "normal")
check("2 short nights -> light (90% weights)",
      rules.recovery_state([entry(1, sleep=4), entry(0, sleep=4.5)])["state"] == "light")
r = rules.recovery_state([entry(2, sleep=4), entry(1, sleep=3), entry(0, sleep=4)])
check("3 short nights -> deload (60% volume)", r["state"] == "deload" and r["volume_factor"] == 0.6, r)
check("a good night breaks the streak",
      rules.recovery_state([entry(2, sleep=4), entry(1, sleep=4), entry(0, sleep=7)])["state"] == "normal")

print("--- Exam mode")
for d, phase, spw in [(10, "normal", None), (6, "taper", 3), (4, "taper", 3), (3, "maintenance", 2), (2, "maintenance", 2),
                      (1, "rest", 0), (0, "rest", 0)]:
    e = rules.exam_state([entry(0, exam=d)], TODAY)
    check(f"exam in {d} days -> {phase}", e["phase"] == phase and e["sessions_per_week"] == spw, e)
check("no exam logged -> none", rules.exam_state([entry(0)], TODAY)["phase"] == "none")
e = rules.exam_state([entry(3, exam=5)], TODAY)
check("'exam in 5 days' said 3 days ago = 2 days left", e["days_to_exam"] == 2 and e["phase"] == "maintenance", e)
e = rules.exam_state([entry(7, exam=0)], TODAY)
check("exam 7 days ago -> ramp back", e["phase"] == "ramp_back" and e["volume_factor"] == 0.7, e)
e = rules.exam_state([entry(12, exam=0)], TODAY)
check("exam 12 days ago -> ramp back 85%", e["volume_factor"] == 0.85, e)
check("exam 20 days ago -> back to none", rules.exam_state([entry(20, exam=0)], TODAY)["phase"] == "none")

print("--- Volume")
log = [entry(1, workouts=[lift("bench press", 60, 8, 8, 8)] * 8)]
v = rules.weekly_volume(log, TODAY)
check("24 chest sets -> high-volume warning", v["sets_by_muscle"]["chest"] == 24 and any("high" in w for w in v["warnings"]), v)
check("old sets (>7 days) ignored", rules.weekly_volume([entry(10, workouts=[lift("squat", 80, 5, 5)])], TODAY)["sets_by_muscle"] == {})

print("--- Combined status")
log = [entry(4, workouts=[lift("bench press", 60, 10, 10, 10)], bw=70),
       entry(1, sleep=4), entry(0, exam=2, sleep=4)]
s = rules.daily_status(log, {"goal": "bulk", "experience": "beginner", "bodyweight_kg": None}, TODAY)
check("exam + short sleep: volume takes the stricter factor (0.4)", s["modifiers"]["volume_factor"] == 0.4, s["modifiers"])
check("short sleep: today's bench weight scaled to 90% of 62.5", s["next_targets"][0].get("today_kg") == 55.0, s["next_targets"])
check("status includes protein target from logged bodyweight", s["nutrition"]["protein"]["target_g"] == 126)

failed = results.count(False)
print(f"\n{len(results) - failed}/{len(results)} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
