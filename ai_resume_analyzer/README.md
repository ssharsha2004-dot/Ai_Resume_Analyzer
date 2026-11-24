# AI Resume Analyzer

A beginner-friendly MCA/BCA project built with Python Flask and SQLite.

## Features
- Register / Login / Logout
- Dashboard
- Resume PDF/DOCX upload
- Resume text extraction
- Rule-based resume analysis
- Resume score and ATS-style keyword score
- Job description matching
- Skill-gap analysis
- AI-style resume improvement suggestions
- Interview question generator
- Resume analysis history
- Responsive UI

## Important
This starter version uses local rule-based analysis so it works without a paid AI API.
You can connect Gemini/OpenAI later in `app.py` where marked.

## Run in VS Code

On Windows, opening this folder in VS Code starts the app automatically after you
allow the recommended folder-open task. Keep VS Code open while using the app.
Open http://127.0.0.1:5000 in your browser. If you close VS Code, the local server
stops; reopening the folder starts it again.

### Windows
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### macOS/Linux
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open:
http://127.0.0.1:5000

Demo database: SQLite is automatically created at `instance/resume_analyzer.db`.

## Project structure
```
ai_resume_analyzer/
├── app.py
├── requirements.txt
├── README.md
├── instance/
├── uploads/
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── upload.html
│   ├── analysis.html
│   ├── job_match.html
│   ├── interview.html
│   ├── history.html
│   └── profile.html
└── static/
    ├── css/style.css
    └── js/app.js
```
