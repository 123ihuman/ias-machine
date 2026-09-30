import json
import re
import feedparser
import hashlib
from datetime import datetime as dt_class
import json
from openai import OpenAI
import os
from collections import Counter, defaultdict
import pypdfium2 as pdfium
import pytesseract
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ias-machine-secret-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ias_machine_v2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024

db = SQLAlchemy(app)

# ---------- Models ----------
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    author = db.Column(db.String(200))
    subject = db.Column(db.String(100))
    topic = db.Column(db.String(200))
    category = db.Column(db.String(50))  # 'book' | 'paper' | 'notes'
    filename = db.Column(db.String(300), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    pages = db.relationship('Page', backref='book', lazy=True, cascade='all, delete-orphan')
    questions = db.relationship('Question', backref='paper', lazy=True, cascade='all, delete-orphan')

class Page(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    ocr_used = db.Column(db.Boolean, default=False)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    question_number = db.Column(db.String(20))
    text = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(200))
    year = db.Column(db.Integer)
    marks = db.Column(db.Integer)
    qtype = db.Column(db.String(50))  # MCQ, GS, Essay, Ethics, etc.
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    sources = db.relationship('QuestionSource', backref='question', lazy=True, cascade='all, delete-orphan')
    answers = db.relationship('Answer', backref='question', lazy=True, cascade='all, delete-orphan')
    student_answers = db.relationship('StudentAnswer', backref='question', lazy=True, cascade='all, delete-orphan')

class QuestionSource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    page_id = db.Column(db.Integer, db.ForeignKey('page.id'), nullable=False)
    note = db.Column(db.Text)
    page = db.relationship('Page', backref='linked_questions')
class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(100))
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
class StudentAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    word_count = db.Column(db.Integer)
    evaluation = db.Column(db.Text)
    score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
class MockTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    total_questions = db.Column(db.Integer)
    items = db.relationship('MockItem', backref='mock', lazy=True, cascade='all, delete-orphan')

class MockItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mock_id = db.Column(db.Integer, db.ForeignKey('mock_test.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    user_answer = db.Column(db.String(5))
    correct = db.Column(db.Boolean)
    question = db.relationship('Question')
class ExamSim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    mode = db.Column(db.String(20))          # prelims | mains | essay
    duration_minutes = db.Column(db.Integer)
    per_question_seconds = db.Column(db.Integer)
    total_questions = db.Column(db.Integer)
    status = db.Column(db.String(20), default='created')
    total_score = db.Column(db.Float)
    max_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    items = db.relationship('ExamSimQuestion', backref='exam', lazy=True, cascade='all, delete-orphan')

class ExamSimQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam_sim.id'), nullable=False)
    q_number = db.Column(db.Integer)
    text = db.Column(db.Text)
    topic = db.Column(db.String(200))
    marks = db.Column(db.Integer)
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    correct_option = db.Column(db.String(5))
    explanation = db.Column(db.Text)
    reference_answer = db.Column(db.Text)
    user_answer = db.Column(db.Text)
    time_taken = db.Column(db.Float)
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
class StudyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    exam_date = db.Column(db.String(20))
    hours_per_day = db.Column(db.Integer)
    subjects = db.Column(db.Text)          # comma separated
    weak_areas = db.Column(db.Text)
    plan_json = db.Column(db.Text)         # generated plan
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
class Topper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    roll_no = db.Column(db.String(50))
    category = db.Column(db.String(20))
    optional_subject = db.Column(db.String(100))
    attempt = db.Column(db.String(10))
    written_marks = db.Column(db.Float)
    interview_marks = db.Column(db.Float)
    total_marks = db.Column(db.Float)
    paper_marks_json = db.Column(db.Text)  # JSON: {"essay": 117, "gs1": 104, ...}
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
class InterviewSim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    audio_path = db.Column(db.String(300))
    transcript = db.Column(db.Text)
    duration_sec = db.Column(db.Float)
    words_per_min = db.Column(db.Float)
    filler_count = db.Column(db.Integer)
    ai_feedback = db.Column(db.Text)
    score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
class NewsArticle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(500), unique=True, nullable=False)
    source = db.Column(db.String(100))
    summary_raw = db.Column(db.Text)
    published = db.Column(db.String(100))
    subject = db.Column(db.String(100))
    ai_summary = db.Column(db.Text)
    fetched_at = db.Column(db.DateTime, default=db.func.current_timestamp())
class InterviewTranscript(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topper = db.Column(db.String(200))
    year = db.Column(db.Integer)
    rank = db.Column(db.String(20))
    optional = db.Column(db.String(100))
    video_url = db.Column(db.String(500))
    filename = db.Column(db.String(300))
    raw_text = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    qas = db.relationship('InterviewQA', backref='transcript', lazy=True, cascade='all, delete-orphan')

class InterviewQA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transcript_id = db.Column(db.Integer, db.ForeignKey('interview_transcript.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text)
    start_time = db.Column(db.Float)
    topic = db.Column(db.String(100))

# ---------- Helpers ----------
def ocr_pil_image(pil_img):
    if pil_img.width < 1000:
        ratio = 1000 / pil_img.width
        pil_img = pil_img.resize((int(pil_img.width * ratio), int(pil_img.height * ratio)))
    return pytesseract.image_to_string(pil_img, lang='eng')

def extract_pages(filepath, use_ocr=True):
    pdf = pdfium.PdfDocument(filepath)
    pages = []
    for i in range(len(pdf)):
        page = pdf[i]
        text = ""
        try:
            textpage = page.get_textpage()
            text = textpage.get_text_range().strip()
        except Exception:
            text = ""
        ocr_used = False
        if len(text) < 30 and use_ocr:
            bitmap = page.render(scale=2.0)
            pil_img = bitmap.to_pil()
            text = ocr_pil_image(pil_img).strip()
            ocr_used = True
        pages.append((i + 1, text if text else "[No text extracted]", ocr_used))
    pdf.close()
    return pages

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

# ---------- Routes ----------
@app.route('/')
def index():
    books = Book.query.order_by(Book.uploaded_at.desc()).all()
    return render_template('index.html', books=books)

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        flash('No file part'); return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        flash('Please upload a PDF.'); return redirect(url_for('index'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    use_ocr = request.form.get('use_ocr') == 'on'
    pages = extract_pages(filepath, use_ocr=use_ocr)

    book = Book(
        title=request.form.get('title') or filename,
        author=request.form.get('author', ''),
        subject=request.form.get('subject', ''),
        topic=request.form.get('topic', ''),
        category=request.form.get('category', 'book'),
        filename=filename
    )
    db.session.add(book)
    db.session.flush()

    for pnum, text, ocr_used in pages:
        db.session.add(Page(book_id=book.id, page_number=pnum, text=text, ocr_used=ocr_used))
    db.session.commit()

    ocr_count = sum(1 for _, _, o in pages if o)
    flash(f'Uploaded "{book.title}" — {len(pages)} pages ({ocr_count} via OCR).')
    return redirect(url_for('book_detail', book_id=book.id))

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template('book.html', book=book)

@app.route('/download/<int:book_id>')
def download_book(book_id):
    book = Book.query.get_or_404(book_id)
    return send_from_directory(app.config['UPLOAD_FOLDER'], book.filename, as_attachment=True)

@app.route('/delete/<int:book_id>', methods=['POST'])
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], book.filename))
    except OSError:
        pass
    db.session.delete(book)
    db.session.commit()
    flash('Deleted.')
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    subject = request.args.get('subject', '').strip()
    category = request.args.get('category', '').strip()
    results = []
    if query:
        words = query.split()
        q = Page.query.join(Book)
        for w in words:
            q = q.filter(Page.text.ilike(f'%{w}%'))
        if subject:
            q = q.filter(Book.subject == subject)
        if category:
            q = q.filter(Book.category == category)
        pages = q.limit(200).all()
        for page in pages:
            text = page.text or ''
            lower = text.lower()
            pos = lower.find(words[0].lower())
            if pos == -1: pos = 0
            start = max(0, pos - 150)
            end = min(len(text), pos + 350)
            snippet = text[start:end].replace('\n', ' ').strip()
            if start > 0: snippet = '...' + snippet
            if end < len(text): snippet = snippet + '...'
            results.append({'book': page.book, 'page_number': page.page_number,
                            'snippet': snippet, 'ocr_used': page.ocr_used})
    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]
    return render_template('search.html', query=query, results=results,
                           subjects=subjects, subject=subject, category=category)

# ---------- Question routes ----------
@app.route('/questions')
def questions_list():
    year = request.args.get('year', '').strip()
    subject = request.args.get('subject', '').strip()
    topic = request.args.get('topic', '').strip()
    qtype = request.args.get('qtype', '').strip()
    q = Question.query
    if year:
        try: q = q.filter(Question.year == int(year))
        except ValueError: pass
    if topic:
        q = q.filter(Question.topic.ilike(f'%{topic}%'))
    if qtype:
        q = q.filter(Question.qtype == qtype)
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    questions = q.order_by(Question.year.desc(), Question.id.desc()).limit(500).all()

    years = [y[0] for y in db.session.query(Question.year).distinct().all() if y[0]]
    years.sort(reverse=True)
    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]
    return render_template('questions.html', questions=questions,
                           years=years, subjects=subjects,
                           year=year, subject=subject, topic=topic, qtype=qtype)

@app.route('/question/<int:qid>')
def question_detail(qid):
    q = Question.query.get_or_404(qid)
    return render_template('question_detail.html', q=q)

@app.route('/paper/<int:book_id>/add-question', methods=['POST'])
def add_question(book_id):
    book = Book.query.get_or_404(book_id)
    text = request.form.get('text', '').strip()
    if not text:
        flash('Question text required.'); return redirect(url_for('book_detail', book_id=book_id))
    q = Question(
        paper_id=book.id,
        question_number=request.form.get('question_number', ''),
        text=text,
        topic=request.form.get('topic', ''),
        year=int(request.form.get('year') or 0) or None,
        marks=int(request.form.get('marks') or 0) or None,
        qtype=request.form.get('qtype', '')
    )
    db.session.add(q)
    db.session.commit()
    flash('Question added.')
    return redirect(url_for('book_detail', book_id=book_id))

@app.route('/question/<int:qid>/delete', methods=['POST'])
def delete_question(qid):
    q = Question.query.get_or_404(qid)
    paper_id = q.paper_id
    db.session.delete(q)
    db.session.commit()
    flash('Question deleted.')
    return redirect(url_for('book_detail', book_id=paper_id))

@app.route('/question/<int:qid>/link-source', methods=['POST'])
def link_source(qid):
    q = Question.query.get_or_404(qid)
    page_id = request.form.get('page_id')
    note = request.form.get('note', '')
    if page_id:
        exists = QuestionSource.query.filter_by(question_id=q.id, page_id=page_id).first()
        if not exists:
            db.session.add(QuestionSource(question_id=q.id, page_id=int(page_id), note=note))
            db.session.commit()
            flash('Source linked.')
        else:
            flash('Already linked.')
    return redirect(url_for('question_detail', qid=q.id))

@app.route('/question/<int:qid>/unlink/<int:src_id>', methods=['POST'])
def unlink_source(qid, src_id):
    src = QuestionSource.query.get_or_404(src_id)
    db.session.delete(src)
    db.session.commit()
    flash('Source removed.')
    return redirect(url_for('question_detail', qid=qid))

@app.route('/question/<int:qid>/source-search')
def source_search(qid):
    """Search pages to link as source for this question."""
    q = Question.query.get_or_404(qid)
    query = request.args.get('q', '').strip()
    results = []
    if query:
        words = query.split()
        pq = Page.query.join(Book).filter(Book.category != 'paper')
        for w in words:
            pq = pq.filter(Page.text.ilike(f'%{w}%'))
        pages = pq.limit(50).all()
        for page in pages:
            text = page.text or ''
            lower = text.lower()
            pos = lower.find(words[0].lower())
            if pos == -1: pos = 0
            start = max(0, pos - 120)
            end = min(len(text), pos + 300)
            snippet = text[start:end].replace('\n', ' ').strip()
            if start > 0: snippet = '...' + snippet
            if end < len(text): snippet = snippet + '...'
            results.append({'page': page, 'book': page.book,
                            'page_number': page.page_number, 'snippet': snippet})
    return render_template('question_source_search.html', q=q, query=query, results=results)

# ---------- Prediction Engine ----------
@app.route('/predict')
def predict():
    subject = request.args.get('subject', '').strip()
    qtype = request.args.get('qtype', '').strip()

    q = Question.query
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    if qtype:
        q = q.filter(Question.qtype == qtype)
    questions = q.all()

    # Topic frequency overall
    topic_counter = Counter()
    topic_years = defaultdict(set)
    for ques in questions:
        if ques.topic:
            key = ques.topic.strip().lower()
            topic_counter[key] += 1
            if ques.year:
                topic_years[key].add(ques.year)

    # Rank by score: frequency * year_spread
    scored = []
    all_years = sorted({ques.year for ques in questions if ques.year})
    total_years = len(all_years) if all_years else 1
    for topic, count in topic_counter.items():
        spread = len(topic_years[topic])
        score = count * (1 + spread / total_years)
        scored.append({
            'topic': topic.title(),
            'count': count,
            'years': sorted(topic_years[topic]),
            'spread': spread,
            'score': round(score, 2)
        })
    scored.sort(key=lambda x: x['score'], reverse=True)

    # Year-wise distribution
    year_topic = defaultdict(Counter)
    for ques in questions:
        if ques.topic and ques.year:
            year_topic[ques.year][ques.topic.strip().lower()] += 1

    # Type breakdown
    type_counter = Counter(q.qtype for q in questions if q.qtype)

    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]

    return render_template('predict.html',
                           scored=scored[:50],
                           all_years=all_years,
                           year_topic=dict(year_topic),
                           type_counter=dict(type_counter),
                           subjects=subjects,
                           subject=subject, qtype=qtype,
                           total=len(questions))

