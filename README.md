# 🔍 RetroLens — AI-Powered Retrospective Analyzer

Paste sprint retro notes → AI categorizes themes, detects sentiment, identifies action items, and tracks team health trends.

## Features
- **AI Analysis**: Claude API categorizes feedback into themes, detects sentiment (-1 to +1), suggests action items
- **Fallback Mode**: Rule-based analysis when no API key is configured
- **Morale Tracking**: Team morale trends across sprints
- **Theme Detection**: Recurring themes (estimation, testing, communication, etc.)
- **Action Item Tracking**: AI-suggested actions with owner/priority/status
- **Sentiment Breakdown**: Positive/neutral/negative distribution per retro
- **Multi-team Support**: Separate teams with independent retro histories

## Tech Stack
- **Backend**: Python / Flask / SQLAlchemy / Anthropic Claude API
- **Frontend**: Jinja2 / Chart.js / Custom dark theme
- **AI**: Claude claude-sonnet-4-20250514 for NLP analysis (optional — works without)

## Quick Start
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...  # Optional, for AI analysis
python app.py
```
Open `http://localhost:5002` — Demo: `saanvi / password123`
