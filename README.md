# AI Health Assistant

A personalised wellness web app for students, built with **Streamlit**, **SQLite** and **Google Gemini**. You log your daily routine (sleep, activity, water, screen time, study, mood, energy, focus, stress), and the app compares *today* against *your own* baseline, spots what changed, and explains it in simple language.

> Mini project (2nd year B.Tech CSE) aligned with **UN SDG 3: Good Health and Well-being**.

> ⚠️ **Disclaimer:** This is an educational wellness tool, **not** a medical diagnosis. If symptoms are serious or persistent, please consult a qualified doctor.

## How it works

1. **Python does the analysis**: personal baseline, % deviation, similar-day matching and a decision simulator. The numbers are never made up by the AI.
2. **The AI only explains the evidence**: Gemini turns the computed results into friendly advice.
3. **No API key? No problem.** Rule-based fallback answers keep the app working offline.

## Pages

| Page | What it does |
|---|---|
| **Landing page** | Animated hero with **Get Started** and **Explore Demo** buttons |
| **Login / Create Account** | Email + password, stored with salted PBKDF2 hashing |
| **DASHBOARD** | Today vs. personal baseline, trend charts (7 / 14 / 30 days), alerts |
| **DAILY LOG** | Log sleep, activity, hydration, screen time, study, mood, energy, focus, stress |
| **WHAT CHANGED** | Evidence from your history, routine drift, decision simulator |
| **HEALTH REPLAY** | Replay of how your routine looked over time |
| **HISTORY AND REPORTS** | Past entries, AI-generated report, PDF download |
| **PROFILE** | Your details and planned routine |
| **PERSONAL AI** | Chat assistant powered by Gemini (English and Hinglish) |

**Explore Demo** opens a ready-made account with sample data, so no sign-up is needed.

## Tech Stack

Python · Streamlit · SQLite · Pandas · NumPy · Plotly · Matplotlib · ReportLab · python-dotenv · Google Gemini API

## Getting Started

**1. Clone the repo** (run in a terminal):
```bash
git clone https://github.com/YOUR_USERNAME/ai-health-assistant.git
cd ai-health-assistant
```

**2. Install dependencies:**
```bash
python -m pip install -r requirements.txt
```

**3. (Optional) Add your Gemini API key.** Copy `.env.example` to `.env` and edit it:
```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=your_model_name
```
Get a free key from [Google AI Studio](https://aistudio.google.com/). Without a key the app runs in offline mode.

**4. Run the app:**
```bash
python -m streamlit run app.py
```

**5. Open** http://localhost:8501 and click **Explore Demo**.

## Project Structure

```
.
├── app.py                  # Streamlit app (UI, analytics, AI layer)
├── hero/
│   ├── index.html          # Landing page template
│   └── style.css           # Landing page styles
├── static/
│   └── bg.mp4              # Landing page background video
├── .streamlit/
│   └── config.toml         # Theme and static file serving
├── requirements.txt
├── .env.example            # Sample environment variables
└── health.db               # SQLite DB, auto-created on first run (not tracked)
```

## Security Notes

- `.env` and `health.db` are in `.gitignore`. Never commit your real API key or user data.
- Passwords are salted and hashed, never stored in plain text.

## Future Scope

Wearable integration, reminders, voice input/output, more languages, mobile-friendly layout.