@app.route('/topic/<path:topic_name>')
def topic_detail(topic_name):
    topic_lower = topic_name.lower()
    questions = Question.query.filter(Question.topic.ilike(f'%{topic_lower}%')).all()

    # Gather all linked source pages across these questions
    sources = []
    seen_pages = set()
    for q in questions:
        for s in q.sources:
            if s.page.id not in seen_pages:
                sources.append({
                    'book': s.page.book,
                    'page_number': s.page.page_number,
                    'note': s.note,
                    'snippet': s.page.text[:300],
                    'question': q
                })
                seen_pages.add(s.page.id)

    years = sorted({q.year for q in questions if q.year})
    return render_template('topic_detail.html',
                           topic=topic_name,
                           questions=questions,
                           sources=sources,
                           years=years)
# ---------- AI Answer Generation ----------
def load_config():
    path = os.path.join(os.path.dirname(__file__), 'config.json')
    if not os.path.exists(path):
        return {"providers": {}}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_source_context(question):
    """Build source text from linked book pages."""
    if not question.sources:
        return "(No book sources linked. Answer from general UPSC knowledge only.)"
    parts = []
    for i, s in enumerate(question.sources, 1):
        parts.append(
            f"[Source {i}] {s.page.book.title} — Page {s.page.page_number}\n"
            f"{s.page.text[:3000]}\n"
        )
    return "\n".join(parts)

def build_prompt(question):
    sources = build_source_context(question)
    system = (
        "You are an expert UPSC Civil Services mentor. Write answers strictly in the style expected "
        "by UPSC examiners. Follow this structure:\n"
        "1. Introduction (2-3 lines, define the core issue or context)\n"
        "2. Body (main arguments, points, examples — use headings and bullets)\n"
        "3. Conclusion (balanced, forward-looking, ties to constitutional/human values)\n\n"
        "RULES:\n"
        "- Ground your answer primarily in the SOURCE material provided below.\n"
        "- Whenever you use a source, cite it as [Source N].\n"
        "- If sources are insufficient, supplement with standard UPSC knowledge, but mark it as (General Knowledge).\n"
        "- For Prelims MCQs: give the correct option with reasoning and eliminations.\n"
        "- For Mains: stick to word limits (150 or 250 words) if implied by marks.\n"
        "- Keep language clear, factual, exam-ready. No filler."
    )
    user = (
        f"QUESTION:\n{question.text}\n\n"
        f"Meta — Year: {question.year or 'N/A'}, Type: {question.qtype or 'General'}, "
        f"Marks: {question.marks or 'N/A'}, Topic: {question.topic or 'N/A'}\n\n"
        f"SOURCE MATERIAL (from standard books):\n{sources}\n\n"
        f"Now write the complete UPSC-style answer."
    )
    return system, user

