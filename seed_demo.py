"""Fill data/ with a believable week so the dashboard looks alive for the demo.
Run:  .venv/bin/python seed_demo.py        (backs up any existing data/log.json first)
Undo: .venv/bin/python seed_demo.py --restore
"""
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"
LOG, BACKUP = DATA / "log.json", DATA / "log.backup.json"


def sets(kg, *reps):
    return [{"kg": kg, "reps": r} for r in reps]


def entry(days_ago, hour, transcript, workouts=(), meals=(), sleep=None, exam=None, bw=None):
    ts = (datetime.now() - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"ts": ts.isoformat(timespec="seconds"), "transcript": transcript, "workouts": list(workouts),
            "meals": [{"meal": None, "unit": None, "qty": None, **m} for m in meals], "sleep_hours": sleep,
            "exam_in_days": exam, "bodyweight_kg": bw, "notes": "", "warnings": []}


def w(name, kg, *reps):
    return {"exercise": name, "sets": sets(kg, *reps)}


SEED = [
    entry(7, 18, "bench 37.5 x 8, 8, 7, squat 70 x 8, 8, 7", [w("bench press", 37.5, 8, 8, 7), w("squat", 70, 8, 8, 7)], sleep=7, bw=69.4),
    entry(6, 13, "lunch 4 roti dal paneer", meals=[{"item": "roti", "qty": 4}, {"item": "dal"}, {"item": "paneer"}]),
    entry(5, 18, "lat pulldown 60 x 10, 10, 9, curls 30 x 10, 10, 8", [w("lat pulldown", 60, 10, 10, 9), w("preacher curl", 30, 10, 10, 8)], sleep=6.5),
    entry(4, 18, "bench 40 x 8, 8, 8, squat 75 x 8, 8, 8", [w("bench press", 40, 8, 8, 8), w("squat", 75, 8, 8, 8)], sleep=6, bw=69.8),
    entry(3, 20, "pull ups 8, 7, 6, overhead press 30 x 8, 8, 7", [{"exercise": "pull-up", "sets": [{"kg": None, "reps": r} for r in (8, 7, 6)]},
                                                                  w("overhead press", 30, 8, 8, 7)], sleep=5.5),
    entry(2, 18, "bench 40 x 9, 9, 8, squat 80 x 8, 7, 6", [w("bench press", 40, 9, 9, 8), w("squat", 80, 8, 7, 6)], sleep=6, bw=70.0),
    entry(1, 18, "lat pulldown 65 x 10, 10, 10, curls 30 x 10, 10, 10", [w("lat pulldown", 65, 10, 10, 10), w("preacher curl", 30, 10, 10, 10)], sleep=5.5, exam=5),
    entry(0, 9, "breakfast 3 eggs, 2 slice bread, 1 glass milk, slept 5 hours", meals=[
        {"meal": "breakfast", "item": "egg", "qty": 3}, {"meal": "breakfast", "item": "bread", "qty": 2},
        {"meal": "breakfast", "item": "milk", "qty": 1, "unit": "glass"}], sleep=5, bw=70.2),
]

def main():
    if "--restore" in sys.argv:
        if BACKUP.exists():
            shutil.copy(BACKUP, LOG)
            print("Restored", LOG)
        else:
            print("No backup found.")
        return
    DATA.mkdir(exist_ok=True)
    if LOG.exists() and not BACKUP.exists():
        shutil.copy(LOG, BACKUP)
        print("Backed up existing log to", BACKUP)
    LOG.write_text(json.dumps(SEED, indent=2, ensure_ascii=False))
    (DATA / "profile.json").write_text(json.dumps({"goal": "bulk", "experience": "beginner", "bodyweight_kg": 70.2}, indent=2))
    print(f"Seeded {len(SEED)} entries. Restart not needed; reload the page.")


if __name__ == "__main__":
    main()
