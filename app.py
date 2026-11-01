import json
import os
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from sarvamai import SarvamAI

ROOT = Path(__file__).parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    raise SystemExit("SARVAM_API_KEY is not set. Add it to .env first.")

client = SarvamAI(api_subscription_key=api_key)
app = Flask(__name__, static_folder="static")

DATA_DIR = ROOT / "data"
LOG_FILE = DATA_DIR / "log.json"

EXTRACT_PROMPT = """You turn a gym student's spoken log (Hinglish / English / other Indian languages, possibly noisy transcription) into JSON.
Extract ONLY what was actually said. Never invent numbers. Use null when something was not mentioned.
Output ONLY a JSON object, no prose, in exactly this shape:
{
 "workouts": [{"exercise": "bench press", "sets": [{"reps": 8, "kg": 60}]}],
 "meals": [{"meal": "lunch" | "breakfast" | "dinner" | "snack" | null, "item": "roti", "qty": 4, "unit": "piece" | "bowl" | "g" | "glass" | "scoop" | null}],
 "sleep_hours": number or null,
 "exam_in_days": integer or null,
 "bodyweight_kg": number or null,
 "notes": "anything else relevant, or empty string"
}
Rules:
- Normalise exercise names to English lowercase (e.g. "bench", "बेंच" -> "bench press"; "deadlift"; "squat"; "overhead press"; "lat pulldown").
- "60 x 8, 8, 6" means three sets at 60 kg: reps 8, 8, 6. "3 sets of 8 at 60" means three separate sets, each 8 reps at 60 kg.
- Bodyweight exercises (pull-ups, push-ups, dips): kg is null.
- Split every food into its own meals entry. "4 roti dal paneer" -> roti qty 4, dal qty null, paneer qty null.
- "kilo" means kg. Hindi number words count too (teen = 3, chaar = 4, paanch = 5).
- If nothing gym-related was said, return empty lists and nulls."""


def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []


def save_entry(entry):
    DATA_DIR.mkdir(exist_ok=True)
    log = load_log()
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def _num(v, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def validate(data):
    """Clamp the LLM output to the schema so bad values never reach the rules engine."""
    out = {"workouts": [], "meals": [], "sleep_hours": None, "exam_in_days": None, "bodyweight_kg": None, "notes": "", "warnings": []}
    for w in data.get("workouts") or []:
        name = str(w.get("exercise") or "").strip().lower()
        sets = []
        for s in w.get("sets") or []:
            reps = _num(s.get("reps"), 1, 100)
            if reps is None:
                out["warnings"].append(f"{name}: dropped a set with unrealistic reps ({s.get('reps')})")
                continue
            kg = _num(s.get("kg"), 0, 500)
            if kg is None and s.get("kg") is not None:
                out["warnings"].append(f"{name}: dropped a set with unrealistic weight ({s.get('kg')} kg)")
                continue
            sets.append({"reps": int(reps), "kg": kg})
        if name and sets:
            out["workouts"].append({"exercise": name, "sets": sets})
    for m in data.get("meals") or []:
        item = str(m.get("item") or "").strip().lower()
        if item:
            qty = _num(m.get("qty"), 0, 5000)
            out["meals"].append({"meal": m.get("meal"), "item": item, "qty": qty, "unit": m.get("unit")})
    out["sleep_hours"] = _num(data.get("sleep_hours"), 0, 24)
    if out["sleep_hours"] is None and data.get("sleep_hours") is not None:
        out["warnings"].append(f"ignored unrealistic sleep ({data.get('sleep_hours')} h)")
    d = _num(data.get("exam_in_days"), 0, 365)
    out["exam_in_days"] = int(d) if d is not None else None
    out["bodyweight_kg"] = _num(data.get("bodyweight_kg"), 20, 300)
    out["notes"] = str(data.get("notes") or "")[:300]
    return out


def extract(text):
    resp = client.chat.completions(
        model="sarvam-105b-conversations",
        messages=[{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": text}],
        temperature=0,
    )
    raw = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("model returned no JSON")
    return validate(json.loads(match.group(0)))


def transcribe(audio):
    stt = client.speech_to_text.transcribe(
        file=(audio.filename or "audio.webm", audio.read(), audio.mimetype),
        model="saaras:v4",
        mode="codemix",
        language_code=request.form.get("language") or "unknown",
    )
    return (stt.transcript or "").strip()


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/api/log")
def log_entry():
    audio = request.files.get("audio")
    text = (request.form.get("text") or "").strip()
    try:
        if audio:
            text = transcribe(audio)
        if not text:
            return jsonify({"error": "Couldn't hear anything."}), 400
        parsed = extract(text)
    except (ValueError, json.JSONDecodeError) as e:
        return jsonify({"error": f"Couldn't parse that: {e}", "transcript": text}), 422
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "transcript": text, **parsed}
    has_data = (parsed["workouts"] or parsed["meals"] or parsed["notes"]
                or any(parsed[k] is not None for k in ("sleep_hours", "exam_in_days", "bodyweight_kg")))
    if not has_data:
        return jsonify({**entry, "saved": False, "error": "Nothing gym-related to log."}), 200
    save_entry(entry)
    return jsonify({**entry, "saved": True})


@app.get("/api/entries")
def entries():
    return jsonify(load_log())


if __name__ == "__main__":
    app.run(port=5050, debug=False)