def call_provider(provider_name, system_prompt, user_prompt):
    cfg = load_config()
    p = cfg.get('providers', {}).get(provider_name)
    if not p or not p.get('api_key'):
        raise ValueError(f"Provider '{provider_name}' not configured. Add API key in config.json.")
    client = OpenAI(base_url=p['base_url'], api_key=p['api_key'])
    resp = client.chat.completions.create(
        model=p['model'],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.4,
        max_tokens=2000
    )
    return resp.choices[0].message.content

# ---------- Answer Routes ----------
@app.route('/question/<int:qid>/generate-answer', methods=['POST'])
def generate_answer(qid):
    q = Question.query.get_or_404(qid)
    providers = request.form.getlist('providers')
    if not providers:
        flash('Pick at least one AI provider.')
        return redirect(url_for('question_detail', qid=q.id))

    system_prompt, user_prompt = build_prompt(q)
    for prov in providers:
        try:
            text = call_provider(prov, system_prompt, user_prompt)
            cfg = load_config()
            model_name = cfg['providers'][prov]['model']
            db.session.add(Answer(question_id=q.id, provider=prov, model=model_name, text=text))
        except Exception as e:
            flash(f"{prov}: {str(e)[:200]}")
    db.session.commit()
    flash('Answer generation complete.')
    return redirect(url_for('question_detail', qid=q.id))

@app.route('/answer/<int:aid>/delete', methods=['POST'])
def delete_answer(aid):
    a = Answer.query.get_or_404(aid)
    qid = a.question_id
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('question_detail', qid=qid))

@app.route('/providers-status')
def providers_status():
    cfg = load_config()
    status = {k: bool(v.get('api_key')) for k, v in cfg.get('providers', {}).items()}
    return status
# ---------- Subject Weightage ----------
@app.route('/weightage')
def weightage():
    # Get all questions joined with their paper's subject
    rows = db.session.query(Question, Book.subject).join(Book, Question.paper_id == Book.id).all()
    total = len(rows)
    subject_counter = Counter()
    subject_by_year = defaultdict(Counter)
    all_years = set()
    for q, subject in rows:
        if not subject:
            continue
        subject_counter[subject] += 1
        if q.year:
            subject_by_year[q.year][subject] += 1
            all_years.add(q.year)
    all_years = sorted(all_years)
    # Percentages
    weighted = [
        {"subject": s, "count": c, "percent": round(100 * c / total, 1)}
        for s, c in subject_counter.most_common()
    ]
    return render_template('weightage.html',
                           weighted=weighted,
                           total=total,
                           all_years=all_years,
                           subject_by_year={y: dict(subject_by_year[y]) for y in all_years},
                           subjects=[s[0] for s in subject_counter.most_common()])

# ---------- Cut-off Tracker ----------
UPSC_CUTOFFS = {
    # year: {"prelims": GS_only_out_of_200, "mains": out_of_1750, "final": out_of_2025, "status": "official/expected"}
    2013: {"prelims": 241.0, "mains": None, "final": 775, "status": "official"},
    2014: {"prelims": 205.0, "mains": None, "final": 889, "status": "official"},
    2015: {"prelims": 107.34, "mains": None, "final": 877, "status": "official"},
    2016: {"prelims": 116.00, "mains": None, "final": 988, "status": "official"},
    2017: {"prelims": 105.34, "mains": 809, "final": 1006, "status": "official"},
    2018: {"prelims": 98.00, "mains": 774, "final": 982, "status": "official"},
    2019: {"prelims": 98.00, "mains": 751, "final": 961, "status": "official"},
    2020: {"prelims": 92.51, "mains": 736, "final": 944, "status": "official"},
    2021: {"prelims": 87.54, "mains": 745, "final": 953, "status": "official"},
    2022: {"prelims": 88.22, "mains": 744, "final": 960, "status": "official"},
    2023: {"prelims": 75.41, "mains": 766, "final": 953, "status": "official"},
    2024: {"prelims": 87.98, "mains": 785, "final": 947, "status": "official"},
    2025: {"prelims": 92.66, "mains": 739, "final": 963, "status": "official"},
    2026: {"prelims": 84.00, "mains": None, "final": None, "status": "expected"},
}

@app.route('/cutoffs', methods=['GET', 'POST'])
def cutoffs():
    result = None
    if request.method == 'POST':
        try:
            prelims = float(request.form.get('prelims_score') or 0)
            mains = float(request.form.get('mains_score') or 0)
            final = float(request.form.get('final_score') or 0)
            target_year = int(request.form.get('target_year') or 2024)
            base = UPSC_CUTOFFS.get(target_year, UPSC_CUTOFFS[2024])
            result = {
                'target_year': target_year,
                'base': base,
                'prelims_gap': round(prelims - base['prelims'], 2),
                'mains_gap': round(mains - base['mains'], 2),
                'final_gap': round(final - base['final'], 2),
                'user_prelims': prelims,
                'user_mains': mains,
                'user_final': final,
            }
        except ValueError:
            flash('Enter valid numbers.')
    return render_template('cutoffs.html', cutoffs=UPSC_CUTOFFS, result=result)
# ---------- Current Affairs ----------
FEEDS = [
    {"name": "PIB", "url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"},
    {"name": "The Hindu – National", "url": "https://www.thehindu.com/news/national/feeder/default.rss"},
    {"name": "Indian Express – India", "url": "https://indianexpress.com/section/india/feed/"},
    {"name": "Down To Earth", "url": "https://www.downtoearth.org.in/rss/environment"},
]

SUBJECT_KEYWORDS = {
    "Polity": ["parliament", "supreme court", "high court", "constitution", "article", "amendment",
               "election", "president", "governor", "bill", "act ", "judiciary", "federal"],
    "Economy": ["gdp", "inflation", "rbi", "budget", "tax", "gst", "fiscal", "monetary", "trade",
                "export", "import", "msme", "bank", "rupee", "stock"],
    "Environment": ["climate", "pollution", "biodiversity", "forest", "wildlife", "carbon",
                    "emission", "renewable", "solar", "tiger", "wetland", "unfccc", "cop2"],
    "Science & Tech": ["isro", "drdo", "satellite", "ai ", "artificial intelligence", "quantum",
                       "vaccine", "biotech", "space", "chip", "5g", "6g", "semiconductor"],
    "International": ["un ", "united nations", "bilateral", "treaty", "summit", "g20", "brics",
                      "quad", "nato", "china", "usa", "russia", "pakistan", "border"],
    "Social": ["education", "health", "women", "child", "caste", "tribe", "poverty", "nutrition",
               "employment", "migration", "welfare", "scheme"],
    "Geography": ["monsoon", "cyclone", "flood", "drought", "earthquake", "himalaya", "river",
                  "glacier", "rainfall", "heatwave"],
    "Security": ["army", "navy", "air force", "terror", "naxal", "cyber", "border", "missile",
                 "defence", "security"],
}

