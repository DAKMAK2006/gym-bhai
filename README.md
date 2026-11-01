# gym-bhai

A voice gym coach for IITB hostel life. Speak in Hinglish or English: log lifts, meals and sleep, or ask what to do next. gym-bhai answers out loud.

**The idea:** the LLM never decides your training. A rules engine does (`rules.py`: progression, protein, recovery, exam mode). The LLM only parses what you say and phrases the result.

## Sarvam APIs used
| Step | API |
|---|---|
| Speech to text (Hinglish) | Saaras v4, `codemix` mode |
| Understand + coach | `sarvam-105b-conversations` |
| Voice reply | Bulbul v3 |

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "SARVAM_API_KEY=your_key_here" > .env
.venv/bin/python app.py        # then open http://localhost:5050
```

## Demo data / tests
```bash
.venv/bin/python seed_demo.py          # fill a believable week (backs up your log; --restore to undo)
.venv/bin/python test_rules.py         # 87 rule tests, no API key needed
```

## Layout
- `app.py`: Flask backend (`/api/coach`, `/api/log`, `/api/status`, `/api/profile`, `/api/voices`)
- `rules.py`: the rules engine and the Indian food table
- `static/index.html`: the whole UI
- `data/`: your logs (git-ignored)
