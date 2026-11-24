import os
import re
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from docx import Document

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
INSTANCE_FOLDER = os.path.join(BASE_DIR, "instance")
DATABASE = os.path.join(INSTANCE_FOLDER, "resume_analyzer.db")
ALLOWED_EXTENSIONS = {"pdf", "docx"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INSTANCE_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, user_id, name, email, password_hash):
        self.id = user_id
        self.name = name
        self.email = email
        self.password_hash = password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            career_goal TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            resume_text TEXT NOT NULL,
            score INTEGER NOT NULL,
            ats_score INTEGER NOT NULL,
            skills TEXT NOT NULL,
            strengths TEXT NOT NULL,
            weaknesses TEXT NOT NULL,
            suggestions TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS job_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_title TEXT NOT NULL,
            job_description TEXT NOT NULL,
            match_score INTEGER NOT NULL,
            matched_skills TEXT NOT NULL,
            missing_skills TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    db.commit()


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return None
    return User(row["id"], row["name"], row["email"], row["password_hash"])


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text(filepath):
    ext = filepath.rsplit(".", 1)[1].lower()
    if ext == "pdf":
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == "docx":
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""


SKILLS = [
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "html", "css", "react", "angular", "vue", "node.js", "flask",
    "django", "fastapi", "spring", "sql", "mysql", "postgresql",
    "mongodb", "sqlite", "git", "github", "docker", "kubernetes",
    "aws", "azure", "gcp", "machine learning", "deep learning",
    "nlp", "artificial intelligence", "data analysis", "pandas",
    "numpy", "tensorflow", "pytorch", "rest api", "linux",
    "power bi", "excel", "communication", "leadership", "teamwork"
]


def clean_text(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_skills(text):
    normalized = clean_text(text)
    found = []
    for skill in SKILLS:
        if skill in normalized:
            found.append(skill)
    return sorted(set(found))


def contains_any(text, terms):
    return any(term in text for term in terms)


def analyze_resume(text):
    normalized = clean_text(text)
    skills = extract_skills(text)

    sections = {
        "education": contains_any(normalized, ["education", "bachelor", "master", "degree", "university", "college"]),
        "experience": contains_any(normalized, ["experience", "internship", "work experience", "employment"]),
        "projects": contains_any(normalized, ["projects", "project"]),
        "skills": contains_any(normalized, ["skills", "technical skills", "technologies"]),
        "certifications": contains_any(normalized, ["certification", "certifications", "certificate"]),
        "contact": bool(re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)) and bool(re.search(r"\b\d{10}\b", text)),
        "summary": contains_any(normalized, ["summary", "objective", "profile"]),
    }

    section_score = sum(sections.values()) * 8
    skill_score = min(len(skills) * 3, 24)
    length_score = 10 if 250 <= len(normalized.split()) <= 1200 else 5
    action_score = 10 if contains_any(normalized, ["developed", "created", "implemented", "designed", "managed", "built"]) else 4

    score = min(100, section_score + skill_score + length_score + action_score)

    ats_terms = ["skills", "experience", "education", "projects", "python", "sql", "github"]
    ats_score = min(100, 40 + sum(8 for t in ats_terms if t in normalized))

    strengths = []
    weaknesses = []
    suggestions = []

    if skills:
        strengths.append(f"Detected {len(skills)} relevant skills.")
    else:
        weaknesses.append("Very few recognizable technical or professional skills were detected.")
        suggestions.append("Add a dedicated Skills section with technologies relevant to your target role.")

    for section, present in sections.items():
        if present:
            strengths.append(f"{section.title()} section detected.")
        else:
            weaknesses.append(f"{section.title()} section may be missing.")
            suggestions.append(f"Consider adding a clear {section.title()} section.")

    if len(normalized.split()) < 250:
        weaknesses.append("The resume appears short.")
        suggestions.append("Add measurable project, internship, or achievement details where appropriate.")
    elif len(normalized.split()) > 1200:
        weaknesses.append("The resume may be too long.")
        suggestions.append("Remove repetitive information and keep the most relevant achievements.")

    if action_score == 10:
        strengths.append("Uses several action-oriented achievement verbs.")
    else:
        suggestions.append("Use action verbs such as Developed, Implemented, Designed, Automated, or Led.")

    if re.search(r"\d+%|\b\d+\s*(users|projects|months|years|clients)\b", normalized):
        strengths.append("Contains measurable details.")
    else:
        suggestions.append("Add measurable results to projects and experience when possible.")

    if not suggestions:
        suggestions.append("Keep the resume tailored to each job description and update it regularly.")

    return {
        "score": score,
        "ats_score": ats_score,
        "skills": skills,
        "strengths": strengths[:8],
        "weaknesses": weaknesses[:8],
        "suggestions": suggestions[:10],
    }


def split_csv(items):
    return ", ".join(items) if items else "None detected"


def calculate_job_match(resume_text, job_description):
    resume_skills = set(extract_skills(resume_text))
    job_skills = set(extract_skills(job_description))

    # If no known skills occur in the job description, use keyword overlap.
    if job_skills:
        matched = sorted(resume_skills & job_skills)
        missing = sorted(job_skills - resume_skills)
        score = round((len(matched) / len(job_skills)) * 100)
    else:
        resume_words = set(re.findall(r"[a-zA-Z]{4,}", clean_text(resume_text)))
        job_words = set(re.findall(r"[a-zA-Z]{4,}", clean_text(job_description)))
        stop = {"that", "with", "this", "from", "your", "have", "will", "work", "years", "role"}
        overlap = sorted((resume_words & job_words) - stop)
        score = min(100, 40 + len(overlap) * 3)
        matched = overlap[:15]
        missing = []

    return {
        "score": max(0, min(100, score)),
        "matched": matched,
        "missing": missing,
    }