def tag_subject(title, summary):
    text = ((title or "") + " " + (summary or "")).lower()
    scores = {}
    for subj, kws in SUBJECT_KEYWORDS.items():
        scores[subj] = sum(1 for kw in kws if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"

@app.route('/news/refresh', methods=['POST'])
def refresh_news():
    added = 0
    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries[:40]:
                link = entry.get("link", "")
                if not link:
                    continue
                if NewsArticle.query.filter_by(link=link).first():
                    continue
                title = entry.get("title", "").strip()
                raw = entry.get("summary", "") or entry.get("description", "")
                # strip html tags roughly
                import re as _re
                raw = _re.sub(r"<[^>]+>", "", raw)[:1500]
                subject = tag_subject(title, raw)
                art = NewsArticle(
                    title=title, link=link, source=feed["name"],
                    summary_raw=raw, published=entry.get("published", ""),
                    subject=subject
                )
                db.session.add(art)
                added += 1
        except Exception as e:
            flash(f"{feed['name']}: {str(e)[:100]}")
    db.session.commit()
    flash(f'Fetched {added} new articles.')
    return redirect(url_for('news_list'))

@app.route('/news')
def news_list():
    subject = request.args.get('subject', '').strip()
    q = NewsArticle.query
    if subject:
        q = q.filter(NewsArticle.subject == subject)
    articles = q.order_by(NewsArticle.fetched_at.desc()).limit(200).all()
    subjects = [s[0] for s in db.session.query(NewsArticle.subject).distinct().all() if s[0]]
    return render_template('news.html', articles=articles, subjects=subjects, subject=subject)

@app.route('/news/<int:aid>')
def news_detail(aid):
    article = NewsArticle.query.get_or_404(aid)
    return render_template('news_detail.html', article=article)

@app.route('/news/<int:aid>/summarize', methods=['POST'])
def news_summarize(aid):
    article = NewsArticle.query.get_or_404(aid)
    prompt = (
        "Summarize this news article for UPSC Civil Services preparation in exactly 5 bullet points.\n"
        "Then add a line 'GS Paper Linkage: ' with the most relevant GS paper (GS1/GS2/GS3/GS4) and topic.\n"
        "Keep it crisp and factual.\n\n"
        f"TITLE: {article.title}\n\nCONTENT:\n{article.summary_raw[:3000]}"
    )
    cfg = load_config()
    for prov, p in cfg.get('providers', {}).items():
        if p.get('api_key'):
            try:
                client = OpenAI(base_url=p['base_url'], api_key=p['api_key'])
                resp = client.chat.completions.create(
                    model=p['model'],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3, max_tokens=500
                )
                article.ai_summary = f"[{prov}] " + resp.choices[0].message.content
                db.session.commit()
                flash(f'Summarized via {prov}.')
                break
            except Exception as e:
                flash(f"{prov}: {str(e)[:150]}")
                continue
    return redirect(url_for('news_detail', aid=article.id))

@app.route('/news/<int:aid>/delete', methods=['POST'])
def news_delete(aid):
    a = NewsArticle.query.get_or_404(aid)
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('news_list'))
# ---------- Interview Module ----------
import re as _re

INTERVIEW_KEYWORDS = {
    "DAF": ["hobby", "hometown", "graduation", "engineering", "medical", "family", "background"],
    "Why IAS": ["why ias", "why civil", "why do you want", "why administration", "motivation"],
    "Situational": ["if you were", "what will you do", "how will you handle", "suppose you"],
    "Current Affairs": ["recent", "current", "2024", "2023", "war", "economy", "climate"],
    "Ethics": ["ethics", "integrity", "honest", "corruption", "moral", "dilemma"],
    "Governance": ["governance", "policy", "administration", "reform", "scheme"],
    "Optional": ["optional", "subject", "paper"],
    "Opinion": ["your view", "your opinion", "do you think", "comment on", "critically"],
}

def tag_interview_topic(q_text):
    t = (q_text or "").lower()
    scores = {k: sum(1 for kw in v if kw in t) for k, v in INTERVIEW_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"

def parse_transcript(raw_text):
    """Split transcript into Q&A pairs using '?' heuristic."""
    lines = []
    for line in raw_text.splitlines():
        m = _re.match(r"\[\s*([\d.]+)s\]\s*(.*)", line)
        if m:
            lines.append((float(m.group(1)), m.group(2).strip()))
    qas = []
    current_q = None
    current_ans = []
    q_start = None
    for t, text in lines:
        if not text:
            continue
        # Heuristic: question if ends with ? OR is short and starts with typical question words
        is_question = (
            text.endswith("?")
            or _re.match(r"^(please|tell me|what|why|how|when|where|who|which|can you|could you|do you|did you|have you|would you|suppose|if you|your)", text, _re.I)
        ) and len(text.split()) < 25
        if is_question:
            if current_q and current_ans:
                qas.append((current_q, " ".join(current_ans), q_start))
            current_q = text
            current_ans = []
            q_start = t
        else:
            if current_q:
                current_ans.append(text)
    if current_q and current_ans:
        qas.append((current_q, " ".join(current_ans), q_start))
    return qas

@app.route('/interview')
def interview_list():
    search = request.args.get('q', '').strip()
    topic = request.args.get('topic', '').strip()
    q = InterviewQA.query
    if search:
        q = q.filter(InterviewQA.question.ilike(f'%{search}%') | InterviewQA.answer.ilike(f'%{search}%'))
    if topic:
        q = q.filter(InterviewQA.topic == topic)
    qas = q.order_by(InterviewQA.id.desc()).limit(300).all()
    transcripts = InterviewTranscript.query.order_by(InterviewTranscript.uploaded_at.desc()).all()
    topics = [t[0] for t in db.session.query(InterviewQA.topic).distinct().all() if t[0]]
    return render_template('interview.html', qas=qas, transcripts=transcripts,
                           topics=topics, search=search, topic=topic)

@app.route('/interview/load', methods=['POST'])
def interview_load():
    """Load a transcript .txt file from the transcripts/ folder into DB."""
    filename = request.form.get('filename', '').strip()
    path = os.path.join('transcripts', filename)
    if not os.path.exists(path):
        flash(f'File not found: {path}')
        return redirect(url_for('interview_list'))

    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()

    tr = InterviewTranscript(
        topper=request.form.get('topper', '').strip(),
        year=int(request.form.get('year') or 0) or None,
        rank=request.form.get('rank', '').strip(),
        optional=request.form.get('optional', '').strip(),
        video_url=request.form.get('video_url', '').strip(),
        filename=filename,
        raw_text=raw
    )
    db.session.add(tr)
    db.session.flush()

    qas = parse_transcript(raw)
    for q_text, a_text, start in qas:
        db.session.add(InterviewQA(
            transcript_id=tr.id,
            question=q_text,
            answer=a_text,
            start_time=start,
            topic=tag_interview_topic(q_text)
        ))
    db.session.commit()
    flash(f'Loaded {len(qas)} Q&A pairs from {filename}.')
    return redirect(url_for('interview_detail', tid=tr.id))

@app.route('/interview/<int:tid>')
def interview_detail(tid):
    tr = InterviewTranscript.query.get_or_404(tid)
    return render_template('interview_detail.html', tr=tr)

@app.route('/interview/<int:tid>/delete', methods=['POST'])
def interview_delete(tid):
    tr = InterviewTranscript.query.get_or_404(tid)
    db.session.delete(tr)
    db.session.commit()
    flash('Transcript deleted.')
    return redirect(url_for('interview_list'))

@app.route('/interview/<int:tid>/pdf')
def interview_pdf(tid):
    from fpdf import FPDF
    tr = InterviewTranscript.query.get_or_404(tid)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, f"Interview Transcript: {tr.topper or tr.filename}")
    pdf.set_font("Helvetica", "", 10)
    meta = f"Year: {tr.year or 'N/A'} | Rank: {tr.rank or 'N/A'} | Optional: {tr.optional or 'N/A'}"
    pdf.multi_cell(0, 6, meta)
    if tr.video_url:
        pdf.multi_cell(0, 6, f"Source: {tr.video_url}")
    pdf.ln(4)
    for i, qa in enumerate(tr.qas, 1):
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 6, f"Q{i}. {qa.question}")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, f"Ans: {qa.answer}")
        pdf.ln(2)
    out_dir = "transcripts"
    out_path = os.path.join(out_dir, f"interview_{tr.id}.pdf")
    pdf.output(out_path)
    return send_from_directory(out_dir, f"interview_{tr.id}.pdf", as_attachment=True)
