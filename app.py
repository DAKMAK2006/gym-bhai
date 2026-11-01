import json
import os
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from sarvamai import SarvamAI

import rules

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
 "workouts": [{"exercise": "bench press", "sets": [{"reps": 8, "kg": 60, "times": 1}]}],
 "meals": [{"meal": "lunch" | "breakfast" | "dinner" | "snack" | null, "item": "roti", "qty": 4, "unit": "piece" | "bowl" | "g" | "glass" | "scoop" | null}],
 "sleep_hours": number or null,
 "exam_in_days": integer or null,
 "bodyweight_kg": number or null,
 "notes": "anything else relevant, or empty string"
}
Rules:
- Normalise exercise names to English lowercase (e.g. "bench", "बेंच" -> "bench press"; "deadlift"; "squat"; "overhead press"; "lat pulldown").
- "60 x 8, 8, 6" means three sets at 60 kg: write three set objects with reps 8, 8, 6, each times 1.
- "3 sets of 8 at 60", "60 kilo 3 sets of 8" or "3x8 at 60" means three identical sets: write ONE set object with reps 8, kg 60, times 3. "times" is how many identical sets (default 1). Always read the set count; never drop it.
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
            times = _num(s.get("times"), 1, 10)
            sets.extend({"reps": int(reps), "kg": kg} for _ in range(int(times or 1)))
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


COACH_REASONING = "low"

COACH_PROMPT = """You are the voice coach inside "Mess-to-Muscle", a gym app for IIT Bombay hostel students. Tone: friendly, practical senior ("bhaiya"-style), light humour, never preachy. You know hostel life: mess food, exams, bad sleep.
You get FACTS computed by the app's rules engine. Rules:
- Use ONLY numbers, weights and recommendations that appear in FACTS. Never invent or recalculate numbers. If FACTS don't have what's needed, say what to log first.
- If the user asked what to do with a lift, answer from next_targets (increase / stay / reduce) and give the exact kg and reps.
- If they only logged something, acknowledge it in one short line, then give the single most useful next step (next target, protein left, or exam/recovery advice).
- If today_modifiers or exam/recovery say to go lighter, mention it.
- Only if the user asks about exercise form: you cannot see them, so give 1-2 general cues and say you can't check their form. Never mention form otherwise. If they mention pain or injury, tell them to see a doctor or physio.
- Never mention FACTS, field names, "next_targets", "factor" or "modifiers". Speak naturally, as if you just know it. Only mention volume/weight changes when they are below 1.0, in plain words (e.g. "keep it light today").
- Reply in 2-4 short spoken sentences (under 60 words), no emojis, no markdown, no lists.
- LANGUAGE is given in FACTS as reply_language. "hindi": write ONLY in Devanagari script (e.g. "आज 40 kg पर 10 reps शानदार रहे"); gym terms like bench press, protein, reps, kg stay in English letters; never use Roman-script Hindi. "english": write ONLY plain English, no Hindi words.
Respond ONLY with JSON: {"say": "..."}"""


def coach_facts(status, entry):
    n = status["nutrition"]
    return {
        "just_logged": {k: entry[k] for k in ("workouts", "meals", "sleep_hours", "exam_in_days", "bodyweight_kg") if entry.get(k)} if entry else None,
        "goal": status["profile"]["goal"], "bodyweight_kg": n["bodyweight_kg"],
        "protein_today": n["protein"], "calories_today": n["calories"],
        "meal_suggestions_for_remaining_protein": n["suggestions"], "bodyweight_trend": n["trend"]["message"],
        "exam": status["exam"]["message"], "recovery": status["recovery"]["message"],
        "today_modifiers": status["modifiers"],
        "next_targets": [{k: t.get(k) for k in ("exercise", "action", "next_kg", "today_kg", "target_reps", "message")}
                         for t in status["next_targets"]],
        "volume_warnings": status["volume"]["warnings"],
    }


HINGLISH_WORDS = {"kya", "hai", "hain", "main", "mein", "mai", "aap", "tum", "mera", "meri", "mujhe", "karun", "karu", "karna",
                  "kiya", "khaya", "badhaun", "badhao", "ghataun", "ghatao", "aaj", "kal", "bhai", "bhaiya", "kitna", "kitni",
                  "chahiye", "aur", "ya", "phir", "nahi", "nahin", "ab", "isko", "ghante", "soya", "neend", "roti", "kaise", "kyun",
                  "abhi", "thoda", "bahut", "wala", "wali", "raha", "rahi", "rahun", "karte", "batao", "bataiye", "dikhao"}


def reply_language(user_text):
    """Decide the reply language in code (not by the model): Hindi if the user used Devanagari or Hinglish words."""
    if re.search(r"[ऀ-ॿ]", user_text):
        return "hindi"
    words = set(re.findall(r"[a-z]+", user_text.lower()))
    return "hindi" if len(words & HINGLISH_WORDS) >= 2 else "english"


def parse_coach(raw):
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        try:
            d = json.loads(match.group(0))
            if isinstance(d, dict) and d.get("say"):
                return str(d["say"])
        except json.JSONDecodeError:
            pass
    return raw or "Sorry, say that once more?"


@app.post("/api/coach")
def coach():
    audio = request.files.get("audio")
    text = (request.form.get("text") or "").strip()
    history = json.loads(request.form.get("history") or "[]")
    try:
        if audio:
            text = transcribe(audio)
        if not text:
            return jsonify({"error": "Couldn't hear anything."}), 400
        parsed = extract(text)
    except (ValueError, json.JSONDecodeError) as e:
        return jsonify({"error": f"Couldn't parse that: {e}"}), 422

    entry = None
    if (parsed["workouts"] or parsed["meals"]
            or any(parsed[k] is not None for k in ("sleep_hours", "exam_in_days", "bodyweight_kg"))):
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "transcript": text, **parsed}
        save_entry(entry)

    status_now = rules.daily_status(load_log())
    lang = reply_language(text)
    facts = {**coach_facts(status_now, entry), "reply_language": lang}
    messages = [{"role": "system", "content": COACH_PROMPT + "\n\nFACTS:\n" + json.dumps(facts, ensure_ascii=False)}]
    messages += [m for m in history if m.get("role") in ("user", "assistant")][-6:]
    messages.append({"role": "user", "content": text})
    resp = client.chat.completions(model="sarvam-105b-conversations", messages=messages, temperature=0.4,
                                   reasoning_effort=COACH_REASONING)
    reply = {"say": parse_coach(resp.choices[0].message.content), "lang": "hi-IN" if lang == "hindi" else "en-IN"}

    audio_b64 = None
    try:
        tts = client.text_to_speech.convert(text=reply["say"][:1500], language_code=reply["lang"], model="bulbul:v3", speaker="aditya")
        audio_b64 = tts.audios[0]
    except Exception as e:  # keep the demo alive without voice
        print("TTS failed:", e)
    return jsonify({"transcript": text, "logged": entry, "warnings": parsed["warnings"], "reply": reply,
                    "audio": audio_b64, "status": status_now})


@app.get("/api/entries")
def entries():
    return jsonify(load_log())


@app.get("/api/status")
def status():
    return jsonify(rules.daily_status(load_log()))


@app.route("/api/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        return jsonify(rules.save_profile(request.get_json(force=True) or {}))
    return jsonify(rules.load_profile())


if __name__ == "__main__":
    app.run(port=5050, debug=False)