def save_analysis(user_id, filename, text, result):
    db = get_db()
    cur = db.execute("""
        INSERT INTO analyses
        (user_id, filename, resume_text, score, ats_score, skills, strengths, weaknesses, suggestions, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, filename, text, result["score"], result["ats_score"],
        "|".join(result["skills"]), "|".join(result["strengths"]),
        "|".join(result["weaknesses"]), "|".join(result["suggestions"]),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    db.commit()
    return cur.lastrowid


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return render_template("register.html")

        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            db.commit()
            user = User(cur.lastrowid, name, email, "")
            login_user(user)
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if row and check_password_hash(row["password_hash"], password):
            login_user(User(row["id"], row["name"], row["email"], row["password_hash"]))
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    analyses = db.execute(
        "SELECT * FROM analyses WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (current_user.id,)
    ).fetchall()
    total = db.execute("SELECT COUNT(*) c FROM analyses WHERE user_id = ?", (current_user.id,)).fetchone()["c"]
    avg = db.execute("SELECT AVG(score) a FROM analyses WHERE user_id = ?", (current_user.id,)).fetchone()["a"]
    avg = round(avg or 0)
    return render_template("dashboard.html", analyses=analyses, total=total, avg=avg)


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        file = request.files.get("resume")
        if not file or not file.filename:
            flash("Please choose a PDF or DOCX resume.", "danger")
            return render_template("upload.html")

        if not allowed_file(file.filename):
            flash("Only PDF and DOCX files are supported.", "danger")
            return render_template("upload.html")

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], f"{current_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}")
        file.save(filepath)

        try:
            text = extract_text(filepath)
            if not text.strip():
                flash("Could not extract readable text from this file.", "danger")
                return render_template("upload.html")

            result = analyze_resume(text)
            analysis_id = save_analysis(current_user.id, filename, text, result)
            return redirect(url_for("analysis", analysis_id=analysis_id))
        except Exception as exc:
            flash(f"Could not analyze the file: {exc}", "danger")

    return render_template("upload.html")


@app.route("/analysis/<int:analysis_id>")
@login_required
def analysis(analysis_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
        (analysis_id, current_user.id)
    ).fetchone()
    if not row:
        flash("Analysis not found.", "danger")
        return redirect(url_for("dashboard"))

    data = dict(row)
    data["skills"] = data["skills"].split("|") if data["skills"] else []
    data["strengths"] = data["strengths"].split("|") if data["strengths"] else []
    data["weaknesses"] = data["weaknesses"].split("|") if data["weaknesses"] else []
    data["suggestions"] = data["suggestions"].split("|") if data["suggestions"] else []
    return render_template("analysis.html", analysis=data)


@app.route("/job-match", methods=["GET", "POST"])
@login_required
def job_match():
    result = None
    form = {"title": "", "description": ""}
    if request.method == "POST":
        form["title"] = request.form.get("title", "").strip() or "Target Job"
        form["description"] = request.form.get("description", "").strip()

        analysis_id = request.form.get("analysis_id")
        db = get_db()
        analysis_row = None
        if analysis_id:
            analysis_row = db.execute(
                "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
                (analysis_id, current_user.id)
            ).fetchone()

        if not analysis_row:
            analysis_row = db.execute(
                "SELECT * FROM analyses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (current_user.id,)
            ).fetchone()

        if not analysis_row:
            flash("Analyze a resume first.", "warning")
            return redirect(url_for("upload"))

        if not form["description"]:
            flash("Paste a job description.", "danger")
            return render_template("job_match.html", result=None, form=form)

        result = calculate_job_match(analysis_row["resume_text"], form["description"])

        db.execute("""
            INSERT INTO job_matches
            (user_id, job_title, job_description, match_score, matched_skills, missing_skills, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            current_user.id, form["title"], form["description"], result["score"],
            "|".join(result["matched"]), "|".join(result["missing"]),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        db.commit()

    return render_template("job_match.html", result=result, form=form)


@app.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    questions = []
    role = ""
    if request.method == "POST":
        role = request.form.get("role", "").strip() or "Software Developer"
        db = get_db()
        latest = db.execute(
            "SELECT resume_text FROM analyses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (current_user.id,)
        ).fetchone()
        skills = extract_skills(latest["resume_text"]) if latest else []

        questions = [
            f"Tell me about yourself and why you are interested in a {role} role.",
            "Explain your most important project and the problem it solved.",
            f"How have you used {skills[0] if skills else 'your main technical skill'} in a real project?",
            "Describe a difficult technical problem you faced and how you solved it.",
            "How do you test and debug your applications?",
            "How do you work with Git and collaborate with a team?",
            "What would you improve in one of your existing projects?",
            "Where do you want to develop your technical skills next?"
        ]
    return render_template("interview.html", questions=questions, role=role)


@app.route("/history")
@login_required
def history():
    db = get_db()
    analyses = db.execute(
        "SELECT * FROM analyses WHERE user_id = ? ORDER BY id DESC",
        (current_user.id,)
    ).fetchall()
    matches = db.execute(
        "SELECT * FROM job_matches WHERE user_id = ? ORDER BY id DESC",
        (current_user.id,)
    ).fetchall()
    return render_template("history.html", analyses=analyses, matches=matches)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        career_goal = request.form.get("career_goal", "").strip()
        if name:
            db.execute(
                "UPDATE users SET name = ?, career_goal = ? WHERE id = ?",
                (name, career_goal, current_user.id)
            )
            db.commit()
            current_user.name = name
            flash("Profile updated.", "success")
    row = db.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
    return render_template("profile.html", profile=row)


@app.context_processor
def inject_year():
    return {"current_year": datetime.now().year}


with app.app_context():
    init_db()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False, use_reloader=False)