# ---------- Mains Answer Evaluation ----------
EVAL_SYSTEM = (
    "You are a strict UPSC Mains answer evaluator. Score the student's answer on these 5 parameters "
    "and give each out of 10, then an overall total out of 50:\n"
    "1. Structure (Intro-Body-Conclusion)\n"
    "2. Content Depth (facts, examples, data)\n"
    "3. Keyword Usage (constitutional, economic, social terms)\n"
    "4. Multi-dimensionality (political, social, economic, ethical angles)\n"
    "5. Presentation (clarity, flow, word discipline)\n\n"
    "Also give:\n"
    "- MISSING POINTS: list concepts from the source pack the student didn't cover\n"
    "- STRENGTHS: 2-3 lines\n"
    "- WEAKNESSES: 2-3 lines\n"
    "- MODEL SKELETON: bullet outline they should aim for next time\n\n"
    "End with EXACTLY this line format: 'TOTAL_SCORE: X' where X is a number 0-50.\n"
    "Be honest — do not inflate. UPSC standards are tough."
)

def evaluate_answer(question, student_text):
    sources = build_source_context(question)
    user = (
        f"QUESTION:\n{question.text}\n\n"
        f"MARKS: {question.marks or 'N/A'}\n\n"
        f"STANDARD SOURCE PACK:\n{sources}\n\n"
        f"STUDENT ANSWER:\n{student_text}\n\n"
        f"Evaluate now."
    )
    cfg = load_config()
    for prov, p in cfg.get('providers', {}).items():
        if p.get('api_key'):
            client = OpenAI(base_url=p['base_url'], api_key=p['api_key'])
            resp = client.chat.completions.create(
                model=p['model'],
                messages=[
                    {"role": "system", "content": EVAL_SYSTEM},
                    {"role": "user", "content": user}
                ],
                temperature=0.2,
                max_tokens=2500
            )
            return resp.choices[0].message.content
    raise ValueError("No AI provider configured. Add API key to config.json.")

@app.route('/question/<int:qid>/submit-answer', methods=['POST'])
def submit_student_answer(qid):
    q = Question.query.get_or_404(qid)
    text = request.form.get('student_text', '').strip()
    if len(text.split()) < 30:
        flash('Write at least 30 words.')
        return redirect(url_for('question_detail', qid=q.id))
    try:
        evaluation = evaluate_answer(q, text)
        score = None
        for line in evaluation.splitlines():
            if line.strip().startswith('TOTAL_SCORE:'):
                try:
                    score = float(line.split(':')[1].strip())
                except ValueError:
                    pass
        db.session.add(StudentAnswer(
            question_id=q.id,
            text=text,
            word_count=len(text.split()),
            evaluation=evaluation,
            score=score
        ))
        db.session.commit()
        flash('Answer evaluated.')
    except Exception as e:
        flash(f"Evaluation error: {str(e)[:200]}")
    return redirect(url_for('question_detail', qid=q.id))

@app.route('/student-answer/<int:aid>/delete', methods=['POST'])
def delete_student_answer(aid):
    a = StudentAnswer.query.get_or_404(aid)
    qid = a.question_id
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('question_detail', qid=qid))

@app.route('/my-answers')
def my_answers():
    answers = StudentAnswer.query.order_by(StudentAnswer.created_at.desc()).limit(100).all()
    total = len(answers)
    avg = sum(a.score for a in answers if a.score) / total if total else 0
    return render_template('my_answers.html', answers=answers, total=total, avg=round(avg, 1))
# ---------- PYQ Auto-Extraction ----------
EXTRACT_SYSTEM = (
    "You extract UPSC past paper questions from raw OCR text. "
    "Return ONLY valid JSON. No markdown fences, no explanation. "
    "Format: {\"questions\": [{\"number\": \"1\", \"text\": \"full question text\", "
    "\"topic\": \"short syllabus topic\", \"marks\": 2, \"qtype\": \"MCQ\"}]}. "
    "Rules:\n"
    "- qtype must be exactly one of: MCQ, GS, Essay, Ethics\n"
    "- marks: 2 for MCQ (Prelims); 10 or 15 for Mains GS; 125 or 250 for Essay\n"
    "- topic: 2-4 word syllabus topic like 'Fundamental Rights', 'Monsoon', 'Federalism'\n"
    "- Skip fragments or cut-off questions\n"
    "- Extract up to 100 questions maximum\n"
    "- If number is unclear, infer sequentially 1,2,3..."
)

def ai_extract_questions(raw_text):
    cfg = load_config()
    # Prefer groq, else first configured provider
    p = cfg.get('providers', {}).get('groq')
    if not p or not p.get('api_key'):
        for v in cfg.get('providers', {}).values():
            if v.get('api_key'):
                p = v
                break
    if not p:
        raise ValueError("No AI provider configured. Add Groq key in config.json.")

    client = OpenAI(base_url=p['base_url'], api_key=p['api_key'])
    text = raw_text[:14000]  # cap for token limits

    # Try with JSON mode first (Groq supports this)
    try:
        resp = client.chat.completions.create(
            model=p['model'],
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
    except Exception:
        # Fallback without JSON mode
        resp = client.chat.completions.create(
            model=p['model'],
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            max_tokens=4000
        )

    content = resp.choices[0].message.content or ''
    # Strip markdown fences if any
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    return json.loads(content)

@app.route('/paper/<int:book_id>/auto-extract', methods=['POST'])
def auto_extract_questions(book_id):
    book = Book.query.get_or_404(book_id)
    if book.category != 'paper':
        flash('Auto-extract works only on Past Papers. Set category to "Past Paper" first.')
        return redirect(url_for('book_detail', book_id=book_id))

    pages = Page.query.filter_by(book_id=book.id).order_by(Page.page_number).all()
    if not pages:
        flash('No pages found. Upload a PDF first.')
        return redirect(url_for('book_detail', book_id=book_id))

    raw = "\n\n".join((p.text or '') for p in pages)
    if len(raw) < 200:
        flash('Paper has too little text. Try re-uploading with "Use OCR" checked.')
        return redirect(url_for('book_detail', book_id=book_id))

    # Try to detect year from title
    year_match = re.search(r'(20\d{2})', book.title or '')
    auto_year = int(year_match.group(1)) if year_match else None

    try:
        result = ai_extract_questions(raw)
    except Exception as e:
        flash(f'Extraction failed: {str(e)[:200]}')
        return redirect(url_for('book_detail', book_id=book_id))

    qs = result.get('questions', [])
    if not qs:
        flash('AI returned zero questions. Try again or check the paper text.')
        return redirect(url_for('book_detail', book_id=book_id))

    added = 0
    skipped = 0
    for qd in qs:
        text = (qd.get('text') or '').strip()
        if len(text) < 10:
            skipped += 1
            continue
        # Skip if already exists (same paper + same text start)
        existing = Question.query.filter(
            Question.paper_id == book.id,
            Question.text.startswith(text[:60])
        ).first()
        if existing:
            skipped += 1
            continue

        marks_val = qd.get('marks')
        try:
            marks_int = int(marks_val) if marks_val else None
        except (ValueError, TypeError):
            marks_int = None

        db.session.add(Question(
            paper_id=book.id,
            question_number=str(qd.get('number', ''))[:20],
            text=text,
            topic=(qd.get('topic') or '')[:200],
            year=auto_year,
            marks=marks_int,
            qtype=(qd.get('qtype') or '')[:50]
        ))
        added += 1

    db.session.commit()
    flash(f'Auto-extracted {added} questions ({skipped} skipped/duplicate).')
    return redirect(url_for('book_detail', book_id=book_id))
# ---------- Adaptive Mock Tests ----------
import random as _random

@app.route('/mock/create', methods=['POST'])
def mock_create():
    num = int(request.form.get('num_questions') or 20)
    mode = request.form.get('mode', 'weighted')

    # Only MCQ questions with a topic
    pool = Question.query.filter(Question.qtype == 'MCQ').all()
    if len(pool) < 5:
        flash(f'Need at least 5 MCQs in the bank. You have {len(pool)}. Auto-extract more past papers first.')
        return redirect(url_for('mock_list'))

    if mode == 'weighted':
        # Weight by topic frequency (higher freq = more likely to be picked)
        topic_freq = Counter(q.topic for q in pool if q.topic)
        weights = [topic_freq.get(q.topic, 1) for q in pool]
    else:
        weights = [1] * len(pool)

    num = min(num, len(pool))
    picked = _random.choices(pool, weights=weights, k=num)
    # Dedupe
    seen = set()
    unique = []
    for q in picked:
        if q.id not in seen:
            unique.append(q)
            seen.add(q.id)
    # Fill if dedupe removed too many
    if len(unique) < num:
        remaining = [q for q in pool if q.id not in seen]
        _random.shuffle(remaining)
        unique.extend(remaining[:num - len(unique)])

    mock = MockTest(name=f'Mock {MockTest.query.count() + 1}', total_questions=len(unique))
    db.session.add(mock)
    db.session.flush()
    for q in unique:
        db.session.add(MockItem(mock_id=mock.id, question_id=q.id))
    db.session.commit()
    return redirect(url_for('mock_take', mid=mock.id))

@app.route('/mock')
def mock_list():
    mocks = MockTest.query.order_by(MockTest.created_at.desc()).all()
    return render_template('mock_list.html', mocks=mocks)

@app.route('/mock/<int:mid>')
def mock_take(mid):
    mock = MockTest.query.get_or_404(mid)
    return render_template('mock_take.html', mock=mock)

@app.route('/mock/<int:mid>/submit', methods=['POST'])
def mock_submit(mid):
    mock = MockTest.query.get_or_404(mid)
    correct_count = 0
    for item in mock.items:
        ans = request.form.get(f'q_{item.id}', '').strip().upper()
        item.user_answer = ans
        # Simple correct detection: if answer text contains key phrases,
        # fallback to comparing letters if question has "(a)/(b)/(c)/(d)"
        # We can't auto-grade without a known answer key, so skip auto-scoring
        # We mark as None; student reviews manually
        item.correct = None
    db.session.commit()
    flash('Responses saved. Review and self-grade below.')
    return redirect(url_for('mock_review', mid=mock.id))

@app.route('/mock/<int:mid>/review')
def mock_review(mid):
    mock = MockTest.query.get_or_404(mid)
    return render_template('mock_review.html', mock=mock)

@app.route('/mock/<int:mid>/delete', methods=['POST'])
def mock_delete(mid):
    m = MockTest.query.get_or_404(mid)
    db.session.delete(m)
    db.session.commit()
    flash('Mock deleted.')
    return redirect(url_for('mock_list'))
# ---------- Exam Simulator ----------
import random as _rand

EXAM_GEN_SYSTEM = (
    "You are a UPSC exam paper setter. Generate questions in strict JSON. "
    "Return ONLY valid JSON, no markdown, no explanation outside the JSON. "
    "Output format depends on the exam mode given."
)

def _get_client():
    cfg = load_config()
    p = cfg.get('providers', {}).get('groq')
    if not p or not p.get('api_key'):
        for v in cfg.get('providers', {}).values():
            if v.get('api_key'):
                p = v
                break
    if not p:
        raise ValueError("No AI provider configured.")
    return OpenAI(base_url=p['base_url'], api_key=p['api_key']), p['model']

def _json_from_ai(messages, max_tokens=4000):
    client, model = _get_client()
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.6,
            max_tokens=max_tokens, response_format={"type": "json_object"}
        )
    except Exception:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.6, max_tokens=max_tokens
        )
    c = (resp.choices[0].message.content or '').strip()
    if c.startswith("```"):
        c = c.split("```")[1]
        if c.startswith("json"):
            c = c[4:]
        c = c.strip()
    return json.loads(c)

def _top_pyq_topics(limit=20):
    qs = Question.query.filter(Question.topic.isnot(None)).all()
    c = Counter(q.topic for q in qs if q.topic)
    return [t for t, _ in c.most_common(limit)]

def _recent_news_headlines(limit=15):
    arts = NewsArticle.query.order_by(NewsArticle.fetched_at.desc()).limit(limit).all()
    return [a.title for a in arts]

def generate_exam_questions(mode, num, topics, news):
    """Return list of question dicts."""
    if mode == 'prelims':
        system = EXAM_GEN_SYSTEM + (
            " For PRELIMS: output {\"questions\":[{\"text\":\"...\",\"topic\":\"...\","
            "\"option_a\":\"...\",\"option_b\":\"...\",\"option_c\":\"...\",\"option_d\":\"...\","
            "\"correct_option\":\"A|B|C|D\",\"explanation\":\"2-3 lines\"}]}"
        )
        user = (
            f"Generate {num} UPSC Prelims-style MCQs. Each question must have 4 options "
            f"and one correct answer.\n\nFocus on these high-probability topics: {topics}\n\n"
            f"Weave in current affairs where relevant: {news}"
        )
    elif mode == 'mains':
        system = EXAM_GEN_SYSTEM + (
            " For MAINS: output {\"questions\":[{\"text\":\"...\",\"topic\":\"...\","
            "\"marks\":10,\"reference_answer\":\"structured model answer in 250 words\"}]}"
        )
        user = (
            f"Generate {num} UPSC Mains GS questions (10 or 15 marks). "
            f"Mix directive words: discuss, examine, analyse, comment.\n\n"
            f"High-probability topics: {topics}\n\nCurrent context: {news}"
        )
    else:  # essay
        system = EXAM_GEN_SYSTEM + (
            " For ESSAY: output {\"questions\":[{\"text\":\"...\",\"topic\":\"...\","
            "\"marks\":125,\"reference_answer\":\"3-paragraph essay skeleton\"}]}"
        )
        user = (
            f"Generate {num} UPSC Essay paper topics (philosophical / contemporary). "
            f"Each essay is 1000-1200 words, 125 marks.\n\nContext: {news}"
        )
    return _json_from_ai([
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]).get("questions", [])

@app.route('/exam')
def exam_list():
    exams = ExamSim.query.order_by(ExamSim.created_at.desc()).all()
    return render_template('exam_list.html', exams=exams)

@app.route('/exam/new', methods=['POST'])
def exam_new():
    mode = request.form.get('mode', 'prelims')
    try:
        num = int(request.form.get('num') or 10)
        dur = int(request.form.get('duration') or 60)
        per_q = int(request.form.get('per_q') or 60)
    except ValueError:
        flash('Invalid number.')
        return redirect(url_for('exam_list'))

    topics = _top_pyq_topics()
    news = _recent_news_headlines()

    try:
        qs = generate_exam_questions(mode, num, topics, news)
    except Exception as e:
        flash(f'AI generation failed: {str(e)[:200]}')
        return redirect(url_for('exam_list'))
    if not qs:
        flash('AI returned 0 questions. Retry.')
        return redirect(url_for('exam_list'))

    name = f'{mode.title()} Mock — {ExamSim.query.count() + 1}'
    exam = ExamSim(name=name, mode=mode, duration_minutes=dur,
                   per_question_seconds=per_q, total_questions=len(qs))
    db.session.add(exam)
    db.session.flush()
    max_score = 0
    for i, q in enumerate(qs, 1):
        marks = int(q.get('marks') or (2 if mode == 'prelims' else 10))
        max_score += marks
        db.session.add(ExamSimQuestion(
            exam_id=exam.id, q_number=i,
            text=q.get('text', ''),
            topic=q.get('topic', ''),
            marks=marks,
            option_a=q.get('option_a', ''),
            option_b=q.get('option_b', ''),
            option_c=q.get('option_c', ''),
            option_d=q.get('option_d', ''),
            correct_option=(q.get('correct_option') or '').upper()[:1],
            explanation=q.get('explanation', ''),
            reference_answer=q.get('reference_answer', '')
        ))
    exam.max_score = max_score
    db.session.commit()
    return redirect(url_for('exam_take', eid=exam.id))

@app.route('/exam/<int:eid>')
def exam_take(eid):
    exam = ExamSim.query.get_or_404(eid)
    return render_template('exam_take.html', exam=exam)

@app.route('/exam/<int:eid>/submit', methods=['POST'])
def exam_submit(eid):
    exam = ExamSim.query.get_or_404(eid)
    for item in exam.items:
        ans = request.form.get(f'q_{item.id}', '').strip()
        tt = request.form.get(f't_{item.id}', '').strip()
        item.user_answer = ans
        try:
            item.time_taken = float(tt) if tt else None
        except ValueError:
            item.time_taken = None

    # Auto-score prelims
    if exam.mode == 'prelims':
        total = 0
        for item in exam.items:
            ua = (item.user_answer or '').upper()[:1]
            ca = (item.correct_option or '').upper()[:1]
            if ua and ua == ca:
                item.score = item.marks
                total += item.marks
            else:
                item.score = 0
        exam.total_score = total
        exam.status = 'evaluated'
    else:
        exam.status = 'submitted'
    db.session.commit()
    return redirect(url_for('exam_result', eid=exam.id))

@app.route('/exam/<int:eid>/evaluate', methods=['POST'])
def exam_evaluate(eid):
    """AI evaluates Mains/Essay answers."""
    exam = ExamSim.query.get_or_404(eid)
    total = 0.0
    for item in exam.items:
        if not item.user_answer:
            item.score = 0
            item.feedback = 'Not attempted.'
            continue
        prompt = (
            f"QUESTION:\n{item.text}\n\nMARKS: {item.marks}\n\n"
            f"REFERENCE ANSWER (for your calibration only):\n{(item.reference_answer or '')[:2500]}\n\n"
            f"STUDENT ANSWER:\n{item.user_answer[:3500]}\n\n"
            "Evaluate strictly on UPSC standards. Give:\n"
            "- Strengths (2 lines)\n- Weaknesses (2 lines)\n"
            "- Missing points\n- What score out of the max marks would you give.\n\n"
            f"End with EXACTLY: SCORE: X  (X is number 0-{item.marks})"
        )
        try:
            client, model = _get_client()
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=1200
            )
            fb = r.choices[0].message.content or ''
            item.feedback = fb
            # Parse score
            for line in fb.splitlines():
                if 'SCORE:' in line.upper():
                    try:
                        item.score = float(line.split(':')[-1].strip().split()[0])
                    except Exception:
                        item.score = 0
                    break
            else:
                item.score = 0
        except Exception as e:
            item.feedback = f"Evaluation failed: {str(e)[:150]}"
            item.score = 0
        total += (item.score or 0)

    exam.total_score = total
    exam.status = 'evaluated'
    db.session.commit()
    flash('Evaluation complete.')
    return redirect(url_for('exam_result', eid=exam.id))

@app.route('/exam/<int:eid>/result')
def exam_result(eid):
    exam = ExamSim.query.get_or_404(eid)
    return render_template('exam_result.html', exam=exam)

@app.route('/exam/<int:eid>/delete', methods=['POST'])
def exam_delete(eid):
    e = ExamSim.query.get_or_404(eid)
    db.session.delete(e)
    db.session.commit()
    return redirect(url_for('exam_list'))
# ---------- Study Plan Generator ----------
PLAN_SYSTEM = (
    "You are a UPSC mentor. Generate a day-by-day study plan in strict JSON. "
    "Return ONLY valid JSON. Format: "
    "{\"weeks\":[{\"week\":1,\"theme\":\"Foundation - Polity\",\"days\":["
    "{\"day\":1,\"date_offset\":0,\"morning\":\"...\",\"afternoon\":\"...\",\"evening\":\"...\","
    "\"test\":\"...\",\"revision\":\"...\"}]}]}. "
    "Each day must have 4 slots. Include revision every 7 days and a full-length test weekly. "
    "Respect the total weeks based on days_remaining. Be realistic."
)

@app.route('/study-plan')
def study_plan_list():
    plans = StudyPlan.query.order_by(StudyPlan.created_at.desc()).all()
    # Get current stats to show pre-fill hints
    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]
    return render_template('study_plan_list.html', plans=plans, subjects=subjects)

@app.route('/study-plan/new', methods=['POST'])
def study_plan_new():
    from datetime import datetime as _dt
    try:
        exam_date_str = request.form.get('exam_date', '').strip()
        hours = int(request.form.get('hours') or 6)
    except ValueError:
        flash('Invalid input.')
        return redirect(url_for('study_plan_list'))

    subjects = request.form.getlist('subjects')
    weak = request.form.get('weak', '').strip()
    name = request.form.get('name') or f'Plan {StudyPlan.query.count() + 1}'

    try:
        exam_date = _dt.strptime(exam_date_str, '%Y-%m-%d')
    except ValueError:
        flash('Enter a valid date (YYYY-MM-DD).')
        return redirect(url_for('study_plan_list'))

    today = _dt.now()
    days_left = max(1, (exam_date - today).days)
    weeks_left = max(1, days_left // 7)

    # Gather context: PYQ topics, news, books
    topics = _top_pyq_topics(30)
    news = _recent_news_headlines(10)
    subjects_str = ', '.join(subjects) if subjects else 'Full UPSC syllabus'

    user = (
        f"Days left: {days_left} ({weeks_left} weeks)\n"
        f"Hours per day available: {hours}\n"
        f"Subjects to cover: {subjects_str}\n"
        f"Student's weak areas: {weak or 'not specified'}\n"
        f"High-probability topics from PYQ data: {topics}\n"
        f"Current affairs to weave in: {news}\n\n"
        f"Generate a {weeks_left}-week plan. Each week has 7 days. "
        f"Allocate more time to weak areas. Include daily revision + weekly test. "
        f"Total daily time = {hours} hours split across morning/afternoon/evening/test."
    )

    try:
        result = _json_from_ai([
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": user}
        ], max_tokens=6000)
    except Exception as e:
        flash(f'Plan generation failed: {str(e)[:200]}')
        return redirect(url_for('study_plan_list'))

    plan = StudyPlan(
        name=name, exam_date=exam_date_str, hours_per_day=hours,
        subjects=subjects_str, weak_areas=weak,
        plan_json=json.dumps(result)
    )
    db.session.add(plan)
    db.session.commit()
    flash(f'Plan generated for {weeks_left} weeks.')
    return redirect(url_for('study_plan_view', pid=plan.id))

@app.route('/study-plan/<int:pid>')
def study_plan_view(pid):
    plan = StudyPlan.query.get_or_404(pid)
    try:
        data = json.loads(plan.plan_json or '{}')
    except json.JSONDecodeError:
        data = {}
    return render_template('study_plan_view.html', plan=plan, data=data)

@app.route('/study-plan/<int:pid>/delete', methods=['POST'])
def study_plan_delete(pid):
    p = StudyPlan.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('study_plan_list'))
# ---------- Voice Interview Sim ----------
from faster_whisper import WhisperModel as _WM
import threading as _threading

_WHISPER = None
_WHISPER_LOCK = _threading.Lock()

def _get_whisper():
    global _WHISPER
    with _WHISPER_LOCK:
        if _WHISPER is None:
            _WHISPER = _WM("tiny", device="cpu", compute_type="int8")
        return _WHISPER

FILLERS = ["umm", "uhh", "uh", "um", "like", "you know", "actually", "basically",
           "so yeah", "kind of", "sort of", "i mean", "whatever"]

INTERVIEW_QUESTIONS = [
    ("Why do you want to become an IAS officer?", "Motivation"),
    ("Tell us about yourself.", "DAF"),
    ("What are your hobbies and how do they help you?", "DAF"),
    ("You are posted in a district facing a Maoist insurgency. What will you do?", "Situational"),
    ("What is your opinion on the recent farm laws?", "Current Affairs"),
    ("How would you handle a situation where your senior asks you to do something unethical?", "Ethics"),
    ("Your home state has poor education outcomes. As DM, how will you improve?", "Governance"),
    ("What is the biggest challenge India faces today?", "Opinion"),
    ("If you were the District Collector during a flood, what would be your priorities?", "Situational"),
    ("Why did you choose your optional subject?", "Optional"),
    ("What is the difference between a leader and a manager in civil services?", "Ethics"),
    ("You are a woman IAS officer posted in a conservative district. How will you handle it?", "Situational"),
    ("What does 'Constitutional Morality' mean to you?", "Ethics"),
    ("Who is your role model and why?", "DAF"),
    ("If you fail this interview, what will you do?", "Opinion"),
]

@app.route('/interview-sim')
def interview_sim_list():
    sims = InterviewSim.query.order_by(InterviewSim.created_at.desc()).all()
    return render_template('interview_sim_list.html', sims=sims, questions=INTERVIEW_QUESTIONS)

@app.route('/interview-sim/new')
def interview_sim_new():
    import random as _r
    q = _r.choice(INTERVIEW_QUESTIONS)
    return render_template('interview_sim_record.html', question=q[0], category=q[1])

@app.route('/interview-sim/record', methods=['POST'])
def interview_sim_record():
    question = request.form.get('question', '').strip()
    category = request.form.get('category', '').strip()
    duration = float(request.form.get('duration') or 0)

    if 'audio' not in request.files:
        flash('No audio received.')
        return redirect(url_for('interview_sim_list'))

    audio = request.files['audio']
    if not audio or audio.filename == '':
        flash('Empty recording.')
        return redirect(url_for('interview_sim_list'))

    # Save audio
    os.makedirs('interview_audio', exist_ok=True)
    fname = f"rec_{int(__import__('time').time())}.webm"
    path = os.path.join('interview_audio', fname)
    audio.save(path)

    # Transcribe
    try:
        model = _get_whisper()
        segments, info = model.transcribe(path, beam_size=1, language="en", vad_filter=True)
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as e:
        flash(f'Transcription error: {str(e)[:200]}')
        return redirect(url_for('interview_sim_list'))

    # Analyze metrics
    lower = transcript.lower()
    filler_count = sum(lower.count(f) for f in FILLERS)
    words = len(transcript.split())
    wpm = (words / (duration / 60.0)) if duration > 0 else 0

    # AI evaluation
    prompt = (
        f"You are a UPSC interview board member. Evaluate this candidate's answer.\n\n"
        f"QUESTION: {question}\n"
        f"CATEGORY: {category}\n"
        f"DURATION: {duration:.0f} seconds\n"
        f"WORDS PER MINUTE: {wpm:.0f} (ideal: 120-160)\n"
        f"FILLER WORDS: {filler_count} (lower is better)\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        "Score on 5 parameters, each out of 10:\n"
        "1. Content Depth (facts, examples, structure)\n"
        "2. Communication Clarity (unambiguous, structured)\n"
        "3. Confidence (no hedging, direct answers)\n"
        "4. Relevance to question\n"
        "5. Overall impression on the board\n\n"
        "Also give:\n"
        "- STRENGTHS (2-3 lines)\n"
        "- WEAKNESSES (2-3 lines)\n"
        "- SUGGESTED BETTER ANSWER (bullet outline)\n\n"
        f"End with EXACTLY: SCORE: X  (X = total out of 50)"
    )
    try:
        client, model_name = _get_client()
        r = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=1500
        )
        feedback = r.choices[0].message.content or ''
        score = None
        for line in feedback.splitlines():
            if 'SCORE:' in line.upper():
                try:
                    score = float(line.split(':')[-1].strip().split()[0])
                except Exception:
                    pass
                break
    except Exception as e:
        feedback = f"AI evaluation failed: {str(e)[:200]}"
        score = None

    sim = InterviewSim(
        question=question, category=category,
        audio_path=path, transcript=transcript,
        duration_sec=duration, words_per_min=wpm, filler_count=filler_count,
        ai_feedback=feedback, score=score
    )
    db.session.add(sim)
    db.session.commit()
    return redirect(url_for('interview_sim_view', sid=sim.id))

@app.route('/interview-sim/<int:sid>')
def interview_sim_view(sid):
    sim = InterviewSim.query.get_or_404(sid)
    return render_template('interview_sim_view.html', sim=sim)

@app.route('/interview-sim/<int:sid>/audio')
def interview_sim_audio(sid):
    sim = InterviewSim.query.get_or_404(sid)
    return send_from_directory('interview_audio', os.path.basename(sim.audio_path))

@app.route('/interview-sim/<int:sid>/delete', methods=['POST'])
def interview_sim_delete(sid):
    sim = InterviewSim.query.get_or_404(sid)
    try:
        os.remove(sim.audio_path)
    except OSError:
        pass
    db.session.delete(sim)
    db.session.commit()
    return redirect(url_for('interview_sim_list'))
# ---------- Topper Database ----------
import json as _json

@app.route('/toppers')
def toppers_list():
    year_filter = request.args.get('year', '').strip()
    search = request.args.get('q', '').strip()

    q = Topper.query
    if year_filter:
        try:
            q = q.filter(Topper.year == int(year_filter))
        except ValueError:
            pass
    if search:
        q = q.filter(Topper.name.ilike(f'%{search}%'))

    toppers = q.order_by(Topper.year.desc(), Topper.rank.asc()).limit(500).all()
    years = sorted([y[0] for y in db.session.query(Topper.year).distinct().all() if y[0]], reverse=True)

    return render_template('toppers_list.html', toppers=toppers, years=years,
                           year=year_filter, search=search)

@app.route('/topper/<int:tid>')
def topper_detail(tid):
    topper = Topper.query.get_or_404(tid)
    paper_marks = {}
    if topper.paper_marks_json:
        try:
            paper_marks = _json.loads(topper.paper_marks_json)
        except Exception:
            pass
    return render_template('topper_detail.html', topper=topper, paper_marks=paper_marks)

@app.route('/toppers/admin')
def toppers_admin():
    toppers = Topper.query.order_by(Topper.year.desc(), Topper.rank.asc()).all()
    return render_template('toppers_admin.html', toppers=toppers)

@app.route('/topper/add', methods=['POST'])
def topper_add():
    try:
        year = int(request.form.get('year') or 0)
        rank = int(request.form.get('rank') or 0)
    except ValueError:
        flash('Year and Rank must be numbers.')
        return redirect(url_for('toppers_admin'))

    name = request.form.get('name', '').strip()
    if not name or not year or not rank:
        flash('Year, Rank, and Name are required.')
        return redirect(url_for('toppers_admin'))

    # Build paper_marks_json from optional fields
    paper_marks = {}
    for key in ['essay', 'gs1', 'gs2', 'gs3', 'gs4', 'optional1', 'optional2']:
        val = request.form.get(f'paper_{key}', '').strip()
        if val:
            try:
                paper_marks[key] = float(val)
            except ValueError:
                pass

    t = Topper(
        year=year,
        rank=rank,
        name=name,
        roll_no=request.form.get('roll_no', '').strip(),
        category=request.form.get('category', '').strip(),
        optional_subject=request.form.get('optional_subject', '').strip(),
        attempt=request.form.get('attempt', '').strip(),
        written_marks=float(request.form.get('written_marks') or 0) or None,
        interview_marks=float(request.form.get('interview_marks') or 0) or None,
        total_marks=float(request.form.get('total_marks') or 0) or None,
        paper_marks_json=_json.dumps(paper_marks) if paper_marks else None
    )
    db.session.add(t)
    db.session.commit()
    flash(f'Topper "{name}" added for {year}.')
    return redirect(url_for('toppers_admin'))

@app.route('/topper/<int:tid>/edit', methods=['POST'])
def topper_edit(tid):
    t = Topper.query.get_or_404(tid)
    try:
        t.year = int(request.form.get('year') or t.year)
        t.rank = int(request.form.get('rank') or t.rank)
    except ValueError:
        pass
    t.name = request.form.get('name', t.name).strip()
    t.roll_no = request.form.get('roll_no', t.roll_no).strip()
    t.category = request.form.get('category', t.category).strip()
    t.optional_subject = request.form.get('optional_subject', t.optional_subject).strip()
    t.attempt = request.form.get('attempt', t.attempt).strip()
    t.written_marks = float(request.form.get('written_marks') or 0) or None
    t.interview_marks = float(request.form.get('interview_marks') or 0) or None
    t.total_marks = float(request.form.get('total_marks') or 0) or None

    paper_marks = {}
    for key in ['essay', 'gs1', 'gs2', 'gs3', 'gs4', 'optional1', 'optional2']:
        val = request.form.get(f'paper_{key}', '').strip()
        if val:
            try:
                paper_marks[key] = float(val)
            except ValueError:
                pass
    t.paper_marks_json = _json.dumps(paper_marks) if paper_marks else None

    db.session.commit()
    flash('Topper updated.')
    return redirect(url_for('toppers_admin'))

@app.route('/topper/<int:tid>/delete', methods=['POST'])
def topper_delete(tid):
    t = Topper.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    flash('Topper deleted.')
    return redirect(url_for('toppers_admin'))
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Database initialized.')

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)