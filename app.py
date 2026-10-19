from dotenv import load_dotenv
load_dotenv('/home/umadivy500/ias_machine/.env')

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

if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ias-machine-secret-2026'
app.config['UPLOAD_FOLDER'] = 'uploads'
import os as _o_db; from dotenv import load_dotenv; load_dotenv(); app.config['SQLALCHEMY_DATABASE_URI'] = _o_db.environ.get('DATABASE_URL') or 'sqlite:///ias_machine_v2.db'
from sqlalchemy.pool import NullPool as _NP
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 60, 'poolclass': _NP}
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
    category = db.Column(db.String(50))
    collection = db.Column(db.String(30))
    year = db.Column(db.Integer)
    sub_subject = db.Column(db.String(100))
    ocr_status = db.Column(db.String(30))
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

class SelectionStat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    stage = db.Column(db.String(50), nullable=False)
    count = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(200))


class CommonMistake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stage = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    fix = db.Column(db.Text)
    source = db.Column(db.String(200))
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
    paper_marks_json = db.Column(db.Text)
    photo_url = db.Column(db.String(500))  # JSON: {"essay": 117, "gs1": 104, ...}
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




class StudyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)
    hits = db.Column(db.Integer, default=1)

class SyllabusNode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('syllabus_node.id'), nullable=True)
    stage = db.Column(db.String(20))       # Prelims, Mains, Interview
    level = db.Column(db.String(20))       # stage, subject, topic
    name = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(20), default='Not Started')
    notes = db.Column(db.Text)
    target_date = db.Column(db.String(20))
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    children = db.relationship('SyllabusNode',
        backref=db.backref('parent', remote_side=[id]),
        cascade='all, delete-orphan')
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
    return library_view()


@app.route('/library')
def library_home():
    return library_view()


def library_view():
    from sqlalchemy import func as _f, case as _c
    col = request.args.get('collection', '').strip().upper()
    year_filter = request.args.get('year', '').strip()
    subj_filter = request.args.get('subject', '').strip()

    q = Book.query
    if col:
        q = q.filter(Book.collection == col)
    if year_filter:
        try:
            q = q.filter(Book.year == int(year_filter))
        except ValueError:
            pass
    if subj_filter:
        q = q.filter(Book.subject == subj_filter)

    books = q.order_by(Book.uploaded_at.desc()).limit(500).all()

    # Collection counts (for tabs)
    counts_rows = db.session.query(Book.collection, _f.count(Book.id)).group_by(Book.collection).all()
    collection_counts = {k: v for k, v in counts_rows if k}
    total_count = Book.query.count()

    # Distinct years + subjects
    years = sorted([y[0] for y in db.session.query(Book.year).distinct().all() if y[0]], reverse=True)
    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]

    return render_template('index.html',
                           books=books,
                           collections=LIBRARY_COLLECTIONS,
                           collection_counts=collection_counts,
                           total_count=total_count,
                           years=years,
                           subjects=subjects)

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

    _col = (request.form.get('collection') or '').strip().upper()
    book = Book(
        title=request.form.get('title') or filename,
        author=request.form.get('author', ''),
        subject=request.form.get('subject', ''),
        topic=request.form.get('topic', ''),
        category=request.form.get('category', 'book'),
        collection=_col if _col else None,
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
    # Topper phrase injection
    subj_hint = ''
    try:
        subj = question.paper.subject if question.paper and question.paper.subject else ''
        phrases = _get_phrases_for_subject(subj, 8)
        if phrases:
            subj_hint = "\n\nPREFER THESE EXAMINER-REWARDED PHRASES (weave naturally): " + ', '.join(phrases)
    except Exception:
        pass
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
        + subj_hint
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
    {"name": "Google News – UPSC", "url": "https://news.google.com/rss/search?q=India+policy+scheme+when:7d&hl=en-IN&gl=IN&ceid=IN:en"},
    {"name": "Google News – Economy", "url": "https://news.google.com/rss/search?q=India+economy+RBI+GDP+when:7d&hl=en-IN&gl=IN&ceid=IN:en"},
    {"name": "Google News – Environment", "url": "https://news.google.com/rss/search?q=India+climate+environment+wildlife+when:7d&hl=en-IN&gl=IN&ceid=IN:en"},
    {"name": "Google News – International", "url": "https://news.google.com/rss/search?q=India+foreign+relations+treaty+summit+when:7d&hl=en-IN&gl=IN&ceid=IN:en"},
    {"name": "Google News – Polity", "url": "https://news.google.com/rss/search?q=Parliament+Supreme+Court+constitution+India+when:7d&hl=en-IN&gl=IN&ceid=IN:en"},
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
                max_tokens=8000
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
    total_with_key = 0
    for item in mock.items:
        ans = request.form.get(f'q_{item.id}', '').strip().upper()[:1]
        item.user_answer = ans
        correct = item.question.correct_answer
        if correct:
            total_with_key += 1
            item.correct = (ans == correct)
            if item.correct:
                correct_count += 1
        else:
            item.correct = None
    db.session.commit()
    if total_with_key:
        flash(f'Score: {correct_count}/{total_with_key} correct. ({total_with_key - correct_count} wrong)')
    else:
        flash('No answer keys set for these questions. Add keys in /mcq/key.')
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
import threading as _threading

_WHISPER = None
_WHISPER_LOCK = _threading.Lock()

def _get_whisper():
    global _WHISPER
    with _WHISPER_LOCK:
        if _WHISPER is None:
            try:
                from faster_whisper import WhisperModel as _WM
            except ImportError:
                raise RuntimeError("Voice transcription is not available on this server. Use the laptop version for voice features.")
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

    photo_url = request.form.get('photo_url', '').strip()
    # Handle file upload
    if 'photo_file' in request.files:
        pf = request.files['photo_file']
        if pf and pf.filename:
            os.makedirs('static/topper_photos', exist_ok=True)
            fname = secure_filename(f"{year}_{rank}_{pf.filename}")
            pf.save(os.path.join('static/topper_photos', fname))
            photo_url = f'/static/topper_photos/{fname}'

    t = Topper(
        year=year,
        rank=rank,
        name=name,
        photo_url=photo_url,
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
    if request.form.get('photo_url', '').strip():
        t.photo_url = request.form.get('photo_url', '').strip()
    if 'photo_file' in request.files:
        pf = request.files['photo_file']
        if pf and pf.filename:
            os.makedirs('static/topper_photos', exist_ok=True)
            fname = secure_filename(f"{t.year}_{t.rank}_{pf.filename}")
            pf.save(os.path.join('static/topper_photos', fname))
            t.photo_url = f'/static/topper_photos/{fname}'
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


# ---------- Selection Statistics ----------
@app.route('/selection')
def selection_stats():
    from collections import defaultdict
    rows = SelectionStat.query.order_by(SelectionStat.year.desc(), SelectionStat.id.asc()).all()
    by_year = defaultdict(list)
    for r in rows:
        by_year[r.year].append({"stage": r.stage, "count": r.count, "note": r.note})
    years = sorted(by_year.keys(), reverse=True)
    return render_template('selection.html', by_year=dict(by_year), years=years)

@app.route('/selection/add', methods=['POST'])
def selection_add():
    try:
        year = int(request.form.get('year'))
        count = int(request.form.get('count'))
    except (ValueError, TypeError):
        flash('Year and count must be numbers.')
        return redirect(url_for('selection_stats'))
    stage = request.form.get('stage', '').strip()
    if not stage or not year:
        flash('Year and stage required.')
        return redirect(url_for('selection_stats'))
    existing = SelectionStat.query.filter_by(year=year, stage=stage).first()
    if existing:
        existing.count = count
        existing.note = request.form.get('note', '')
    else:
        db.session.add(SelectionStat(
            year=year, stage=stage, count=count,
            note=request.form.get('note', '')
        ))
    db.session.commit()
    flash(f'Saved {year} / {stage}.')
    return redirect(url_for('selection_stats'))

@app.route('/selection/<int:sid>/delete', methods=['POST'])
def selection_delete(sid):
    s = SelectionStat.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    return redirect(url_for('selection_stats'))



# ---------- Common Mistakes ----------
@app.route('/mistakes')
def mistakes_list():
    stage = request.args.get('stage', '').strip()
    q = CommonMistake.query
    if stage:
        q = q.filter(CommonMistake.stage == stage)
    mistakes = q.order_by(CommonMistake.stage.asc(), CommonMistake.id.desc()).all()
    stages = sorted({m.stage for m in CommonMistake.query.all()})
    return render_template('mistakes.html', mistakes=mistakes, stages=stages, stage=stage)

@app.route('/mistakes/add', methods=['POST'])
def mistake_add():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    stage = request.form.get('stage', '').strip()
    if not title or not description or not stage:
        flash('Stage, title, description required.')
        return redirect(url_for('mistakes_list'))
    db.session.add(CommonMistake(
        stage=stage, title=title, description=description,
        fix=request.form.get('fix', '').strip(),
        source=request.form.get('source', '').strip()
    ))
    db.session.commit()
    flash('Mistake added.')
    return redirect(url_for('mistakes_list'))

@app.route('/mistakes/<int:mid>/delete', methods=['POST'])
def mistake_delete(mid):
    m = CommonMistake.query.get_or_404(mid)
    db.session.delete(m)
    db.session.commit()
    return redirect(url_for('mistakes_list'))



# ---------- Topper Comparison ----------
@app.route('/toppers/compare')
def toppers_compare():
    t1 = request.args.get('t1', '').strip()
    t2 = request.args.get('t2', '').strip()
    all_toppers = Topper.query.order_by(Topper.year.desc(), Topper.rank.asc()).all()
    import json as _j
    a = b = None
    a_marks = b_marks = {}
    if t1:
        a = Topper.query.get(int(t1))
        if a and a.paper_marks_json:
            a_marks = _j.loads(a.paper_marks_json)
    if t2:
        b = Topper.query.get(int(t2))
        if b and b.paper_marks_json:
            b_marks = _j.loads(b.paper_marks_json)
    return render_template('toppers_compare.html',
                           all_toppers=all_toppers,
                           a=a, b=b, a_marks=a_marks, b_marks=b_marks,
                           t1=t1, t2=t2)



# ---------- PYQ Heatmap ----------
@app.route('/heatmap')
def pyq_heatmap():
    from collections import defaultdict, Counter
    subject = request.args.get('subject', '').strip()
    q = Question.query
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    questions = q.all()

    # Build topic x year matrix
    topic_years = defaultdict(Counter)
    all_years = set()
    for ques in questions:
        if ques.topic and ques.year:
            key = ques.topic.strip().title()
            topic_years[key][ques.year] += 1
            all_years.add(ques.year)
    all_years = sorted(all_years)

    # Rank topics by total frequency
    ranked = sorted(
        topic_years.items(),
        key=lambda kv: sum(kv[1].values()),
        reverse=True
    )[:40]

    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]
    max_count = max((max(c.values()) for _, c in ranked), default=1)
    return render_template('heatmap.html',
                           ranked=ranked, all_years=all_years,
                           max_count=max_count, subjects=subjects,
                           subject=subject)



# ---------- Syllabus Tracker ----------
@app.route('/syllabus')
def syllabus_tracker():
    from datetime import datetime
    exam_date = request.args.get('exam_date', '2027-05-25')
    try:
        target = datetime.strptime(exam_date, '%Y-%m-%d')
        days_left = max(0, (target - datetime.now()).days)
    except ValueError:
        days_left = 0

    stage = request.args.get('stage', 'Prelims')
    subjects = SyllabusNode.query.filter_by(stage=stage, level='subject').order_by(SyllabusNode.id).all()

    # Compute progress
    def node_progress(node):
        topics = node.children
        if not topics:
            return 0, 0
        weight = {'Not Started':0, 'Reading':25, 'Revised 1x':50, 'Revised 2x':75, 'Confident':100}
        total = sum(weight.get(t.status, 0) for t in topics)
        return total, len(topics)

    overall_done = 0
    overall_total = 0
    subject_data = []
    for s in subjects:
        done, cnt = node_progress(s)
        avg = (done / cnt) if cnt else 0
        subject_data.append({'node': s, 'avg': round(avg,1), 'total_topics': cnt})
        overall_done += done
        overall_total += cnt

    overall_pct = round(overall_done / overall_total, 1) if overall_total else 0
    return render_template('syllabus.html',
                           stages=['Prelims','Mains','Interview'],
                           stage=stage,
                           subject_data=subject_data,
                           overall_pct=overall_pct,
                           exam_date=exam_date,
                           days_left=days_left)

@app.route('/syllabus/subject/<int:sid>')
def syllabus_subject(sid):
    subj = SyllabusNode.query.get_or_404(sid)
    return render_template('syllabus_subject.html', subject=subj)

@app.route('/syllabus/update/<int:nid>', methods=['POST'])
def syllabus_update(nid):
    node = SyllabusNode.query.get_or_404(nid)
    new_status = request.form.get('status', '').strip()
    if new_status in ['Not Started', 'Reading', 'Revised 1x', 'Revised 2x', 'Confident']:
        node.status = new_status
    if 'notes' in request.form:
        node.notes = request.form.get('notes', '')
    if 'target_date' in request.form:
        node.target_date = request.form.get('target_date', '')
    node.updated_at = db.func.current_timestamp()
    db.session.commit()
    # Return to referring page
    ref = request.form.get('return_to', '')
    if ref:
        return redirect(ref)
    return redirect(url_for('syllabus_subject', sid=node.parent_id or node.id))

@app.route('/syllabus/add', methods=['POST'])
def syllabus_add():
    parent_id = request.form.get('parent_id') or None
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name required.')
        return redirect(request.referrer or url_for('syllabus_tracker'))
    parent = SyllabusNode.query.get(int(parent_id)) if parent_id else None
    db.session.add(SyllabusNode(
        parent_id=int(parent_id) if parent_id else None,
        stage=parent.stage if parent else request.form.get('stage', 'Prelims'),
        level='topic' if parent else 'subject',
        name=name
    ))
    db.session.commit()
    flash('Added.')
    return redirect(request.referrer or url_for('syllabus_tracker'))

@app.route('/syllabus/delete/<int:nid>', methods=['POST'])
def syllabus_delete(nid):
    node = SyllabusNode.query.get_or_404(nid)
    pid = node.parent_id
    db.session.delete(node)
    db.session.commit()
    return redirect(url_for('syllabus_subject', sid=pid) if pid else url_for('syllabus_tracker'))



# ---------- Pace Alert ----------
@app.route('/syllabus/pace')
def syllabus_pace():
    from datetime import datetime, timedelta
    today = datetime.now().date()

    overdue = []
    due_soon = []
    on_track = []
    no_date = []

    topics = SyllabusNode.query.filter_by(level='topic').all()
    for t in topics:
        if t.status == 'Confident':
            continue
        if not t.target_date:
            no_date.append(t)
            continue
        try:
            td = datetime.strptime(t.target_date, '%Y-%m-%d').date()
        except ValueError:
            no_date.append(t)
            continue
        days = (td - today).days
        entry = {'topic': t, 'days': days, 'target': t.target_date}
        if days < 0:
            overdue.append(entry)
        elif days <= 7:
            due_soon.append(entry)
        else:
            on_track.append(entry)

    overdue.sort(key=lambda e: e['days'])
    due_soon.sort(key=lambda e: e['days'])

    return render_template('syllabus_pace.html',
                           overdue=overdue, due_soon=due_soon,
                           on_track=on_track, no_date=no_date,
                           today=today)



# ---------- MCQ Answer Key ----------
@app.route('/question/<int:qid>/set-answer', methods=['POST'])
def set_answer_key(qid):
    q = Question.query.get_or_404(qid)
    ans = request.form.get('correct_answer', '').strip().upper()
    if ans in ['A','B','C','D']:
        q.correct_answer = ans
    else:
        q.correct_answer = None
    q.explanation = request.form.get('explanation', '').strip() or None
    db.session.commit()
    flash('Answer key saved.')
    return redirect(url_for('question_detail', qid=q.id))

# ---------- Bulk MCQ Answer Key ----------
@app.route('/mcq/key', methods=['GET', 'POST'])
def mcq_answer_key():
    from collections import Counter
    subject = request.args.get('subject', '').strip()
    only_missing = request.args.get('only_missing', '')

    q = Question.query.filter(Question.qtype == 'MCQ')
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    if only_missing:
        q = q.filter((Question.correct_answer == None) | (Question.correct_answer == ''))

    questions = q.order_by(Question.year.desc(), Question.id).limit(500).all()
    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]

    # Count of missing
    total_mcq = Question.query.filter(Question.qtype == 'MCQ').count()
    missing_mcq = Question.query.filter(
        Question.qtype == 'MCQ',
        (Question.correct_answer == None) | (Question.correct_answer == '')
    ).count()

    return render_template('mcq_key.html',
                           questions=questions, subjects=subjects,
                           subject=subject, only_missing=only_missing,
                           total_mcq=total_mcq, missing_mcq=missing_mcq)



# ---------- Weak MCQ Topics Analytics ----------
@app.route('/weak-topics')
def weak_topics():
    from collections import defaultdict
    # Look at all MockItems + ExamSimQuestions with a user answer
    topic_stats = defaultdict(lambda: {'total':0, 'correct':0, 'wrong':0})

    # From Mock tests
    mock_items = MockItem.query.filter(MockItem.user_answer.isnot(None)).all()
    for it in mock_items:
        topic = (it.question.topic or 'Unknown').strip().title()
        topic_stats[topic]['total'] += 1
        if it.correct is True:
            topic_stats[topic]['correct'] += 1
        elif it.correct is False:
            topic_stats[topic]['wrong'] += 1

    # From Exam Sims
    exam_qs = ExamSimQuestion.query.filter(ExamSimQuestion.user_answer.isnot(None)).all()
    for eq in exam_qs:
        if not eq.exam or eq.exam.mode != 'prelims':
            continue
        topic = (eq.topic or 'Unknown').strip().title()
        topic_stats[topic]['total'] += 1
        if eq.user_answer and eq.correct_option and eq.user_answer.upper()[:1] == eq.correct_option.upper()[:1]:
            topic_stats[topic]['correct'] += 1
        else:
            topic_stats[topic]['wrong'] += 1

    # Compute accuracy
    rows = []
    for topic, s in topic_stats.items():
        if s['total'] == 0:
            continue
        acc = round(100 * s['correct'] / s['total'], 1)
        rows.append({
            'topic': topic,
            'total': s['total'],
            'correct': s['correct'],
            'wrong': s['wrong'],
            'accuracy': acc
        })

    # Weakest first (accuracy ASC, but require min 2 attempts)
    rows.sort(key=lambda r: (r['accuracy'], -r['total']))
    weakest = [r for r in rows if r['total'] >= 2][:30]
    strongest = sorted([r for r in rows if r['total'] >= 2], key=lambda r: -r['accuracy'])[:15]

    total_attempts = sum(r['total'] for r in rows)
    total_correct = sum(r['correct'] for r in rows)
    overall_acc = round(100 * total_correct / total_attempts, 1) if total_attempts else 0

    return render_template('weak_topics.html',
                           weakest=weakest, strongest=strongest,
                           overall_acc=overall_acc,
                           total_attempts=total_attempts,
                           total_correct=total_correct)



# ---------- ZIP Batch Upload ----------
import zipfile
import tempfile
import shutil

@app.route('/upload-zip', methods=['GET', 'POST'])
def upload_zip():
    if request.method == 'GET':
        return render_template('upload_zip.html')

    if 'zipfile' not in request.files:
        flash('No file uploaded.')
        return redirect(url_for('upload_zip'))

    zf = request.files['zipfile']
    if not zf or not zf.filename.lower().endswith('.zip'):
        flash('Please upload a .zip file.')
        return redirect(url_for('upload_zip'))

    # Form options
    default_subject = request.form.get('subject', '').strip()
    default_author = request.form.get('author', '').strip()
    use_ocr = request.form.get('use_ocr') == 'on'
    category = request.form.get('category', 'book')

    # Save zip to temp
    tmpdir = tempfile.mkdtemp()
    zip_path = os.path.join(tmpdir, 'upload.zip')
    zf.save(zip_path)

    try:
        added = 0
        skipped = 0
        errors = []
        with zipfile.ZipFile(zip_path, 'r') as z:
            pdf_names = [n for n in z.namelist() if n.lower().endswith('.pdf') and not n.startswith('__MACOSX')]
            if not pdf_names:
                flash('No PDF files found in the ZIP.')
                return redirect(url_for('upload_zip'))

            # Extract all PDFs to temp
            for name in pdf_names:
                try:
                    z.extract(name, tmpdir)
                except Exception as e:
                    errors.append(f"{name}: extract failed")
                    skipped += 1

            # Process each PDF
            for name in pdf_names:
                pdf_path = os.path.join(tmpdir, name)
                if not os.path.exists(pdf_path):
                    continue

                # Skip duplicates (same title + category)
                raw_title = os.path.basename(name).replace('.pdf', '').replace('_', ' ').strip()
                existing = Book.query.filter_by(title=raw_title, category=category).first()
                if existing:
                    skipped += 1
                    continue

                try:
                    # Store file
                    stored_name = secure_filename(os.path.basename(name))
                    target = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
                    shutil.copy2(pdf_path, target)

                    pages = extract_pages(target, use_ocr=use_ocr)

                    book = Book(
                        title=raw_title[:300],
                        author=default_author,
                        subject=default_subject,
                        topic='',
                        category=category,
                        filename=stored_name
                    )
                    db.session.add(book)
                    db.session.flush()

                    for pnum, text, ocr_used in pages:
                        db.session.add(Page(book_id=book.id, page_number=pnum, text=text, ocr_used=ocr_used))
                    db.session.commit()
                    added += 1
                except Exception as e:
                    db.session.rollback()
                    errors.append(f"{raw_title}: {str(e)[:80]}")
                    skipped += 1

        flash(f'ZIP upload complete — {added} added, {skipped} skipped, {len(errors)} errors.')
        if errors:
            for err in errors[:5]:
                flash(f'⚠️ {err}')
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return redirect(url_for('index'))



# ---------- District Portal Directory ----------



# ---------- Voice Mentor ----------
@app.route('/voice-mentor')
def voice_mentor():
    return render_template('voice_mentor.html')

@app.route('/voice-mentor/ask', methods=['POST'])
def voice_mentor_ask():
    import requests as _rq
    if 'audio' not in request.files:
        return {'error': 'No audio received'}, 400
    audio = request.files['audio']
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    tmp = os.path.join(app.config['UPLOAD_FOLDER'], 'voice_temp.webm')
    audio.save(tmp)

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    try:
        with open(tmp, 'rb') as f:
            r = _rq.post(
                'https://api.groq.com/openai/v1/audio/transcriptions',
                headers={'Authorization': 'Bearer ' + groq['api_key']},
                files={'file': ('audio.webm', f, 'audio/webm')},
                data={'model': 'whisper-large-v3-turbo'},
                timeout=60
            )
        r.raise_for_status()
        transcript = (r.json().get('text') or '').strip()
    except Exception as e:
        try: os.remove(tmp)
        except: pass
        return {'error': 'Transcription failed: ' + str(e)[:200]}, 500

    if not transcript:
        try: os.remove(tmp)
        except: pass
        return {'error': 'No speech detected. Speak clearly.'}, 400

    system = "You are a UPSC Civil Services mentor. The student asked a doubt by voice. Answer in exam-ready structure: 1) Direct answer / definition (2-3 lines), 2) Key points as bullets, 3) UPSC angle (Prelims/Mains linkage), 4) Related topic to read. Be crisp. No filler."

    try:
        r2 = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={
                'Authorization': 'Bearer ' + groq['api_key'],
                'Content-Type': 'application/json'
            },
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': transcript}
                ],
                'temperature': 0.4,
                'max_tokens': 1200
            },
            timeout=60
        )
        r2.raise_for_status()
        answer = r2.json()['choices'][0]['message']['content']
    except Exception as e:
        try: os.remove(tmp)
        except: pass
        return {'error': 'Answer failed: ' + str(e)[:200]}, 500

    try: os.remove(tmp)
    except: pass
    return {'transcript': transcript, 'answer': answer}


# ---------- Mains Photo Upload + AI Evaluation ----------
@app.route('/mains-photo')
def mains_photo():
    return render_template('mains_photo.html')

@app.route('/mains-photo/evaluate', methods=['POST'])
def mains_photo_evaluate():
    import requests as _rq
    question = request.form.get('question', '').strip()
    marks = request.form.get('marks', '10').strip()
    if not question:
        return {'error': 'Question text required.'}, 400
    if 'photo' not in request.files:
        return {'error': 'No photo uploaded.'}, 400

    img = request.files['photo']
    if not img or img.filename == '':
        return {'error': 'Empty file.'}, 400

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    ext = os.path.splitext(img.filename)[1].lower() or '.jpg'
    tmp = os.path.join(app.config['UPLOAD_FOLDER'], 'mains_photo_temp' + ext)
    img.save(tmp)

    # OCR via Tesseract
    try:
        from PIL import Image as _Img
        import pytesseract as _pyt
        pil = _Img.open(tmp)
        if pil.width < 1200:
            ratio = 1200 / pil.width
            pil = pil.resize((int(pil.width * ratio), int(pil.height * ratio)))
        student_text = _pyt.image_to_string(pil, lang='eng').strip()
    except Exception as e:
        try: os.remove(tmp)
        except: pass
        return {'error': 'OCR failed: ' + str(e)[:200]}, 500
    finally:
        try: os.remove(tmp)
        except: pass

    if len(student_text.split()) < 30:
        return {'error': 'Could not read enough text from photo. Write clearly or use a darker pen. Detected: ' + student_text[:150]}, 400

    # Evaluate via Groq
    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    system = (
        "You are a strict UPSC Mains answer evaluator. The student wrote on paper, we OCR'd it. "
        "Score on 5 parameters (each /10, total /50): Structure, Content Depth, Keyword Usage, "
        "Multi-dimensionality, Presentation. Then give: MISSING POINTS, STRENGTHS (2-3 lines), "
        "WEAKNESSES (2-3 lines), MODEL SKELETON. End with EXACTLY: TOTAL_SCORE: X  (X = 0-50). "
        "Be honest — do not inflate."
    )
    user = (
        "QUESTION:\n" + question + "\n\nMARKS: " + marks + "\n\n"
        "STUDENT ANSWER (OCR — may have small errors):\n" + student_text + "\n\nEvaluate now."
    )
    try:
        r = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user}
                ],
                'temperature': 0.2,
                'max_tokens': 8000
            },
            timeout=90
        )
        r.raise_for_status()
        evaluation = r.json()['choices'][0]['message']['content']
    except Exception as e:
        return {'error': 'Evaluation failed: ' + str(e)[:200]}, 500

    score = None
    for line in evaluation.splitlines():
        if line.strip().startswith('TOTAL_SCORE:'):
            try: score = float(line.split(':')[1].strip())
            except: pass

    return {'text': student_text, 'evaluation': evaluation, 'score': score}


# ---------- Reminders + Streak ----------
from datetime import datetime as _dt, timedelta as _td

def _today():
    return _dt.now().strftime('%Y-%m-%d')

def _log_hit():
    try:
        d = _today()
        log = StudyLog.query.filter_by(date=d).first()
        if log:
            log.hits = (log.hits or 0) + 1
        else:
            db.session.add(StudyLog(date=d, hits=1))
        db.session.commit()
    except Exception:
        db.session.rollback()

def _calc_streak():
    try:
        logs = StudyLog.query.order_by(StudyLog.date.desc()).limit(400).all()
        dates = set(l.date for l in logs)
        streak = 0
        cur = _dt.now().date()
        while cur.strftime('%Y-%m-%d') in dates:
            streak += 1
            cur = cur - _td(days=1)
        return streak
    except Exception:
        return 0

def _reminder_data():
    exam_date = '2027-05-25'
    days_left = 9999
    try:
        d = _dt.strptime(exam_date, '%Y-%m-%d')
        days_left = max(0, (d - _dt.now()).days)
    except Exception:
        pass

    today = _dt.now().date()
    overdue = 0
    due_soon = 0
    try:
        topics = SyllabusNode.query.filter_by(level='topic').all()
        for t in topics:
            if t.status == 'Confident' or not t.target_date:
                continue
            try:
                td = _dt.strptime(t.target_date, '%Y-%m-%d').date()
            except Exception:
                continue
            delta = (td - today).days
            if delta < 0:
                overdue += 1
            elif delta <= 7:
                due_soon += 1
    except Exception:
        pass

    return {'days_left': days_left, 'overdue': overdue, 'due_soon': due_soon}

@app.route('/streak')
def streak_dashboard():
    current = _calc_streak()
    logs = StudyLog.query.order_by(StudyLog.date.desc()).limit(30).all()
    return render_template('streak.html', current=current, logs=logs)

@app.context_processor
def inject_reminders():
    try:
        _log_hit()
    except Exception:
        pass
    try:
        r = _reminder_data()
        r['current_streak'] = _calc_streak()
        return {'reminder': r}
    except Exception as e:
        return {'reminder': {'days_left': 9999, 'overdue': 0, 'due_soon': 0, 'current_streak': 0}}


# ---------- Current Affairs AI Ranking ----------
import re as _re

UPSC_KEYWORDS_WEIGHT = {
    'scheme': 3, 'policy': 3, 'act': 3, 'bill': 3, 'amendment': 3,
    'supreme court': 4, 'high court': 3, 'constitution': 4, 'article': 3,
    'parliament': 3, 'ministry': 3, 'government': 2, 'commission': 3,
    'report': 2, 'index': 3, 'rank': 2, 'survey': 3,
    'rbi': 3, 'gdp': 3, 'inflation': 3, 'budget': 3, 'fiscal': 2,
    'climate': 3, 'pollution': 2, 'biodiversity': 3, 'forest': 2,
    'isro': 3, 'drdo': 3, 'satellite': 2, 'mission': 2,
    'united nations': 3, 'g20': 4, 'brics': 4, 'quad': 4, 'un ': 2,
    'china': 3, 'pakistan': 3, 'usa': 2, 'russia': 2, 'border': 2,
    'tiger': 2, 'elephant': 2, 'national park': 3, 'unesco': 3,
    'poverty': 3, 'unemployment': 3, 'women': 2, 'child': 2, 'tribe': 3,
    'census': 3, 'election': 3, 'governor': 3, 'president': 2,
    'treaty': 3, 'summit': 3, 'agreement': 2, 'bilateral': 3,
    'security': 3, 'defence': 3, 'army': 2, 'naxal': 3, 'terror': 3,
    'cyber': 2, 'missile': 2, 'nuclear': 3,
}

IRRELEVANT_KEYWORDS = ['sports', 'cricket', 'bollywood', 'movie', 'entertainment',
                       'astrology', 'horoscope', 'celebrity', 'film', 'actor',
                       'actress', 'box office', 'web series', 'reality show']

def score_article_heuristic(title, summary):
    text = ((title or '') + ' ' + (summary or '')).lower()
    score = 0
    for kw, weight in UPSC_KEYWORDS_WEIGHT.items():
        if kw in text:
            score += weight
    for bad in IRRELEVANT_KEYWORDS:
        if bad in text:
            score -= 5
    return max(0, min(10, score))

@app.route('/news/rank', methods=['POST'])
def news_rank():
    import requests as _rq
    articles = NewsArticle.query.filter_by(ai_summary=None).limit(20).all()
    if not articles:
        articles = NewsArticle.query.order_by(NewsArticle.fetched_at.desc()).limit(20).all()

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        flash('Groq key required for AI ranking.')
        return redirect(url_for('news_list'))

    system = ("You rate news items for UPSC Civil Services relevance on a scale of 0-10. "
              "Score based on: link to syllabus, current affairs importance, exam utility. "
              "Return ONLY JSON: {\"score\": N, \"gs_paper\": \"GS1/GS2/GS3/GS4\", "
              "\"topic\": \"short topic\", \"reason\": \"1-line why\"}. "
              "Score 8-10 for major schemes/policies/constitutional matters/international summits. "
              "Score 5-7 for moderately useful news. Score 0-4 for sports/entertainment/gossip.")

    updated = 0
    for art in articles:
        try:
            text = art.title + '\n' + (art.summary_raw or '')[:800]
            r = _rq.post(
                groq['base_url'].rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
                json={
                    'model': groq['model'],
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': text}
                    ],
                    'temperature': 0.1,
                    'max_tokens': 200,
                    'response_format': {'type': 'json_object'}
                },
                timeout=30
            )
            r.raise_for_status()
            data = r.json()['choices'][0]['message']['content']
            import json as _j
            parsed = _j.loads(data)
            score = int(parsed.get('score', 0))
            art.ai_summary = 'RANK:' + str(score) + '|GS:' + str(parsed.get('gs_paper','')) + '|' + str(parsed.get('reason',''))
            updated += 1
        except Exception as e:
            continue

    db.session.commit()
    flash(f'AI ranked {updated} articles. Sorted by UPSC relevance.')
    return redirect(url_for('news_list'))

@app.route('/news/top')
def news_top():
    articles = NewsArticle.query.filter(NewsArticle.ai_summary.like('RANK:%')).all()
    parsed = []
    for a in articles:
        try:
            parts = a.ai_summary.split('|')
            score = int(parts[0].split(':')[1])
            gs = parts[1].split(':')[1] if len(parts) > 1 else ''
            reason = parts[2] if len(parts) > 2 else ''
            parsed.append({'art': a, 'score': score, 'gs': gs, 'reason': reason})
        except Exception:
            continue
    parsed.sort(key=lambda x: -x['score'])
    return render_template('news_top.html', items=parsed[:80])


# ---------- Flashcards (Spaced Repetition) ----------
from datetime import datetime as _fdt, timedelta as _ftd

class Flashcard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(100))
    topic = db.Column(db.String(200))
    due_date = db.Column(db.String(20))
    interval_days = db.Column(db.Integer, default=0)
    ease = db.Column(db.Float, default=2.5)
    reps = db.Column(db.Integer, default=0)
    lapses = db.Column(db.Integer, default=0)
    last_review = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

def _sm2(card, rating):
    """rating: 0=Again, 1=Hard, 2=Good, 3=Easy"""
    now = _fdt.now()
    today = now.strftime('%Y-%m-%d')

    if rating == 0:
        card.reps = 0
        card.lapses = (card.lapses or 0) + 1
        card.interval_days = 1
        card.ease = max(1.3, (card.ease or 2.5) - 0.2)
    else:
        if rating == 1:
            card.ease = max(1.3, (card.ease or 2.5) - 0.15)
            card.interval_days = max(1, int((card.interval_days or 0) * 1.2))
        elif rating == 2:
            if (card.reps or 0) == 0:
                card.interval_days = 1
            elif (card.reps or 0) == 1:
                card.interval_days = 6
            else:
                card.interval_days = max(1, int((card.interval_days or 1) * (card.ease or 2.5)))
        elif rating == 3:
            card.ease = min(3.0, (card.ease or 2.5) + 0.15)
            if (card.reps or 0) == 0:
                card.interval_days = 3
            elif (card.reps or 0) == 1:
                card.interval_days = 8
            else:
                card.interval_days = max(1, int((card.interval_days or 1) * (card.ease or 2.5) * 1.3))
        card.reps = (card.reps or 0) + 1

    card.last_review = today
    card.due_date = (now + _ftd(days=card.interval_days)).strftime('%Y-%m-%d')

@app.route('/flashcards')
def flashcards_list():
    subject = request.args.get('subject', '').strip()
    q = Flashcard.query
    if subject:
        q = q.filter(Flashcard.subject == subject)
    cards = q.order_by(Flashcard.due_date.asc()).limit(500).all()
    today = _fdt.now().strftime('%Y-%m-%d')
    due_count = sum(1 for c in cards if not c.due_date or c.due_date <= today)
    subjects = [s[0] for s in db.session.query(Flashcard.subject).distinct().all() if s[0]]
    return render_template('flashcards.html',
                           cards=cards, due_count=due_count,
                           subjects=subjects, subject=subject, today=today)

@app.route('/flashcards/add', methods=['POST'])
def flashcards_add():
    q = request.form.get('question', '').strip()
    a = request.form.get('answer', '').strip()
    if not q or not a:
        flash('Question and answer required.')
        return redirect(url_for('flashcards_list'))
    today = _fdt.now().strftime('%Y-%m-%d')
    db.session.add(Flashcard(
        question=q, answer=a,
        subject=request.form.get('subject', '').strip(),
        topic=request.form.get('topic', '').strip(),
        due_date=today, interval_days=0, ease=2.5, reps=0
    ))
    db.session.commit()
    flash('Card added.')
    return redirect(url_for('flashcards_list'))

@app.route('/flashcards/<int:cid>/delete', methods=['POST'])
def flashcards_delete(cid):
    c = Flashcard.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    return redirect(url_for('flashcards_list'))

@app.route('/flashcards/review')
def flashcards_review():
    subject = request.args.get('subject', '').strip()
    today = _fdt.now().strftime('%Y-%m-%d')
    q = Flashcard.query.filter(
        (Flashcard.due_date == None) | (Flashcard.due_date <= today)
    )
    if subject:
        q = q.filter(Flashcard.subject == subject)
    cards = q.order_by(Flashcard.due_date.asc()).limit(50).all()
    return render_template('flashcard_review.html', cards=cards, subject=subject)

@app.route('/flashcards/review/submit', methods=['POST'])
def flashcards_review_submit():
    cid = request.form.get('cid')
    rating = int(request.form.get('rating', 2))
    card = Flashcard.query.get_or_404(int(cid))
    _sm2(card, rating)
    db.session.commit()
    return {'ok': True, 'next_due': card.due_date, 'interval': card.interval_days}


# ---------- Book Chat (RAG) ----------
@app.route('/book-chat')
def book_chat():
    return render_template('book_chat.html')

@app.route('/book-chat/ask', methods=['POST'])
def book_chat_ask():
    import requests as _rq
    query = request.form.get('query', '').strip()
    if not query or len(query) < 3:
        return {'error': 'Ask a question.'}, 400

    # Extract keywords (remove stopwords)
    stopwords = {'what','is','the','a','an','of','in','on','and','or','to','for','with','how','why','when','where','which','who','are','was','were','be','been','being','do','does','did','have','has','had','this','that','these','those','it','its','as','by','at','from','into','about','explain','describe','tell','me'}
    words = [w.lower().strip('?,.!') for w in query.split() if w.lower() not in stopwords and len(w) > 2]
    if not words:
        words = query.lower().split()[:3]

    # Search pages for keyword matches, score by count
    from collections import Counter as _C
    score_map = {}
    for w in words:
        pages = Page.query.filter(Page.text.ilike(f'%{w}%')).limit(40).all()
        for p in pages:
            snippet = p.text.lower()
            hits = snippet.count(w)
            score_map[p.id] = score_map.get(p.id, 0) + hits

    # Top 5 pages
    top_ids = sorted(score_map.keys(), key=lambda x: -score_map[x])[:5]
    if not top_ids:
        return {'error': 'No matching content in your library. Upload relevant books first.'}, 404

    context_parts = []
    citations = []
    for i, pid in enumerate(top_ids, 1):
        p = Page.query.get(pid)
        if not p:
            continue
        book = p.book
        snippet = (p.text or '')[:2000]
        context_parts.append(
            f"[Source {i}] Book: {book.title}, Page {p.page_number}\n{snippet}"
        )
        citations.append({
            'n': i,
            'book': book.title,
            'book_id': book.id,
            'page': p.page_number,
        })

    context = "\n\n---\n\n".join(context_parts)

    system = (
        "You are an expert UPSC mentor. Answer the student's question using ONLY the SOURCE material below. "
        "RULES:\n"
        "1) Cite sources using [Source N] after each fact.\n"
        "2) If sources don't fully cover the answer, say so and add only essential (General Knowledge) content briefly.\n"
        "3) Structure: Direct answer (2-3 lines) → Key points (bullets) → UPSC angle (Prelims/Mains).\n"
        "4) Be concise. No filler. If sources disagree, note it."
    )
    user = f"STUDENT QUESTION:\n{query}\n\nSOURCE MATERIAL:\n{context}\n\nAnswer now with [Source N] citations."

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    try:
        r = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user}
                ],
                'temperature': 0.3,
                'max_tokens': 1500
            },
            timeout=90
        )
        r.raise_for_status()
        answer = r.json()['choices'][0]['message']['content']
    except Exception as e:
        return {'error': 'Answer failed: ' + str(e)[:200]}, 500

    return {'answer': answer, 'citations': citations, 'query': query}


# ---------- PDF Reader ----------

@app.route('/read/<int:book_id>/page/<int:page_num>')
def read_book_page(book_id, page_num):
    """Text-based reader with page navigation + auto-fallback to PDF view"""
    book = Book.query.get_or_404(book_id)
    total_pages = len(book.pages)
    if total_pages == 0:
        # No pages extracted — go straight to PDF view
        return redirect(url_for('read_book', book_id=book_id))
    if page_num < 1:
        page_num = 1
    if page_num > total_pages:
        page_num = total_pages

    page = Page.query.filter_by(book_id=book_id, page_number=page_num).first()

    # Check if text extraction worked — sample first 5 pages
    if page and len((page.text or '').strip()) < 80:
        sample = Page.query.filter_by(book_id=book_id).limit(5).all()
        avg_len = sum(len((p.text or '').strip()) for p in sample) / max(len(sample), 1)
        if avg_len < 100:
            flash('This is a scanned PDF — opening PDF View. Use "Run OCR" button to enable text search.')
            return redirect(url_for('read_book', book_id=book_id))

    return render_template('read_text.html', book=book, page=page,
                           page_num=page_num, total_pages=total_pages)


@app.route('/book/<int:book_id>/search')
def book_search(book_id):
    book = Book.query.get_or_404(book_id)
    q = request.args.get('q', '').strip()
    results = []
    if q:
        words = [w for w in q.split() if len(w) > 1]
        pq = Page.query.filter_by(book_id=book_id)
        for w in words:
            pq = pq.filter(Page.text.ilike(f'%{w}%'))
        pages = pq.limit(50).all()
        for p in pages:
            text = p.text or ''
            lower = text.lower()
            pos = lower.find(words[0].lower())
            if pos == -1: pos = 0
            start = max(0, pos - 150)
            end = min(len(text), pos + 350)
            snippet = text[start:end].replace('\n', ' ').strip()
            if start > 0: snippet = '...' + snippet
            if end < len(text): snippet = snippet + '...'
            results.append({'page': p.page_number, 'snippet': snippet})
    return render_template('book_search_in.html', book=book, q=q, results=results)


# ---------- Visual Thinking (How a Topper Thinks) ----------
@app.route('/question/<int:qid>/think-like-topper', methods=['POST'])
def think_like_topper(qid):
    import requests as _rq
    q = Question.query.get_or_404(qid)

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    system = (
        "You are a UPSC Prelims topper explaining your thought process. For the MCQ below, "
        "show EXACTLY these 4 steps in this format:\n\n"
        "STEP 1 — WHAT IS THE QUESTION REALLY ASKING?\n"
        "(1-2 lines identifying core concept + directive)\n\n"
        "STEP 2 — WHAT DO I KNOW FOR SURE?\n"
        "(2-4 bullet facts I'm 100% certain about)\n\n"
        "STEP 3 — ELIMINATION\n"
        "List options (a), (b), (c), (d) and mark each as ✅ Safe / ⚠️ Suspect / ❌ Eliminate with 1-line reason\n\n"
        "STEP 4 — FINAL PICK\n"
        "The correct option + one-line why.\n\n"
        "Rules: Be crisp. Real toppers think in 30-60 sec. No philosophy. No filler."
    )
    user = f"QUESTION:\n{q.text}\n\nOptions if listed in question above. Now walk through your thinking."

    try:
        r = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user}
                ],
                'temperature': 0.4,
                'max_tokens': 1200
            },
            timeout=90
        )
        r.raise_for_status()
        result = r.json()['choices'][0]['message']['content']
    except Exception as e:
        return {'error': 'Failed: ' + str(e)[:200]}, 500

    return {'thinking': result}


# ---------- Heatmap v2 — Probability Analysis ----------
@app.route('/heatmap-v2')
def heatmap_v2():
    from collections import defaultdict, Counter
    from datetime import datetime
    subject = request.args.get('subject', '').strip()
    q = Question.query
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    questions = q.all()

    # Build topic → {year: count}
    topic_years = defaultdict(Counter)
    all_years = set()
    for ques in questions:
        if ques.topic and ques.year:
            key = ques.topic.strip().title()
            topic_years[key][ques.year] += 1
            all_years.add(ques.year)

    all_years = sorted(all_years)
    current_year = datetime.now().year

    # Probability formula weights:
    # recent (current_year-1, current_year-2): weight 3
    # mid (current_year-3, current_year-4): weight 2
    # older: weight 1
    scored = []
    for topic, yc in topic_years.items():
        total = sum(yc.values())
        distinct_years = len(yc)
        recent_count = sum(c for y, c in yc.items() if y >= current_year - 2)
        mid_count = sum(c for y, c in yc.items() if current_year - 4 <= y < current_year - 2)
        older_count = total - recent_count - mid_count

        # Weighted score
        weighted = recent_count * 3 + mid_count * 2 + older_count * 1

        # Spread bonus (appearing in many years = consistent topic)
        spread_bonus = distinct_years * 0.5

        # Recency — if not seen in last 3 years, boost ("due for return")
        last_seen = max(yc.keys()) if yc else current_year
        gap_years = current_year - last_seen
        gap_boost = 2 if gap_years >= 3 else 0

        raw_score = weighted + spread_bonus + gap_boost

        # Trend direction
        first_half = sum(c for y, c in yc.items() if y <= (current_year - 3))
        second_half = sum(c for y, c in yc.items() if y > (current_year - 3))
        if second_half > first_half * 1.3:
            trend = '↑ Rising'
        elif second_half < first_half * 0.7:
            trend = '↓ Falling'
        else:
            trend = '→ Stable'

        scored.append({
            'topic': topic,
            'years': dict(yc),
            'total': total,
            'spread': distinct_years,
            'recent': recent_count,
            'raw': raw_score,
            'trend': trend,
            'last_seen': last_seen
        })

    # Normalize to probability %
    if scored:
        max_raw = max(s['raw'] for s in scored)
        for s in scored:
            pct = (s['raw'] / max_raw) * 85 + 10
            s['probability'] = min(95, round(pct, 1))
            if s['raw'] == 0:
                s['probability'] = 5.0

    # Sort by probability desc
    scored.sort(key=lambda x: -x['probability'])
    top = scored[:40]

    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]
    return render_template('heatmap_v2.html',
                           scored=top, all_years=all_years,
                           subjects=subjects, subject=subject,
                           current_year=current_year)


# ---------- Answer Comparison ----------
@app.route('/question/<int:qid>/compare')
def answer_compare_page(qid):
    q = Question.query.get_or_404(qid)
    return render_template('answer_compare.html', q=q)

@app.route('/question/<int:qid>/compare/run', methods=['POST'])
def answer_compare_run():
    import requests as _rq
    q = Question.query.get_or_404(qid)
    student_answer = request.form.get('student_answer', '').strip()
    if len(student_answer.split()) < 30:
        return {'error': 'Write at least 30 words.'}, 400

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    # Build source context from linked book pages
    source_ctx = ''
    if q.sources:
        parts = []
        for i, s in enumerate(q.sources, 1):
            parts.append(f"[Source {i}] {s.page.book.title} — Page {s.page.page_number}\n{(s.page.text or '')[:1500]}")
        source_ctx = '\n\n'.join(parts)
    else:
        source_ctx = '(No book sources linked — use general UPSC knowledge.)'

    system = (
        "You are a UPSC Mains examiner doing a side-by-side comparison. "
        "Return STRICT JSON only:\n"
        "{\n"
        '  "model_answer": "A complete 250-word model answer (Intro-Body-Conclusion)",\n'
        '  "coverage": {"matched": ["point1", "point2"], "missed": ["gap1", "gap2"]},\n'
        '  "structure_student": "1-line structure critique of student",\n'
        '  "structure_model": "1-line structure summary of model",\n'
        '  "score": 42,\n'
        '  "score_max": 50,\n'
        '  "verdict": "one-line overall verdict"\n'
        "}\n"
        "Rules: matched = concepts the student covered correctly. missed = important concepts they missed. "
        "Score out of 50 based on 5 parameters (Structure, Content, Keywords, Multi-dim, Presentation). "
        "Be honest, no inflation."
    )
    user = (
        f"QUESTION:\n{q.text}\n\nMARKS: {q.marks or 15}\n\n"
        f"SOURCE MATERIAL:\n{source_ctx}\n\n"
        f"STUDENT ANSWER:\n{student_answer}\n\n"
        "Compare now."
    )

    try:
        r = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user}
                ],
                'temperature': 0.3,
                'max_tokens': 8000,
                'response_format': {'type': 'json_object'}
            },
            timeout=120
        )
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content']
    except Exception as e:
        return {'error': 'Failed: ' + str(e)[:200]}, 500

    import json as _j
    try:
        parsed = _j.loads(content)
    except Exception:
        # Attempt cleanup
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        try:
            parsed = _j.loads(content)
        except Exception:
            return {'error': 'AI returned invalid response. Try again.'}, 500

    parsed['student_answer'] = student_answer
    parsed['student_word_count'] = len(student_answer.split())
    parsed['model_word_count'] = len(parsed.get('model_answer','').split())
    return parsed


# ---------- PYQ Trend Predictor (ML) ----------
@app.route('/trend-predictor')
def trend_predictor():
    from collections import defaultdict
    from datetime import datetime

    subject = request.args.get('subject', '').strip()
    q = Question.query
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    questions = q.all()

    # Build topic-year matrix
    topic_years = defaultdict(dict)
    all_years = set()
    for ques in questions:
        if ques.topic and ques.year:
            key = ques.topic.strip().title()
            topic_years[key][ques.year] = topic_years[key].get(ques.year, 0) + 1
            all_years.add(ques.year)

    if not all_years:
        return render_template('trend_predictor.html', predictions=[], years=[], subject=subject)

    years = sorted(all_years)
    latest = years[-1]
    next_year = latest + 1

    predictions = []
    for topic, yc in topic_years.items():
        # Pad missing years with 0
        series = [yc.get(y, 0) for y in years]
        total = sum(series)

        # ---------- Statistical analysis ----------

        # 1. Recent activity (last 3 years)
        recent = sum(series[-3:]) if len(series) >= 3 else sum(series)

        # 2. Long-term frequency
        freq = total / len(years)

        # 3. Linear regression slope (trend direction)
        n = len(years)
        x_mean = sum(range(n)) / n
        y_mean = sum(series) / n
        num = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0

        # 4. Cyclical pattern — check if topic appears every N years
        gaps = []
        for i in range(1, len(years)):
            if series[i] > 0 and series[i-1] > 0:
                continue
            if series[i] > 0:
                # find previous appearance
                for j in range(i-1, -1, -1):
                    if series[j] > 0:
                        gaps.append(i - j)
                        break
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        cycle_predicted = False
        if avg_gap > 0:
            years_since_last = n - 1 - max(i for i, v in enumerate(series) if v > 0)
            if years_since_last >= avg_gap - 1:
                cycle_predicted = True

        # 5. Mean reversion — if topic hasn't appeared in 3+ years, it's "due"
        last_seen_idx = max((i for i, v in enumerate(series) if v > 0), default=-1)
        years_since = n - 1 - last_seen_idx if last_seen_idx >= 0 else n
        due_boost = 2 if years_since >= 3 else 0

        # 6. Composite score
        recent_weight = recent * 3
        freq_weight = freq * 2
        slope_weight = slope * 2 if slope > 0 else slope
        cycle_weight = 3 if cycle_predicted else 0
        score = recent_weight + freq_weight + slope_weight + cycle_weight + due_boost

        # Confidence: 0-95%
        confidence = min(95, max(10, round(score * 10, 1)))

        # Trend direction
        if slope > 0.15:
            trend = '↑ Rising'
        elif slope < -0.15:
            trend = '↓ Falling'
        else:
            trend = '→ Stable'

        predictions.append({
            'topic': topic,
            'years': years,
            'series': series,
            'total': total,
            'recent': recent,
            'slope': round(slope, 2),
            'trend': trend,
            'cycle': cycle_predicted,
            'years_since': years_since,
            'score': round(score, 2),
            'confidence': confidence
        })

    # Sort by confidence
    predictions.sort(key=lambda x: -x['confidence'])
    top = predictions[:40]

    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]
    return render_template('trend_predictor.html',
                           predictions=top,
                           years=years,
                           next_year=next_year,
                           subjects=subjects,
                           subject=subject)


@app.route('/trend-predictor/ai', methods=['POST'])
def trend_predictor_ai():
    """Groq AI validates and enriches the top predictions"""
    import requests as _rq
    subject = request.form.get('subject', '').strip()

    q = Question.query
    if subject:
        q = q.join(Book).filter(Book.subject == subject)
    questions = q.all()

    from collections import defaultdict, Counter
    tc = Counter()
    for ques in questions:
        if ques.topic and ques.year:
            tc[ques.topic.strip().title()] += 1

    top_topics = ', '.join([f"{t} ({n})" for t, n in tc.most_common(25)])
    if not top_topics:
        return {'error': 'No PYQ data'}, 400

    # Get latest news topics
    news_titles = ', '.join([a.title[:80] for a in NewsArticle.query.order_by(NewsArticle.fetched_at.desc()).limit(15).all()])

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    system = (
        "You are a UPSC Prelims paper setter predicting 2027 questions. "
        "Return STRICT JSON: {\"predictions\": ["
        "{\"topic\": \"topic name\", \"confidence\": 75, \"reason\": \"why\", "
        "\"prelims_q\": \"sample MCQ stem\", \"answer\": \"correct concept\"}, ...]}. "
        "Give 10 predictions. Score 40-90% confidence. Prioritize topics that (a) repeat in PYQs, "
        "(b) link to current affairs. Be specific, not generic. No filler."
    )
    user = (
        f"TOP PYQ TOPICS with frequency:\n{top_topics}\n\n"
        f"RECENT NEWS:\n{news_titles or 'No news data'}\n\n"
        f"Predict 10 topics likely to appear in UPSC Prelims 2027. JSON only."
    )

    try:
        r = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user}
                ],
                'temperature': 0.5,
                'max_tokens': 2000,
                'response_format': {'type': 'json_object'}
            },
            timeout=90
        )
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content']
    except Exception as e:
        return {'error': 'AI failed: ' + str(e)[:200]}, 500

    import json as _j
    try:
        parsed = _j.loads(content)
    except Exception:
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        try:
            parsed = _j.loads(content)
        except Exception:
            return {'error': 'Invalid AI response. Try again.'}, 500

    return parsed


# ---------- Delta Progress Tracking ----------
class ProgressSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)
    syllabus_pct = db.Column(db.Float, default=0)
    mock_accuracy = db.Column(db.Float, default=0)
    flashcards_known = db.Column(db.Integer, default=0)
    streak = db.Column(db.Integer, default=0)
    questions_done = db.Column(db.Integer, default=0)

def _snapshot_today():
    from datetime import datetime as _dt
    today = _dt.now().strftime('%Y-%m-%d')

    # Syllabus %
    try:
        weight = {'Not Started':0,'Reading':25,'Revised 1x':50,'Revised 2x':75,'Confident':100}
        topics = SyllabusNode.query.filter_by(level='topic').all()
        if topics:
            v = sum(weight.get(t.status, 0) for t in topics)
            syll = round(v / len(topics), 1)
        else:
            syll = 0
    except Exception:
        syll = 0

    # Mock accuracy
    try:
        total = correct = 0
        for it in MockItem.query.filter(MockItem.user_answer.isnot(None)).all():
            if it.correct is True:
                total += 1; correct += 1
            elif it.correct is False:
                total += 1
        acc = round(100 * correct / total, 1) if total else 0
    except Exception:
        acc = 0

    # Flashcards confident
    try:
        fc = Flashcard.query.filter(Flashcard.reps >= 3).count()
    except Exception:
        fc = 0

    # Streak
    try:
        streak = _calc_streak()
    except Exception:
        streak = 0

    # Questions done
    try:
        qd = Question.query.count()
    except Exception:
        qd = 0

    existing = ProgressSnapshot.query.filter_by(date=today).first()
    if existing:
        existing.syllabus_pct = syll
        existing.mock_accuracy = acc
        existing.flashcards_known = fc
        existing.streak = streak
        existing.questions_done = qd
    else:
        db.session.add(ProgressSnapshot(
            date=today, syllabus_pct=syll, mock_accuracy=acc,
            flashcards_known=fc, streak=streak, questions_done=qd
        ))
    db.session.commit()
    return True

@app.route('/delta')
def delta_dashboard():
    _snapshot_today()
    snaps = ProgressSnapshot.query.order_by(ProgressSnapshot.date.asc()).limit(90).all()
    labels = [s.date[5:] for s in snaps]
    syllabus_series = [s.syllabus_pct for s in snaps]
    mock_series = [s.mock_accuracy for s in snaps]
    streak_series = [s.streak for s in snaps]
    cards_series = [s.flashcards_known for s in snaps]

    # Compute deltas vs 7/30 days ago
    now = snaps[-1] if snaps else None
    week_ago = snaps[-8] if len(snaps) >= 8 else None
    month_ago = snaps[-31] if len(snaps) >= 31 else None

    def diff(a, b, key):
        if not a or not b: return None
        return round(getattr(a, key) - getattr(b, key), 1)

    deltas = {
        'syllabus_7d': diff(now, week_ago, 'syllabus_pct'),
        'syllabus_30d': diff(now, month_ago, 'syllabus_pct'),
        'mock_7d': diff(now, week_ago, 'mock_accuracy'),
        'mock_30d': diff(now, month_ago, 'mock_accuracy'),
        'cards_30d': diff(now, month_ago, 'flashcards_known'),
    }

    return render_template('delta.html',
                           labels=labels,
                           syllabus=syllabus_series,
                           mock=mock_series,
                           streak=streak_series,
                           cards=cards_series,
                           deltas=deltas,
                           total_snaps=len(snaps))


# ---------- Streak-Performance Correlation ----------
@app.route('/correlation')
def correlation_dashboard():
    from datetime import datetime
    from collections import defaultdict

    # Get all progress snapshots
    snaps = ProgressSnapshot.query.order_by(ProgressSnapshot.date.asc()).all()
    if len(snaps) < 4:
        return render_template('correlation.html',
                               insufficient=True,
                               total=len(snaps))

    # Extract paired data: (streak, mock_accuracy)
    pairs = [(s.streak or 0, s.mock_accuracy or 0) for s in snaps if s.mock_accuracy > 0]

    # Pearson correlation
    correlation = 0
    if len(pairs) >= 3:
        n = len(pairs)
        sx = sum(p[0] for p in pairs)
        sy = sum(p[1] for p in pairs)
        sxx = sum(p[0]**2 for p in pairs)
        syy = sum(p[1]**2 for p in pairs)
        sxy = sum(p[0]*p[1] for p in pairs)
        num = n*sxy - sx*sy
        den = ((n*sxx - sx*sx) * (n*syy - sy*sy)) ** 0.5
        correlation = round(num / den, 2) if den != 0 else 0

    # Group days by streak band
    bands = defaultdict(lambda: {'total_acc':0,'count':0})
    for s in snaps:
        st = s.streak or 0
        if st == 0: band = '0 days'
        elif st <= 3: band = '1-3 days'
        elif st <= 7: band = '4-7 days'
        elif st <= 14: band = '8-14 days'
        elif st <= 30: band = '15-30 days'
        else: band = '30+ days'
        if s.mock_accuracy and s.mock_accuracy > 0:
            bands[band]['total_acc'] += s.mock_accuracy
            bands[band]['count'] += 1

    band_data = []
    order = ['0 days','1-3 days','4-7 days','8-14 days','15-30 days','30+ days']
    for b in order:
        if bands[b]['count'] > 0:
            band_data.append({
                'band': b,
                'avg_acc': round(bands[b]['total_acc'] / bands[b]['count'], 1),
                'count': bands[b]['count']
            })

    # Insight message
    if correlation >= 0.5:
        verdict = "🔥 Strong positive — your consistency directly boosts your scores."
        color = 'success'
    elif correlation >= 0.2:
        verdict = "✅ Mild positive — more consistency correlates with better accuracy."
        color = 'info'
    elif correlation <= -0.2:
        verdict = "⚠️ Negative — check if you're overloading without retention."
        color = 'warning'
    else:
        verdict = "📊 Not enough data — keep going, correlation will emerge."
        color = 'secondary'

    # Compare avg accuracy on high-streak vs low-streak days
    high_streak = [p[1] for p in pairs if p[0] >= 7]
    low_streak = [p[1] for p in pairs if p[0] < 7]
    high_avg = round(sum(high_streak)/len(high_streak), 1) if high_streak else 0
    low_avg = round(sum(low_streak)/len(low_streak), 1) if low_streak else 0
    uplift = round(high_avg - low_avg, 1) if high_avg and low_avg else 0

    return render_template('correlation.html',
                           insufficient=False,
                           total=len(snaps),
                           correlation=correlation,
                           verdict=verdict,
                           color=color,
                           band_data=band_data,
                           high_avg=high_avg,
                           low_avg=low_avg,
                           uplift=uplift,
                           data_points=len(pairs))


# ---------- Daily Digest ----------
@app.route('/today')
def today_digest():
    from datetime import datetime

    # Days to exam
    exam_date = '2027-05-25'
    try:
        d = datetime.strptime(exam_date, '%Y-%m-%d')
        days_left = max(0, (d - datetime.now()).days)
    except Exception:
        days_left = 0

    # Streak
    try:
        streak = _calc_streak()
    except Exception:
        streak = 0

    # Flashcards due
    today_str = datetime.now().strftime('%Y-%m-%d')
    try:
        due_cards = Flashcard.query.filter(
            (Flashcard.due_date == None) | (Flashcard.due_date <= today_str)
        ).count()
    except Exception:
        due_cards = 0

    # Top 5 AI-ranked news
    try:
        news = NewsArticle.query.filter(NewsArticle.ai_summary.like('RANK:%')).all()
        parsed = []
        for a in news:
            try:
                parts = a.ai_summary.split('|')
                score = int(parts[0].split(':')[1])
                parsed.append({'art': a, 'score': score})
            except Exception:
                continue
        parsed.sort(key=lambda x: -x['score'])
        top_news = parsed[:5]
    except Exception:
        top_news = []

    # Overdue + due-soon
    overdue = []
    due_soon = []
    try:
        today = datetime.now().date()
        for t in SyllabusNode.query.filter_by(level='topic').all():
            if t.status == 'Confident' or not t.target_date:
                continue
            try:
                td = datetime.strptime(t.target_date, '%Y-%m-%d').date()
            except Exception:
                continue
            diff = (td - today).days
            row = {'name': t.name, 'subject': t.parent.name if t.parent else ''}
            if diff < 0:
                row['days'] = -diff
                overdue.append(row)
            elif diff <= 7:
                row['days'] = diff
                due_soon.append(row)
        overdue.sort(key=lambda x: -x['days'])
        overdue = overdue[:5]
        due_soon = due_soon[:5]
    except Exception:
        pass

    # Weak topics (top 3)
    weak = []
    try:
        from collections import defaultdict
        stats = defaultdict(lambda: {'t':0,'c':0})
        for it in MockItem.query.filter(MockItem.user_answer.isnot(None)).all():
            top = (it.question.topic or 'General').title()
            stats[top]['t'] += 1
            if it.correct: stats[top]['c'] += 1
        for topic, s in stats.items():
            if s['t'] >= 2:
                acc = round(100*s['c']/s['t'], 1)
                if acc < 60:
                    weak.append({'topic': topic, 'acc': acc})
        weak.sort(key=lambda x: x['acc'])
        weak = weak[:3]
    except Exception:
        pass

    # High-probability PYQ topics
    prob = []
    try:
        from collections import Counter
        qs = Question.query.filter(Question.topic.isnot(None)).all()
        c = Counter(q.topic.strip().title() for q in qs if q.topic)
        prob = [{'topic': t, 'count': n} for t, n in c.most_common(3)]
    except Exception:
        pass

    # Motivational message
    hour = datetime.now().hour
    if hour < 6: greeting = "🌙 Early bird — late night grind pays off."
    elif hour < 12: greeting = "☀️ Good morning. Fresh start, fresh focus."
    elif hour < 17: greeting = "🌤️ Afternoon push — one more hour matters."
    elif hour < 21: greeting = "🌆 Evening — consolidate what you learned."
    else: greeting = "🌃 Night — wrap up, sleep well for retention."

    if streak >= 30: motiv = "🔥 Legendary streak! You're on another level."
    elif streak >= 7: motiv = "💪 One week strong. Don't break the chain."
    elif streak >= 1: motiv = "✅ Consistency is compounding."
    else: motiv = "🚀 Start today. One page, one MCQ — momentum begins now."

    return render_template('today.html',
                           days_left=days_left, exam_date=exam_date,
                           streak=streak, due_cards=due_cards,
                           top_news=top_news,
                           overdue=overdue, due_soon=due_soon,
                           weak=weak, prob=prob,
                           greeting=greeting, motiv=motiv)


# ---------- Advanced Prediction Engine ----------
import math
from collections import defaultdict, Counter

class ExamPhasePrediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_phase = db.Column(db.String(20))  # prelims, mains, essay
    subject = db.Column(db.String(100))
    topic = db.Column(db.String(200), nullable=False)
    probability = db.Column(db.Float)
    trend = db.Column(db.String(20))  # rising, falling, stable
    cycle_due = db.Column(db.Boolean, default=False)
    last_seen_year = db.Column(db.Integer)
    years_asked = db.Column(db.Integer)
    total_questions = db.Column(db.Integer)
    avg_marks = db.Column(db.Float)
    prediction_year = db.Column(db.Integer)
    computed_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    ai_reason = db.Column(db.Text)


def compute_phase_predictions(exam_phase, prediction_year, subject_filter=None):
    """Compute predictions for a specific exam phase using EQPM-style analysis."""
    q = Question.query.filter(Question.year.isnot(None))
    if subject_filter:
        q = q.join(Book).filter(Book.subject == subject_filter)

    if exam_phase == 'prelims':
        q = q.filter(Question.qtype == 'MCQ')
    elif exam_phase == 'mains':
        q = q.filter(Question.qtype.in_(['GS', 'Ethics']))
    elif exam_phase == 'essay':
        q = q.filter(Question.qtype == 'Essay')

    questions = q.all()
    if not questions:
        return []

    # Build topic-year-marks matrix
    topic_years = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'marks': []}))
    all_years = set()

    for ques in questions:
        if not ques.topic or not ques.year:
            continue
        key = ques.topic.strip().title()
        topic_years[key][ques.year]['count'] += 1
        if ques.marks:
            topic_years[key][ques.year]['marks'].append(ques.marks)
        all_years.add(ques.year)

    if not all_years:
        return []

    years = sorted(all_years)
    latest_year = years[-1]
    n_years = len(years)

    predictions = []
    for topic, year_data in topic_years.items():
        series = []
        mark_series = []
        for y in years:
            if y in year_data:
                series.append(year_data[y]['count'])
                mark_series.append(sum(year_data[y]['marks']))
            else:
                series.append(0)
                mark_series.append(0)

        total_qs = sum(series)
        total_marks = sum(mark_series)
        avg_marks = total_marks / total_qs if total_qs else 0

        # --- Recency-weighted frequency ---
        recency_weights = [math.exp(-(n_years - 1 - i) * 0.3) for i in range(n_years)]
        weighted_freq = sum(s * w for s, w in zip(series, recency_weights))

        # --- Trend via linear regression ---
        x_mean = (n_years - 1) / 2.0
        y_mean = total_qs / n_years
        num = sum((i - x_mean) * (series[i] - y_mean) for i in range(n_years))
        den = sum((i - x_mean) ** 2 for i in range(n_years))
        slope = num / den if den != 0 else 0

        # --- Cycle detection ---
        appearances = [i for i, v in enumerate(series) if v > 0]
        gaps = [appearances[i] - appearances[i-1] for i in range(1, len(appearances))]
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        years_since_last = (n_years - 1) - (appearances[-1] if appearances else 0)
        cycle_due = avg_gap > 0 and years_since_last >= avg_gap

        # --- Composite score ---
        raw_score = (
            weighted_freq * 3.0 +
            total_qs * 0.5 +
            max(0, slope) * 4.0 +
            (2.0 if cycle_due else 0) +
            avg_marks * 0.1
        )

        predictions.append({
            'topic': topic,
            'raw_score': raw_score,
            'series': series,
            'total_qs': total_qs,
            'avg_marks': round(avg_marks, 1),
            'slope': round(slope, 2),
            'cycle_due': cycle_due,
            'years_since_last': years_since_last,
            'last_seen': years[appearances[-1]] if appearances else None,
            'years_asked': len(appearances),
        })

    # Normalize to probability
    if predictions:
        max_raw = max(p['raw_score'] for p in predictions)
        for p in predictions:
            pct = (p['raw_score'] / max_raw) * 80 + 10 if max_raw > 0 else 10
            p['probability'] = round(min(95, pct), 1)
            if p['slope'] > 0.15:
                p['trend'] = 'rising'
            elif p['slope'] < -0.15:
                p['trend'] = 'falling'
            else:
                p['trend'] = 'stable'

    predictions.sort(key=lambda x: -x['probability'])
    return predictions[:50]


@app.route('/predict-engine')
def predict_engine():
    phase = request.args.get('phase', 'prelims')
    year = request.args.get('year', '2027')
    subject = request.args.get('subject', '').strip()

    try:
        pred_year = int(year)
    except ValueError:
        pred_year = 2027

    predictions = compute_phase_predictions(phase, pred_year, subject)
    subjects = [s[0] for s in db.session.query(Book.subject).distinct().all() if s[0]]

    return render_template('predict_engine.html',
                           predictions=predictions,
                           phase=phase, year=pred_year,
                           subject=subject, subjects=subjects)


@app.route('/predict-engine/ai-explain', methods=['POST'])
def predict_engine_ai():
    import requests as _rq
    topic = request.form.get('topic', '').strip()
    phase = request.form.get('phase', 'prelims')
    if not topic:
        return {'error': 'Topic required'}, 400

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    # Get news context
    news = ', '.join([a.title[:80] for a in NewsArticle.query.order_by(NewsArticle.fetched_at.desc()).limit(10).all()])

    system = ("You are a UPSC exam analyst. Given a topic, explain in 3-4 lines why it is "
              "likely or unlikely to appear in the next exam. Reference PYQ patterns, current affairs, "
              "and structural trends. Be specific. Return plain text, no JSON.")
    user = f"TOPIC: {topic}\nEXAM PHASE: {phase}\nRECENT NEWS: {news}\n\nWhy is this topic likely to appear?"

    try:
        r = _rq.post(groq['base_url'].rstrip('/') + '/chat/completions',
                     headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
                     json={'model': groq['model'], 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                           'temperature': 0.4, 'max_tokens': 400}, timeout=60)
        r.raise_for_status()
        return {'explanation': r.json()['choices'][0]['message']['content']}
    except Exception as e:
        return {'error': str(e)[:200]}, 500


# ---------- Coaching Resource Hub ----------
COACHING_RESOURCES = [
    # --- TOP COACHING WEBSITES ---
    {'name': 'Drishti IAS', 'cat': 'Coaching', 'url': 'https://www.drishtiias.com',
     'yt': 'https://www.youtube.com/@DrishtiIASvideos', 'desc': 'India\'s largest UPSC coaching. Hindi + English. Free daily current affairs, monthly magazine PDF, mock tests.', 'tags': ['hindi', 'english', 'free-pdf']},
    {'name': 'Vision IAS', 'cat': 'Coaching', 'url': 'https://www.visionias.in',
     'yt': 'https://www.youtube.com/@VisionIAS', 'desc': 'PT365, Mains 365, monthly magazine. Hindi + English. Best test series.', 'tags': ['test-series', 'magazine']},
    {'name': 'Vajiram & Ravi', 'cat': 'Coaching', 'url': 'https://vajiramandravi.com',
     'yt': 'https://www.youtube.com/@vajiramandravi', 'desc': 'Delhi\'s premier institute. GS Foundation. Interview guidance.', 'tags': ['foundation', 'interview']},
    {'name': 'Rau\'s IAS', 'cat': 'Coaching', 'url': 'https://www.rauias.com',
     'yt': 'https://www.youtube.com/@RausIASDelhi', 'desc': 'Focus on answer writing, mock interviews. Pioneer in UPSC coaching.', 'tags': ['interview', 'answer-writing']},
    {'name': 'StudyIQ IAS', 'cat': 'Coaching', 'url': 'https://www.studyiq.com',
     'yt': 'https://www.youtube.com/@StudyIQEducation', 'desc': '20M+ subscribers. Daily news analysis, GS subjects, current affairs.', 'tags': ['daily-news', 'hindi']},
    {'name': 'Unacademy UPSC', 'cat': 'Coaching', 'url': 'https://unacademy.com/goal/upsc-civil-services-examination-ias-preparation/KSCGY',
     'yt': 'https://www.youtube.com/@UnacademyUPSC', 'desc': 'Free lectures by top educators. Mrunal Patel, etc.', 'tags': ['free-lectures']},
    {'name': 'PW OnlyIAS', 'cat': 'Coaching', 'url': 'https://www.pw.live/upsc',
     'yt': 'https://www.youtube.com/@PWOnlyIAS', 'desc': 'Physics Wallah UPSC. Free NCERT series, daily current affairs.', 'tags': ['free-ncert']},
    {'name': 'Shankar IAS Academy', 'cat': 'Coaching', 'url': 'https://www.shankariasacademy.com',
     'yt': 'https://www.youtube.com/@ShankarIAS', 'desc': 'Best for Environment & Ecology. Monthly magazines.', 'tags': ['environment']},
    {'name': 'NextIAS', 'cat': 'Coaching', 'url': 'https://www.nextias.com',
     'yt': 'https://www.youtube.com/@NEXTIAS', 'desc': 'Made Easy group. Daily editorials, answer writing.', 'tags': ['editorials', 'mains']},
    {'name': 'ForumIAS', 'cat': 'Coaching', 'url': 'https://forumias.com',
     'yt': 'https://www.youtube.com/@ForumIAS', 'desc': 'Mains-oriented. 9 PM brief, EPIC magazine. Free PDFs.', 'tags': ['mains', 'free-pdf']},
    {'name': 'InsightsIAS', 'cat': 'Coaching', 'url': 'https://www.insightsonindia.com',
     'yt': 'https://www.youtube.com/@InsightsIAS', 'desc': 'Best free content. InstaCourses, SECURE, quizzes, current affairs PDFs.', 'tags': ['free', 'current-affairs']},
    {'name': 'ClearIAS', 'cat': 'Coaching', 'url': 'https://www.clearias.com',
     'yt': 'https://www.youtube.com/@ClearIAS', 'desc': 'Free notes, apps, mock exams, ebooks.', 'tags': ['free-notes', 'mock']},
    {'name': 'IASbaba', 'cat': 'Coaching', 'url': 'https://iasbaba.com',
     'yt': 'https://www.youtube.com/@IASbaba', 'desc': 'Yojana & Kurukshetra gist. ILP program.', 'tags': ['magazine-gist']},
    {'name': 'PMF IAS', 'cat': 'Coaching', 'url': 'https://www.pmfias.com',
     'yt': 'https://www.youtube.com/@PMFIAS', 'desc': 'Geography + Environment. Free daily resources.', 'tags': ['geography', 'free']},
    {'name': 'Mrunal Patel', 'cat': 'Coaching', 'url': 'https://mrunal.org',
     'yt': 'https://www.youtube.com/@MrunalPatel', 'desc': 'Best for Economy. Free lectures, handouts, Win25 series.', 'tags': ['economy', 'free-lectures']},

    # --- GOVERNMENT OFFICIAL ---
    {'name': 'UPSC Official', 'cat': 'Government', 'url': 'https://upsc.gov.in',
     'yt': 'https://www.youtube.com/@UPSCOfficialIndia', 'desc': 'Official UPSC website. Past papers, cut-offs, notification, marksheets.', 'tags': ['official', 'pyq']},
    {'name': 'NCERT Official', 'cat': 'Government', 'url': 'https://ncert.nic.in/textbook.php',
     'yt': 'https://www.youtube.com/@NCERTOFFICIAL', 'desc': 'All NCERT textbooks Class 1-12. Free PDF download.', 'tags': ['free', 'pdf']},
    {'name': 'PIB', 'cat': 'Government', 'url': 'https://pib.gov.in',
     'yt': 'https://www.youtube.com/@PIBIndia', 'desc': 'Press Information Bureau. Daily govt releases, schemes.', 'tags': ['daily', 'current-affairs']},
    {'name': 'Yojana Magazine', 'cat': 'Government', 'url': 'https://yojana.gov.in',
     'yt': 'https://www.youtube.com/@YojanaOfficial', 'desc': 'Monthly magazine on development. Free PDF.', 'tags': ['magazine', 'free']},
    {'name': 'Kurukshetra', 'cat': 'Government', 'url': 'https://publicationsdivision.nic.in',
     'yt': 'https://www.youtube.com/@PublicationsDivision', 'desc': 'Rural development monthly magazine. Free PDF.', 'tags': ['magazine', 'rural']},
    {'name': 'India Year Book', 'cat': 'Government', 'url': 'https://www.publicationsdivision.nic.in',
     'yt': 'https://www.youtube.com/@PublicationsDivision', 'desc': 'Official reference on India. PDF available.', 'tags': ['reference']},
    {'name': 'Sansad TV', 'cat': 'Government', 'url': 'https://sansadtv.nic.in',
     'yt': 'https://www.youtube.com/@SansadTV', 'desc': 'Parliament debates. Best for GS2, Essay.', 'tags': ['debate', 'polity']},
    {'name': 'The Hindu', 'cat': 'Government', 'url': 'https://www.thehindu.com/opinion/editorial',
     'yt': 'https://www.youtube.com/@TheHindu', 'desc': 'Best editorial source for UPSC.', 'tags': ['editorial', 'daily']},
    {'name': 'Indian Express Explained', 'cat': 'Government', 'url': 'https://indianexpress.com/section/explained',
     'yt': 'https://www.youtube.com/@IndianExpressOnline', 'desc': 'Deep analysis of current topics.', 'tags': ['analysis']},

    # --- TOPPER NOTES & ANSWER COPIES ---
    {'name': 'UnlockIAS — Topper Copies', 'cat': 'Topper', 'url': 'https://www.unlockias.in',
     'yt': '', 'desc': '640+ free PDFs of topper answer copies (2017-2025). GS1-4, Essay, Optional.', 'tags': ['free-pdf', 'answer-copy']},
    {'name': 'PDF Study Materials', 'cat': 'Topper', 'url': 'https://pdfstudymaterials.com',
     'yt': '', 'desc': 'Anudeep Durishetty (AIR 1) notes, book lists, topper strategies.', 'tags': ['free-pdf', 'notes']},
    {'name': 'Resource Vault (Telegram)', 'cat': 'Topper', 'url': 'https://t.me/resource_vault',
     'yt': '', 'desc': 'NCERTs, standard books, handwritten notes, PYQs, magazines — all free PDFs.', 'tags': ['telegram', 'free']},
    {'name': 'Delhi UPSC Secrets', 'cat': 'Topper', 'url': 'https://t.me/DelhiUpscSecrets_official',
     'yt': '', 'desc': 'PYQ analysis (2013-2026), essay papers, GS mains analysis.', 'tags': ['telegram', 'pyq']},
    {'name': 'UPSC Polity Notes', 'cat': 'Topper', 'url': 'https://t.me/UPSCPOLITYNOTES',
     'yt': '', 'desc': 'Short polity notes for UPSC CSE. 80K+ subscribers.', 'tags': ['telegram', 'polity']},

    # --- MOCK INTERVIEW CHANNELS ---
    {'name': 'Drishti IAS English (Mock Interviews)', 'cat': 'Interview', 'url': 'https://www.drishtiias.com',
     'yt': 'https://www.youtube.com/@DrishtiIASEnglish', 'desc': 'All topper mock interviews — Rank 1 to Rank 1000+.', 'tags': ['mock-interview', 'topper']},
    {'name': 'Vijender Singh Chauhan', 'cat': 'Interview', 'url': '',
     'yt': 'https://www.youtube.com/@VijenderSinghChauhan', 'desc': 'Full-length UPSC mock interviews. Communication workshops.', 'tags': ['mock-interview', 'coaching']},
    {'name': 'OnlyIAS Extended', 'cat': 'Interview', 'url': 'https://www.pw.live/upsc',
     'yt': 'https://www.youtube.com/@OnlyIASExtended', 'desc': 'Mock interviews of UPSC toppers + daily news analysis.', 'tags': ['mock-interview']},
]


@app.route('/coaching')
def coaching_hub():
    cat = request.args.get('cat', '').strip()
    search = request.args.get('q', '').strip().lower()

    items = COACHING_RESOURCES
    if cat:
        items = [i for i in items if i['cat'] == cat]
    if search:
        items = [i for i in items if search in i['name'].lower() or search in i['desc'].lower() or any(search in t for t in i['tags'])]

    cats = sorted(set(i['cat'] for i in COACHING_RESOURCES))
    return render_template('coaching.html', items=items, cats=cats, cat=cat, search=search)


# ---------- Weather Dashboard ----------
import requests as _rq

WEATHER_TOPICS = {
    'monsoon_mechanics': {'keywords': ['ITCZ','jet stream','monsoon trough','SW monsoon','NE monsoon'],'weight':5},
    'elnino_lanina': {'keywords': ['El Nino','La Nina','ENSO','Pacific','Walker circulation'],'weight':5},
    'iod': {'keywords': ['Indian Ocean Dipole','IOD','SST'],'weight':4},
    'climate_change_monsoon': {'keywords': ['extreme rainfall','monsoon variability','flood','drought'],'weight':4},
    'imd_prediction_tech': {'keywords': ['AI forecast','IMD','ensemble model'],'weight':3},
    'regional_monsoon': {'keywords': ['Kerala onset','Mumbai','Tamil Nadu NE','rain shadow'],'weight':3},
}

@app.route('/weather')
def weather_dashboard():
    from datetime import datetime
    monsoon_2026 = {
        'forecast': 'Below Normal (90% of LPA ± 4%)',
        'source': 'IMD First Long Range Forecast, April 2026',
        'implication': 'Below-normal rainfall expected in Jun-Sep 2026',
        'exam_impact': 'High probability of questions on drought, food security, water crisis, El Niño'
    }
    topics = [{'name': k.replace('_',' ').title(), 'weight': v['weight'], 'keywords': v['keywords']}
              for k, v in WEATHER_TOPICS.items()]
    topics.sort(key=lambda x: -x['weight'])
    return render_template('weather.html', monsoon_2026=monsoon_2026, topics=topics)

@app.route('/weather/predict', methods=['POST'])
def weather_predict():
    import requests as _rq
    event = request.form.get('event', '').strip()
    if not event:
        return {'error': 'Describe the weather event'}, 400
    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500
    system = ("You are a UPSC Prelims paper setter. Given a weather/climate event, predict 5-7 UPSC-style "
              "questions likely to be asked. Return JSON: {\"predictions\":[{\"topic\":\"...\","
              "\"question\":\"...\",\"answer\":\"...\",\"confidence\":75,\"reason\":\"...\"}]}. "
              "Focus on monsoon, El Niño, IOD, climate change. Confidence 40-90%.")
    user = f"WEATHER EVENT: {event}\n\nPredict UPSC Prelims questions."
    try:
        r = _rq.post(groq['base_url'].rstrip('/') + '/chat/completions',
                     headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
                     json={'model': groq['model'], 'messages': [{'role':'system','content':system},{'role':'user','content':user}],
                           'temperature': 0.5, 'max_tokens': 1500, 'response_format': {'type':'json_object'}},
                     timeout=60)
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content']
    except Exception as e:
        return {'error': str(e)[:200]}, 500
    import json as _j
    try:
        return _j.loads(content)
    except Exception:
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        try:
            return _j.loads(content)
        except Exception:
            return {'error': 'Invalid AI response'}, 500


# ---------- Adaptive Plan ----------
@app.route('/adaptive-plan')
def adaptive_plan():
    from datetime import datetime
    from collections import defaultdict, Counter

    exam_date = '2027-05-25'
    try:
        d = datetime.strptime(exam_date, '%Y-%m-%d')
        days_left = max(0, (d - datetime.now()).days)
    except Exception:
        days_left = 0

    weak_topics = []
    try:
        stats = defaultdict(lambda: {'t':0,'c':0})
        for it in MockItem.query.filter(MockItem.user_answer.isnot(None)).all():
            t = (it.question.topic or 'General').title()
            stats[t]['t'] += 1
            if it.correct: stats[t]['c'] += 1
        for t, s in stats.items():
            if s['t'] >= 2:
                acc = 100 * s['c'] / s['t']
                if acc < 60:
                    weak_topics.append({'topic': t, 'acc': round(acc,1), 'attempts': s['t']})
        weak_topics.sort(key=lambda x: x['acc'])
        weak_topics = weak_topics[:8]
    except Exception:
        pass

    prob_topics = []
    try:
        qs = Question.query.filter(Question.topic.isnot(None)).all()
        c = Counter(q.topic.strip().title() for q in qs if q.topic)
        prob_topics = [{'topic': t, 'count': n} for t, n in c.most_common(8)]
    except Exception:
        pass

    overdue = []
    due_soon = []
    try:
        today = datetime.now().date()
        for t in SyllabusNode.query.filter_by(level='topic').all():
            if t.status == 'Confident' or not t.target_date: continue
            try: td = datetime.strptime(t.target_date, '%Y-%m-%d').date()
            except: continue
            diff = (td - today).days
            row = {'name': t.name, 'subject': t.parent.name if t.parent else '', 'days': diff}
            if diff < 0: overdue.append(row)
            elif diff <= 7: due_soon.append(row)
        overdue.sort(key=lambda x: x['days'])
        due_soon.sort(key=lambda x: x['days'])
        overdue = overdue[:6]
        due_soon = due_soon[:6]
    except Exception:
        pass

    plan = []
    for o in overdue[:2]:
        plan.append({'priority':'URGENT','color':'danger','task': f"Finish: {o['name']} ({o['subject']})",'reason': f"Overdue by {-o['days']} days",'time':'60 min'})
    for w in weak_topics[:2]:
        plan.append({'priority':'WEAK','color':'warning','task': f"Practice MCQs: {w['topic']}",'reason': f"Accuracy {w['acc']}%",'time':'45 min'})
    for p in prob_topics[:2]:
        plan.append({'priority':'HIGH-PROB','color':'primary','task': f"Read/Revise: {p['topic']}",'reason': f"Appeared {p['count']} times",'time':'45 min'})
    for ds in due_soon[:2]:
        plan.append({'priority':'DUE SOON','color':'info','task': f"Progress: {ds['name']}",'reason': f"Due in {ds['days']} days",'time':'45 min'})
    plan.append({'priority':'DAILY','color':'success','task':'Current Affairs — Top 10 AI-ranked articles','reason':'Daily compulsory','time':'30 min'})

    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        due_cards = Flashcard.query.filter((Flashcard.due_date == None) | (Flashcard.due_date <= today_str)).count()
        if due_cards > 0:
            plan.append({'priority':'REVIEW','color':'secondary','task': f"Flashcard review ({due_cards} due)",'reason':'Spaced repetition','time':'20 min'})
    except Exception:
        pass

    return render_template('adaptive_plan.html', plan=plan, days_left=days_left, exam_date=exam_date,
                           weak_topics=weak_topics, prob_topics=prob_topics,
                           overdue=overdue, due_soon=due_soon)


# ---------- Answer Writing Helper (25 Visual Formats) ----------
VISUAL_FORMATS = {
    'flowchart': ('🔄 Flowchart (Top-Down)', 'Show a top-down process flow with arrows ↓ and boxes [ ]'),
    'compare_table': ('📊 Comparison Table', 'Draw a text table with 8+ rows comparing two items across multiple aspects. Use simple | column | separators'),
    'cycle': ('♻️ Cycle Diagram', 'Show a circular process with arrows ⤵ returning to start'),
    'tree': ('🌳 Tree Hierarchy', 'Show branches like a tree with │ ├─ └─ characters'),
    'cause_effect': ('➡️ Cause-Effect Chain', 'Show a chain of causes leading to effects with → arrows'),
    'pros_cons': ('⚖️ Pros-Cons Table', 'Two-column table: Pros | Cons'),
    'venn': ('🔵 Venn Diagram (text)', 'Show overlap between 2-3 concepts using ( A )  ( A∩B )  ( B ) style'),
    'timeline': ('📅 Timeline', 'Chronological events with year | event along a line ───'),
    'pyramid': ('🔺 Pyramid Hierarchy', 'Show levels of a pyramid from base to apex'),
    'mind_map': ('🧠 Mind Map', 'Central topic with radiating branches like a spoke wheel'),
    'fishbone': ('🐟 Fishbone Diagram', 'Main issue with causes attached along a spine →'),
    'three_column': ('📋 3-Column Table', 'Table with 3 columns: Aspect | Description | Example'),
    'quadrant': ('⬛ 2x2 Quadrant Matrix', 'Four quadrants: High-High, High-Low, Low-High, Low-Low'),
    'y_chart': ('Y️⃣ Y-Chart (3-way)', 'Three-way analysis: Looks Like / Sounds Like / Feels Like'),
    'ladder': ('🪜 Step Ladder', 'Step-by-step ascending with numbered rungs 1→2→3'),
    'triangle': ('🔺 Triangle Relationship', 'Three-way relationship among 3 concepts'),
    'input_process_output': ('⚙️ Input-Process-Output', 'Show INPUTS → PROCESS → OUTPUTS framework'),
    'bullet_nested': ('🔹 Nested Bullets', 'Hierarchical bullets with main • and sub ◦ points'),
    'do_dont': ('✅❌ Do vs Don\'t', 'Two-column table: Do | Don\'t'),
    'swot': ('🎯 SWOT Analysis', '4-quadrant: Strengths | Weaknesses | Opportunities | Threats'),
    'pestle': ('🌐 PESTLE Analysis', 'Political, Economic, Social, Technological, Legal, Environmental'),
    'before_after': ('⏮️⏭️ Before-After', 'Two-column: Before | After with arrows between'),
    'radial_wheel': ('☸️ Radial Wheel', 'Central topic + 6-8 spokes around it'),
    'waterfall': ('💧 Waterfall Sequential', 'Show 5-7 cascading steps with ↓ arrows between each. Each step has a title + 1 bullet'),
    'force_field': ('⚡ Force Field', 'Two opposing columns: Drivers → | ← Restrainers'),
    'sun_ray': ('☀️ Sun-Ray Diagram', 'Central topic with rays radiating out — each ray is a heading with 1-2 sub-points under it, like a sun with beams'),
    'headed_blocks': ('📌 Headed Blocks', 'Use BOLD HEADINGS in CAPS like 【HEADING】 then 3-4 bullet lines underneath each'),
    'quote_opener': ('💬 Quote + Points', 'Start with a famous quote in "double quotes", then numbered points, end with a 1-line takeaway'),
    'short_line': ('📏 Short-Line Pointwise', 'Ultra-short numbered lines (max 8 words each), one point per line, spaced for readability'),
    'underline_emphasis': ('🖍️ Underline + Emphasis', 'Use symbols like ══ or ▬▬ to underline key terms, box important words with 【 】, mark core phrase with ⭐'),
    'bold_headed': ('🔠 Bold-Head + Bullets', 'Format: **HEADING** then ◦ ◦ ◦ sub-points, then next HEADING, repeat 4-5 times'),
    'property_table': ('🧾 Property Table', 'Table with columns: Property | Buddhism | Jainism (or any 2-3 items) — 6-8 properties compared'),
    'about_para': ('📖 About-Structure', 'Structure: 【ABOUT】2 lines → 【KEY FEATURES】bullets → 【SIGNIFICANCE】bullets → 【CRITICISM】bullets'),
    'for_against': ('🆚 For vs Against', 'Two-column table with 5-6 FOR arguments and 5-6 AGAINST arguments plus 1-line verdict'),
    'arrow_chain': ('➡️ Arrow Chain', 'Concept1 ⇒ Concept2 ⇒ Concept3 with short labels, showing progression or causality'),
    'two_column_compare': ('⚖️ Two-Column Compare', 'Feature | Item A | Item B — 8-10 rows, rigorous comparison'),
    'definition_sig': ('📚 Def + Significance', 'Format: DEFINITION (1 line) → KEY POINTS (bullets) → SIGNIFICANCE (bullets) → EXAM ANGLE (1 line)'),
    'numbers_first': ('🔢 Numbers-First Answer', 'Start with DATA/NUMBERS relevant to topic, then 5 bullet points, then conclusion'),
    'key_value': ('🗝️ Key-Value Pairs', 'Format as Key: Value lines — each line starts with a term and explains in ≤10 words'),
    'abc_format': ('🅰️ A-B-C Framework', 'Divide answer into A) Aspects, B) Benefits/Challenges, C) Conclusion with 3 bullets each'),
    'quote_sandwich': ('🥪 Quote Sandwich', 'Open with quote, middle 3 points, close with another quote — shows erudition'),
    'annotated_diagram': ('🎨 Annotated Diagram', 'Draw a simple shape (circle/triangle/box) with text labels along edges and inside — ASCII art style'),
    'flow_with_conditions': ('🔀 Conditional Flow', 'If X → then Y → else Z, showing conditional logic like a decision tree'),
    'rule_of_three': ('3️⃣ Rule of Three', 'Present answer as exactly 3 factors / 3 reasons / 3 challenges, each with 2-3 sub-points — toppers use this heavily'),
    'historical_arc': ('📜 Historical Arc', 'Ancient → Medieval → Modern → Present, each with 1-2 key points'),
    'stakeholder_map': ('👥 Stakeholder Map', 'List stakeholders (govt, citizens, private, judiciary, media) each with 1-2 lines on their role/impact'),
    'case_study': ('📋 Case-Study Style', 'Start with a real example/case, extract 3-4 principles from it, then generalization'),
    'significance_challenges_way': ('🎯 S-C-W Framework', 'Three sections: 【SIGNIFICANCE】 4-5 bullets, 【CHALLENGES】 4-5 bullets, 【WAY FORWARD】 4-5 bullets. All three mandatory'),
}

@app.route('/answer-helper')
def answer_helper():
    return render_template('answer_helper.html', formats=VISUAL_FORMATS)

@app.route('/answer-helper/generate', methods=['POST'])
def answer_helper_generate():
    import requests as _rq
    topic = request.form.get('topic', '').strip()
    fmt = request.form.get('format', 'flowchart')
    marks = request.form.get('marks', '15').strip()
    length = request.form.get('length', 'medium').strip()
    if not topic:
        return {'error': 'Enter a topic or question'}, 400
    if fmt not in VISUAL_FORMATS:
        fmt = 'flowchart'

    fmt_name, fmt_desc = VISUAL_FORMATS[fmt]

    # Length presets
    length_map = {
        'short':  {'words': '150 words',  'tokens': 1400, 'depth': 'brief 4-5 bullets'},
        'medium': {'words': '250 words',  'tokens': 2200, 'depth': '7-9 bullets + 2 examples'},
        'long':   {'words': '600 words',  'tokens': 3500, 'depth': 'detailed 12-15 points + 3 examples + 1 case study + 1 data point'},
        'essay':  {'words': '1100 words', 'tokens': 5500, 'depth': 'comprehensive 20+ points + 5 examples + 2 case studies + 3 data points + multiple headings'},
    }
    cfg_l = length_map.get(length, length_map['medium'])

    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        return {'error': 'Groq key missing'}, 500

    system = (
        "You are a UPSC Mains topper writing a FULL-LENGTH answer in visual/diagrammatic format. "
        "TARGET LENGTH: " + cfg_l['words'] + " — this is MANDATORY. Do not stop early.\n\n"
        "STYLE RULES:\n"
        "1) Use Unicode: → ← ↑ ↓ ⇒ ● ○ ▪ ▸ • ★ ─ │ ┌ ┐ └ ┘ ├ ┤ ═ ║ ✅ ❌ ⭐ 【 】 ▬ ☀ ⟳\n"
        "2) Keep each line under 40 chars.\n"
        "3) Structure:\n"
        "   【INTRO / DEFINITION】 — 2-3 lines context\n"
        "   Then the requested VISUAL FORMAT with multiple sections\n"
        "   【EXAMPLES / CASE STUDIES】 — real cases (name, year, place)\n"
        "   【DATA / FACTS】 — numbers, reports, indices\n"
        "   【WAY FORWARD / CONCLUSION】 — 3-4 lines\n"
        "4) Depth required: " + cfg_l['depth'] + "\n"
        "5) Include sub-headings in 【 】 for each major section.\n"
        "6) No paragraphs. Only headings + bullets + visuals + short labels.\n"
        "7) Format: " + fmt_desc + "\n"
        "8) Plain text only. No markdown, no HTML, no code fences.\n"
        "9) LENGTH IS CRITICAL — count roughly: " + cfg_l['words'] + ". If you stop early, the answer is rejected."
    )
    user = f"TOPIC: {topic}\nMARKS: {marks}\nFORMAT: {fmt_name}\nTARGET LENGTH: {cfg_l['words']}\n\nGenerate the FULL visual answer now — hit the target length."

    def _call_groq(extra_note=''):
        r = _rq.post(
            groq['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
            json={
                'model': groq['model'],
                'messages': [
                    {'role': 'system', 'content': system + extra_note},
                    {'role': 'user', 'content': user}
                ],
                'temperature': 0.5,
                'max_tokens': cfg_l['tokens']
            },
            timeout=180
        )
        r.raise_for_status()
        return r.json()

    try:
        data = _call_groq()
        msg = data.get('choices', [{}])[0].get('message', {}) or {}
        answer = (msg.get('content') or '').strip()
        # Some models put output in 'reasoning' field instead
        if not answer:
            answer = (msg.get('reasoning') or '').strip()
    except Exception as e:
        return {'error': 'Failed: ' + str(e)[:200]}, 500

    # Retry with a forceful instruction if still empty
    if not answer:
        try:
            data = _call_groq('\n\nCRITICAL: Your previous reply was empty. You MUST output the visual answer as plain text. Do not return empty content. Start directly with 【DIRECT ANSWER】')
            msg = data.get('choices', [{}])[0].get('message', {}) or {}
            answer = (msg.get('content') or msg.get('reasoning') or '').strip()
        except Exception:
            pass

    if not answer:
        return {'error': 'AI returned empty. Try a shorter length (Short/Medium) or a different format.'}, 500

    return {'answer': answer, 'format': fmt_name}


# ---------- E-Paper Phase 1: Content Engine ----------
import feedparser
from datetime import datetime as _dt



# ---------- Jinja clean filter (strips HTML from RSS text) ----------
@app.template_filter('clean')
def _jinja_clean(s):
    import re as _r
    if not s:
        return ''
    s = str(s)
    s = _r.sub(r'<a[^>]*>(.*?)</a>', r'\1', s, flags=_r.DOTALL)
    s = _r.sub(r'<[^>]+>', ' ', s)
    s = s.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#39;',"'").replace('&#8217;',"'").replace('&#8216;',"'")
    s = _r.sub(r'\s+', ' ', s).strip()
    return s


class DailyPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    sections = db.relationship('PaperSection', backref='paper', lazy=True, cascade='all, delete-orphan')

class PaperSection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('daily_paper.id'), nullable=False)
    name = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')
    articles = db.relationship('PaperArticle', backref='section', lazy=True, cascade='all, delete-orphan')

class NewsMCQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('paper_section.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('paper_article.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    correct = db.Column(db.String(2))
    explanation = db.Column(db.Text)
    difficulty = db.Column(db.String(20))
    articles = db.relationship('PaperArticle', backref='mcq', lazy=True)

class MainsMusing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('paper_article.id'), nullable=False)
    section_name = db.Column(db.String(100))
    question = db.Column(db.Text, nullable=False)
    marks = db.Column(db.Integer, default=10)
    word_limit = db.Column(db.Integer, default=150)
    directive = db.Column(db.String(50))
    skeleton = db.Column(db.Text)
    article = db.relationship('PaperArticle', backref='mains_musing', lazy=True)

class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mcq_id = db.Column(db.Integer, db.ForeignKey('news_mcq.id'), nullable=False)
    user_answer = db.Column(db.String(2))
    correct = db.Column(db.Boolean)
    attempted_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    mcq = db.relationship('NewsMCQ', backref='attempts', lazy=True)

class WeeklyMock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    exam_pattern = db.Column(db.String(50))    # UPSC_GS, UPSC_CSAT, State_PSC, Custom
    total_questions = db.Column(db.Integer)
    duration_minutes = db.Column(db.Integer)
    negative_marking = db.Column(db.Float, default=0.66)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    submitted_at = db.Column(db.DateTime)
    score = db.Column(db.Float)
    max_score = db.Column(db.Float)
    status = db.Column(db.String(20), default='active')  # active, submitted
    questions = db.relationship('WeeklyMockQ', backref='mock', lazy=True, cascade='all, delete-orphan')

class WeeklyMockQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mock_id = db.Column(db.Integer, db.ForeignKey('weekly_mock.id'), nullable=False)
    mcq_id = db.Column(db.Integer, db.ForeignKey('news_mcq.id'), nullable=False)
    user_answer = db.Column(db.String(2))
    is_correct = db.Column(db.Boolean)
    mcq = db.relationship('NewsMCQ')




class PaperArticle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('paper_section.id'), nullable=False)
    title = db.Column(db.String(500))
    summary = db.Column(db.Text)
    source = db.Column(db.String(100))
    url = db.Column(db.String(500))
    gs_paper = db.Column(db.String(20))
    relevance = db.Column(db.Integer)

RSS_SOURCES = [
    # Front page & Polity
    {'name': 'PIB', 'url': 'https://news.google.com/rss/search?q=site:pib.gov.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Polity'},
    {'name': 'Parliament', 'url': 'https://news.google.com/rss/search?q=Parliament+India+bill+act+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Polity'},
    {'name': 'Supreme Court', 'url': 'https://news.google.com/rss/search?q=Supreme+Court+constitution+verdict+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Polity'},
    # Economy
    {'name': 'RBI & Economy', 'url': 'https://news.google.com/rss/search?q=India+RBI+GDP+inflation+budget+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Economy'},
    {'name': 'Markets', 'url': 'https://news.google.com/rss/search?q=India+economy+trade+exports+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Economy'},
    # International
    {'name': 'World News', 'url': 'https://news.google.com/rss/search?q=India+foreign+relations+bilateral+summit+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'International'},
    {'name': 'UN & Global', 'url': 'https://news.google.com/rss/search?q=United+Nations+G20+BRICS+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'International'},
    # Environment
    {'name': 'Environment', 'url': 'https://news.google.com/rss/search?q=India+climate+environment+wildlife+pollution+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Environment'},
    {'name': 'Climate Change', 'url': 'https://news.google.com/rss/search?q=climate+change+COP+emission+renewable+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Environment'},
    # Science & Tech
    {'name': 'ISRO & Space', 'url': 'https://news.google.com/rss/search?q=ISRO+satellite+space+mission+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Science & Tech'},
    {'name': 'Tech & AI', 'url': 'https://news.google.com/rss/search?q=India+AI+technology+innovation+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Science & Tech'},
    # Editorial & Analysis
    {'name': 'The Hindu Editorial', 'url': 'https://news.google.com/rss/search?q=site:thehindu.com+editorial+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Editorial'},
    {'name': 'Indian Express Explained', 'url': 'https://news.google.com/rss/search?q=site:indianexpress.com+explained+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Editorial'},
    # Society & Governance
    {'name': 'Schemes & Welfare', 'url': 'https://news.google.com/rss/search?q=India+scheme+welfare+education+health+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Society'},
    {'name': 'Governance', 'url': 'https://news.google.com/rss/search?q=India+governance+reform+policy+when:2d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Governance'},
]

@app.route('/epaper')
def epaper_home():
    return redirect(url_for('epaper_lazy'))

@app.route('/epaper/generate', methods=['GET', 'POST'])
def epaper_generate():
    import time as _time
    import requests as _rq
    from collections import defaultdict
    today = _dt.now().strftime('%Y-%m-%d')
    
    existing = DailyPaper.query.filter_by(date=today).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    
    cfg = load_config()
    groq = cfg.get('providers', {}).get('groq')
    if not groq or not groq.get('api_key'):
        flash('Groq key required.')
        return redirect(url_for('index'))

    # Fetch articles from RSS
    fetched = []
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src['url'])
            for entry in feed.entries[:5]:
                fetched.append({
                    'title': entry.get('title', ''),
                    'summary': entry.get('summary', '')[:500],
                    'link': entry.get('link', ''),
                    'source': src['name'],
                    'category': src['category']
                })
        except Exception:
            continue

    if not fetched:
        flash('No articles fetched. Check internet.')
        return redirect(url_for('index'))

    # AI summarize + score
    paper = DailyPaper(date=today)
    db.session.add(paper)
    db.session.flush()
    
    section_map = defaultdict(list)
    CORE_SECTIONS = ['Polity', 'Economy', 'International', 'Environment',
                     'Science & Tech', 'Editorial', 'Society', 'Governance']
    
    # Keyword-based fallback section detection (in case AI miscategorizes)
    def detect_section(text):
        t = text.lower()
        if any(k in t for k in ['parliament','supreme court','constitution','president','governor','election','bill','act ','lok sabha','rajya sabha','federal']):
            return 'Polity'
        if any(k in t for k in ['rbi','gdp','inflation','budget','tax','gst','fiscal','monetary','trade','export','import','rupee','bank','economy','economic']):
            return 'Economy'
        if any(k in t for k in ['china','pakistan','usa','russia','united nations','g20','brics','quad','summit','bilateral','treaty','foreign','diplomacy','nato']):
            return 'International'
        if any(k in t for k in ['climate','pollution','biodiversity','forest','wildlife','carbon','emission','renewable','solar','tiger','wetland','unfccc','cop']):
            return 'Environment'
        if any(k in t for k in ['isro','drdo','satellite','ai ','artificial intelligence','quantum','vaccine','biotech','space','chip','5g','6g','semiconductor','tech','technology']):
            return 'Science & Tech'
        if any(k in t for k in ['editorial','opinion','analysis','column','comment']):
            return 'Editorial'
        if any(k in t for k in ['education','health','women','child','caste','tribe','poverty','nutrition','employment','welfare','scheme']):
            return 'Society'
        if any(k in t for k in ['governance','reform','policy','administration','pib','ministry']):
            return 'Governance'
        return 'Polity'
    
    for art in fetched[:30:]:
        if len(art.get('summary','')) < 40:
            continue
        try:
            system = ("You are a UPSC news classifier. Return JSON only: "
                      "{\"summary\": \"2-3 bullet UPSC summary\", \"gs_paper\": \"GS1|GS2|GS3|GS4\", "
                      "\"relevance\": 8, \"section\": \"ONE_OF: Polity, Economy, International, Environment, Science & Tech, Editorial, Society, Governance\"}")
            user = f"TITLE: {art['title']}\n\nCONTENT: {art['summary'][:400]}\n\nClassify and summarize."
            r = _rq.post(groq['base_url'].rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + groq['api_key'], 'Content-Type': 'application/json'},
                json={'model': groq['model'], 'messages': [{'role':'system','content':system},{'role':'user','content':user}],
                      'temperature': 0.2, 'max_tokens': 800, 'response_format': {'type':'json_object'}},
                timeout=30)
            r.raise_for_status()
            parsed = r.json()['choices'][0]['message']['content']
            import json as _j
            data = _j.loads(parsed)
            _time.sleep(2.2)
            
            # Normalize section — match any of the 8 by keyword, case-insensitive
            raw_sec = (data.get('section') or '').strip()
            sec_name = None
            for core in CORE_SECTIONS:
                if core.lower() in raw_sec.lower() or raw_sec.lower() in core.lower():
                    sec_name = core
                    break
            if not sec_name:
                # Fallback to keyword detection on title
                sec_name = detect_section(art['title'] + ' ' + art['summary'])
            
            section_map[sec_name].append({
                'title': art['title'],
                'summary': data.get('summary', ''),
                'gs': data.get('gs_paper', ''),
                'relevance': data.get('relevance', 6),
                'source': art['source'],
                'url': art['link']
            })
        except Exception:
            _time.sleep(1.5)
            continue
    
    # Distribute: ensure every section has at least 2 (pull from large sections)
    for sec_name in CORE_SECTIONS:
        while len(section_map[sec_name]) < 2:
            donors = sorted(section_map.items(), key=lambda kv: -len(kv[1]))
            moved = False
            for dn, darts in donors:
                if dn != sec_name and len(darts) > 3:
                    section_map[sec_name].append(darts.pop())
                    moved = True
                    break
            if not moved:
                break
    
    # Save — only insert placeholder if still empty after distribution
    for sec_name in CORE_SECTIONS:
        arts = section_map.get(sec_name, [])
        if not arts:
            arts = [{'title': f'{sec_name} — No major news today',
                     'summary': 'Check back tomorrow.',
                     'gs': '', 'relevance': 5, 'source': 'AI Desk', 'url': '#'}]
        sec = PaperSection(paper_id=paper.id, name=sec_name)
        db.session.add(sec)
        db.session.flush()
        for a in arts:
            db.session.add(PaperArticle(
                section_id=sec.id, title=a['title'][:300], summary=a['summary'],
                source=a['source'], url=a['url'], gs_paper=a['gs'], relevance=a['relevance']
            ))
    
    db.session.commit()
    flash(f'E-Paper generated for {today} with {len(fetched)} articles processed.')
    return redirect(url_for('epaper_home'))

@app.route('/epaper/archive')
def epaper_archive():
    papers = DailyPaper.query.order_by(DailyPaper.date.desc()).limit(30).all()
    return render_template('epaper_archive.html', papers=papers)


# ---------- Lazy E-Paper v2 ----------
import json as _lazy_json
import time as _lazy_time

def _lazy_call_any_ai(system, user, max_tokens=800):
    """Try multiple providers in order — return parsed JSON or raise."""
    providers_order = ['groq', 'gemini', 'deepseek', 'openrouter']
    cfg = load_config()
    last_err = None
    for prov in providers_order:
        p = cfg.get('providers', {}).get(prov)
        if not p or not p.get('api_key'):
            continue
        try:
            r = _rq.post(
                p['base_url'].rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + p['api_key'], 'Content-Type': 'application/json'},
                json={
                    'model': p['model'],
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': user}
                    ],
                    'temperature': 0.3,
                    'max_tokens': max_tokens
                },
                timeout=30
            )
            r.raise_for_status()
            content = r.json()['choices'][0]['message']['content']
            return content, prov
        except Exception as e:
            last_err = str(e)[:120]
            continue
    raise Exception(f"All AI providers failed. Last: {last_err}")

def _lazy_detect_section(text):
    t = text.lower()
    if any(k in t for k in ['parliament','supreme court','constitution','president','election','bill','act ','lok sabha','rajya sabha','federal']):
        return 'Polity'
    if any(k in t for k in ['rbi','gdp','inflation','budget','tax','gst','fiscal','trade','export','import','rupee','bank','economy']):
        return 'Economy'
    if any(k in t for k in ['china','pakistan','usa','russia','united nations','g20','brics','quad','summit','bilateral','treaty','foreign','diplomacy']):
        return 'International'
    if any(k in t for k in ['climate','pollution','biodiversity','forest','wildlife','carbon','emission','renewable','solar','tiger','wetland']):
        return 'Environment'
    if any(k in t for k in ['isro','drdo','satellite','ai ','artificial intelligence','quantum','vaccine','biotech','space','chip','5g','6g','tech']):
        return 'Science & Tech'
    if any(k in t for k in ['editorial','opinion','analysis','column']):
        return 'Editorial'
    if any(k in t for k in ['education','health','women','child','caste','tribe','poverty','nutrition','employment','welfare','scheme']):
        return 'Society'
    if any(k in t for k in ['governance','reform','policy','administration','pib','ministry']):
        return 'Governance'
    return 'Polity'

import re as _re_clean

def _clean_html(text):
    """Strip HTML tags, links, entities from RSS text."""
    if not text:
        return ''
    # Remove <a href="...">text</a> → keep text
    text = _re_clean.sub(r'<a[^>]*>(.*?)</a>', r'\1', text, flags=_re_clean.DOTALL)
    # Remove all other tags
    text = _re_clean.sub(r'<[^>]+>', ' ', text)
    # Decode common entities
    text = text.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&#39;',"'")
    # Collapse whitespace
    text = _re_clean.sub(r'\s+', ' ', text).strip()
    return text

def _lazy_fetch():
    """Fetch fresh articles from RSS — returns list with cleaned text."""
    fetched = []
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src['url'])
            for entry in feed.entries[:5]:
                raw_summary = entry.get('summary','') or entry.get('description','')
                fetched.append({
                    'title': _clean_html(entry.get('title','')),
                    'summary': _clean_html(raw_summary)[:500],
                    'link': entry.get('link',''),
                    'source': src['name'],
                    'category': src['category']
                })
        except Exception:
            continue
    return fetched

def _lazy_generate_front(paper):
    """Generate front page — no AI, just highest-priority article."""
    fetched = _lazy_fetch()
    if not fetched:
        return
    # Pick the one with most policy keywords
    scored = []
    for a in fetched:
        txt = (a['title'] + ' ' + a['summary']).lower()
        score = 0
        for kw in ['scheme','policy','act','bill','supreme court','constitution','rbi','gdp','climate','isro','g20','pib']:
            if kw in txt:
                score += 2
        scored.append((score, a))
    scored.sort(key=lambda x: -x[0])
    top = scored[0][1] if scored else fetched[0]
    
    sec = PaperSection.query.filter_by(paper_id=paper.id, name='Front Page').first()
    if not sec:
        sec = PaperSection(paper_id=paper.id, name='Front Page', status='ready')
        db.session.add(sec)
        db.session.flush()
    sec.status = 'ready'
    # Simple summary (no AI): first 3 sentences
    summary_text = _clean_html(top['summary'])[:350]
    db.session.add(PaperArticle(
        section_id=sec.id,
        title=top['title'][:300],
        summary=summary_text,
        source=top['source'],
        url=top['link'],
        gs_paper='',
        relevance=8
    ))
    db.session.commit()

def _lazy_generate_section(paper, section):
    """Generate one section using AI."""
    fetched = _lazy_fetch()
    # Filter by section using keyword detection
    matching = [a for a in fetched if _lazy_detect_section(a['title'] + ' ' + a['summary']) == section.name]
    if not matching:
        matching = fetched[:3]
    # Apply theme weight — larger sections get more articles this month
    weights = _current_theme_weights()
    boost = weights.get(section.name, 1.0)
    if boost >= 1.5:
        # grab extra articles for high-weight sections
        extra = [a for a in fetched if _lazy_detect_section(a['title'] + ' ' + a['summary']) == section.name]
        matching = (extra + matching)[:6]
    
    arts_saved = 0
    for art in matching[:6]:
        if arts_saved >= 5:
            break
        try:
            system = ("You are a UPSC news editor. Return JSON: "
                      "{\"summary\": \"Full 150-word newspaper-style article with headline, 3-4 factual paragraphs, names, numbers, dates\", "
                      "\"gs_paper\": \"GS1|GS2|GS3|GS4\", \"relevance\": 8}")
            user = f"TITLE: {art['title']}\n\nCONTENT: {art['summary']}\n\nSummarize for UPSC."
            content, prov = _lazy_call_any_ai(system, user, max_tokens=800)
            content = content.strip().strip('`').replace('```json','').replace('```','').strip()
            data = _lazy_json.loads(content)
            db.session.add(PaperArticle(
                section_id=section.id,
                title=art['title'][:300],
                summary=data.get('summary', art['summary'][:200]),
                source=art['source'],
                url=art['link'],
                gs_paper=data.get('gs_paper', ''),
                relevance=data.get('relevance', 6)
            ))
            arts_saved += 1
            _lazy_time.sleep(1.5)  # small pause
        except Exception as e:
            continue
    
    if arts_saved == 0:
        # Fallback — save raw summary without AI
        for art in matching[:2]:
            db.session.add(PaperArticle(
                section_id=section.id,
                title=art['title'][:300],
                summary=_clean_html(art['summary'])[:300],
                source=art['source'],
                url=art['link'],
                gs_paper='',
                relevance=6
            ))
    
    section.status = 'ready'
    db.session.commit()
    return arts_saved


@app.route('/epaper/lazy')
def epaper_lazy():
    today = _dt.now().strftime('%Y-%m-%d')
    paper = DailyPaper.query.filter_by(date=today).first()
    if not paper:
        paper = DailyPaper(date=today)
        db.session.add(paper)
        db.session.flush()
        CORE = ['Front Page','Polity','Economy','International','Environment','Science & Tech','Editorial','Society','Governance']
        for name in CORE:
            db.session.add(PaperSection(paper_id=paper.id, name=name, status='pending'))
        db.session.commit()
        # Auto-generate front (fast, no AI)
        _lazy_generate_front(paper)
    
    sections = PaperSection.query.filter_by(paper_id=paper.id).order_by(PaperSection.id).all()
    ready = [s for s in sections if s.status == 'ready']
    pending = [s for s in sections if s.status != 'ready']
    return render_template('epaper_lazy.html', paper=paper, today=today,
                           ready=ready, pending=pending,
                           total=len(sections), done=len(ready))


@app.route('/epaper/lazy/load-next', methods=['POST'])
def epaper_lazy_load_next():
    today = _dt.now().strftime('%Y-%m-%d')
    paper = DailyPaper.query.filter_by(date=today).first_or_404()
    pending = PaperSection.query.filter_by(paper_id=paper.id, status='pending').order_by(PaperSection.id).first()
    if not pending:
        return {'done': True}
    try:
        _lazy_generate_section(paper, pending)
        return {'done': False, 'section': pending.name, 'status': 'ready'}
    except Exception as e:
        return {'error': str(e)[:200]}, 500


@app.route('/epaper/lazy/reset', methods=['POST'])
def epaper_lazy_reset():
    today = _dt.now().strftime('%Y-%m-%d')
    paper = DailyPaper.query.filter_by(date=today).first()
    if paper:
        db.session.delete(paper)
        db.session.commit()
    return redirect(url_for('epaper_lazy'))


# ---------- E-Paper PDF Route ----------
@app.route('/epaper/pdf')
def epaper_pdf():
    from datetime import datetime as _pdfdt
    today = _pdfdt.now().strftime('%Y-%m-%d')
    paper = DailyPaper.query.filter_by(date=today).first()
    if not paper:
        flash('No paper generated yet.')
        return redirect(url_for('epaper_lazy'))
    sections = PaperSection.query.filter_by(paper_id=paper.id, status='ready').order_by(PaperSection.id).all()
    return render_template('epaper_pdf.html', paper=paper, today=today, sections=sections)


# ---------- PYQ Flashback filter (fix) ----------
def _find_related_pyqs(text, max_results=3):
    import re as _r
    from collections import Counter as _Cnt
    from sqlalchemy import or_ as _or
    if not text:
        return []
    stop = {'the','a','an','of','in','on','and','or','to','for','with','is','are','was','were',
            'be','been','being','that','this','it','its','as','by','at','from','into','about',
            'which','who','what','when','where','why','how','has','have','had','will','would',
            'can','could','should','may','might','their','there','they','than','then',
            'also','such','said','says','according','new','recent'}
    words = [w.lower().strip('.,?!;:()[]"\'\'') for w in _r.findall(r'\w+', text)]
    words = [w for w in words if len(w) > 3 and w not in stop]
    if not words:
        return []
    top_words = [w for w, _ in _Cnt(words).most_common(8)]
    filters = []
    for w in top_words:
        filters.append(Question.text.ilike(f'%{w}%'))
        filters.append(Question.topic.ilike(f'%{w}%'))
    try:
        candidates = Question.query.filter(_or(*filters)).limit(40).all()
    except Exception:
        return []
    scored = []
    for c in candidates:
        ctext = ((c.text or '') + ' ' + (c.topic or '')).lower()
        score = sum(1 for w in top_words if w in ctext)
        if score >= 2:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:max_results]]


@app.template_filter('pyq_flashback')
def _pyq_flashback_filter(text):
    qs = _find_related_pyqs(text)
    out = []
    for q in qs:
        out.append({
            'id': q.id,
            'text': (q.text or '')[:220],
            'topic': q.topic or '',
            'year': q.year,
            'qtype': (q.qtype or 'Prelims'),
            'marks': q.marks
        })
    return out


# ---------- Missing routes restored ----------
@app.route('/quiz-tracker')
def quiz_tracker():
    from datetime import datetime as _qdt, timedelta as _qtd
    today = _qdt.now().strftime('%Y-%m-%d')
    paper = DailyPaper.query.filter_by(date=today).first()
    today_mcqs = []
    if paper:
        for sec in PaperSection.query.filter_by(paper_id=paper.id, status='ready').all():
            for art in sec.articles:
                for m in NewsMCQ.query.filter_by(article_id=art.id).all():
                    today_mcqs.append(m)
    cutoff = (_qdt.now() - _qtd(days=30))
    attempts = QuizAttempt.query.filter(QuizAttempt.attempted_at >= cutoff).all()
    total = len(attempts)
    correct = sum(1 for a in attempts if a.correct)
    accuracy = round(100 * correct / total, 1) if total else 0
    from collections import defaultdict
    sec_stats = defaultdict(lambda: {'t':0, 'c':0})
    for a in attempts:
        if a.mcq and a.mcq.article and a.mcq.article.section:
            key = a.mcq.article.section.name
            sec_stats[key]['t'] += 1
            if a.correct: sec_stats[key]['c'] += 1
    sec_list = [{'name': k, 'total': v['t'], 'correct': v['c'],
                 'accuracy': round(100 * v['c'] / v['t'], 1) if v['t'] else 0}
                for k, v in sec_stats.items()]
    sec_list.sort(key=lambda x: x['accuracy'])
    return render_template('quiz_tracker.html',
                           today_mcqs=today_mcqs,
                           total=total, correct=correct, accuracy=accuracy,
                           sec_list=sec_list)


@app.route('/quiz/answer', methods=['POST'])
def quiz_answer():
    mcq_id = request.form.get('mcq_id')
    user_ans = (request.form.get('answer') or '').upper()[:1]
    if not mcq_id or user_ans not in ['A','B','C','D']:
        return {'error': 'Invalid'}, 400
    mcq = NewsMCQ.query.get_or_404(int(mcq_id))
    is_correct = (user_ans == (mcq.correct or '').upper()[:1])
    db.session.add(QuizAttempt(mcq_id=mcq.id, user_answer=user_ans, correct=is_correct))
    db.session.commit()
    return {'correct': is_correct, 'answer': mcq.correct, 'explanation': mcq.explanation or ''}


@app.route('/yesterday-recall')
def yesterday_recall():
    from datetime import datetime as _yy, timedelta as _yd
    yesterday = (_yy.now() - _yd(days=1)).strftime('%Y-%m-%d')
    ypaper = DailyPaper.query.filter_by(date=yesterday).first()
    mcqs = []
    if ypaper:
        for sec in PaperSection.query.filter_by(paper_id=ypaper.id, status='ready').all():
            for art in sec.articles:
                for m in NewsMCQ.query.filter_by(article_id=art.id).limit(2).all():
                    mcqs.append(m)
                    if len(mcqs) >= 8: break
                if len(mcqs) >= 8: break
            if len(mcqs) >= 8: break
    return render_template('yesterday_recall.html', mcqs=mcqs)


EXAM_PATTERNS = {
    'UPSC_GS':   {'q':100,'min':120,'neg':0.66,'marks_per_q':2,'label':'UPSC Prelims GS Paper I'},
    'UPSC_CSAT': {'q':80,'min':120,'neg':0.83,'marks_per_q':2.5,'label':'UPSC Prelims CSAT Paper II'},
    'UPSC_BOTH': {'q':180,'min':240,'neg':0.66,'marks_per_q':2,'label':'Full Prelims (GS + CSAT)'},
    'STATE_150': {'q':150,'min':150,'neg':0.33,'marks_per_q':1,'label':'State PSC (150 Q)'},
    'STATE_160': {'q':160,'min':160,'neg':0.33,'marks_per_q':1,'label':'State PSC (160 Q)'},
    'STATE_200': {'q':200,'min':180,'neg':0.25,'marks_per_q':1,'label':'State PSC (200 Q)'},
    'CUSTOM_50': {'q':50,'min':60,'neg':0.66,'marks_per_q':2,'label':'Quick 50-Q Mock'},
    'CUSTOM_25': {'q':25,'min':30,'neg':0.66,'marks_per_q':2,'label':'Rapid 25-Q Mock'},
}


@app.route('/weekly-mock')
def weekly_mock_home():
    mocks = WeeklyMock.query.order_by(WeeklyMock.created_at.desc()).limit(20).all()
    return render_template('weekly_mock_home.html', mocks=mocks, patterns=EXAM_PATTERNS)


@app.route('/weekly-mock/create', methods=['POST'])
def weekly_mock_create():
    from random import shuffle as _shuf
    pattern_key = request.form.get('pattern', 'UPSC_GS')
    p = EXAM_PATTERNS.get(pattern_key, EXAM_PATTERNS['UPSC_GS'])
    target_q = min(int(request.form.get('custom_q') or p['q']), 300)
    pool = []
    papers = DailyPaper.query.order_by(DailyPaper.date.desc()).limit(30).all()
    for paper in papers:
        for sec in PaperSection.query.filter_by(paper_id=paper.id, status='ready').all():
            for art in sec.articles:
                for m in NewsMCQ.query.filter_by(article_id=art.id).all():
                    if m.correct and m.option_a:
                        pool.append(m)
    if len(pool) < 5:
        flash('Not enough MCQs yet. Open E-Paper and load sections.')
        return redirect(url_for('weekly_mock_home'))
    _shuf(pool)
    pool = pool[:target_q]
    mock = WeeklyMock(
        name=f"{p['label']} — {_dt.now().strftime('%d %b %Y')}",
        exam_pattern=pattern_key, total_questions=len(pool),
        duration_minutes=int(request.form.get('custom_min') or p['min']),
        negative_marking=p['neg'], max_score=len(pool) * p['marks_per_q'], status='active'
    )
    db.session.add(mock); db.session.flush()
    for m in pool:
        db.session.add(WeeklyMockQ(mock_id=mock.id, mcq_id=m.id))
    db.session.commit()
    return redirect(url_for('weekly_mock_take', mid=mock.id))


@app.route('/weekly-mock/<int:mid>')
def weekly_mock_take(mid):
    mock = WeeklyMock.query.get_or_404(mid)
    if mock.status == 'submitted':
        return redirect(url_for('weekly_mock_result', mid=mock.id))
    return render_template('weekly_mock_take.html', mock=mock)


@app.route('/weekly-mock/<int:mid>/submit', methods=['POST'])
def weekly_mock_submit(mid):
    mock = WeeklyMock.query.get_or_404(mid)
    total_correct = total_wrong = 0
    for q in mock.questions:
        ua = (request.form.get(f'q_{q.id}', '') or '').upper()[:1]
        q.user_answer = ua
        if not ua:
            q.is_correct = None
        else:
            correct = (q.mcq.correct or '').upper()[:1]
            q.is_correct = (ua == correct)
            if q.is_correct: total_correct += 1
            else: total_wrong += 1
    p = EXAM_PATTERNS.get(mock.exam_pattern, EXAM_PATTERNS['UPSC_GS'])
    mock.score = round(total_correct * p['marks_per_q'] - total_wrong * (p['marks_per_q'] * p['neg']), 2)
    mock.status = 'submitted'
    mock.submitted_at = _dt.now()
    db.session.commit()
    return redirect(url_for('weekly_mock_result', mid=mock.id))


@app.route('/weekly-mock/<int:mid>/result')
def weekly_mock_result(mid):
    mock = WeeklyMock.query.get_or_404(mid)
    total_correct = sum(1 for q in mock.questions if q.is_correct is True)
    total_wrong = sum(1 for q in mock.questions if q.is_correct is False)
    total_blank = sum(1 for q in mock.questions if not q.user_answer)
    return render_template('weekly_mock_result.html', mock=mock,
                           correct=total_correct, wrong=total_wrong, blank=total_blank)


@app.route('/weekly-mock/<int:mid>/delete', methods=['POST'])
def weekly_mock_delete(mid):
    m = WeeklyMock.query.get_or_404(mid)
    db.session.delete(m); db.session.commit()
    flash('Mock deleted.')
    return redirect(url_for('weekly_mock_home'))


# ---------- Predictive Exam Paper Generator ----------
class PredictivePaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300))
    exam_type = db.Column(db.String(50))     # UPSC_PRELIMS_GS, UPSC_CSAT, UPSC_MAINS_GS1..4, ESSAY, OPTIONAL, STATE_PSC
    total_questions = db.Column(db.Integer)
    total_marks = db.Column(db.Integer)
    duration_minutes = db.Column(db.Integer)
    negative_marking = db.Column(db.Float, default=0.33)
    subject_distribution = db.Column(db.Text)  # JSON: {subject: count}
    status = db.Column(db.String(20), default='generating')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    questions = db.relationship('PredictiveQ', backref='paper', lazy=True, cascade='all, delete-orphan')


class PredictiveQ(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('predictive_paper.id'), nullable=False)
    q_number = db.Column(db.Integer)
    subject = db.Column(db.String(100))
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    correct = db.Column(db.String(2))
    explanation = db.Column(db.Text)
    source_type = db.Column(db.String(20))   # PYQ, AI_NEW, HYBRID
    source_year = db.Column(db.Integer)
    qtype = db.Column(db.String(30))         # MCQ, Statement, Match, Sequence, Mains


# Exam type presets
PAPER_PRESETS = {
    'UPSC_PRELIMS_GS': {
        'label': 'UPSC Prelims GS Paper I',
        'total_q': 100, 'marks': 200, 'minutes': 120, 'neg': 0.66,
        'distribution': {'History':14,'Polity':15,'Geography':14,'Economy':14,'Environment':13,
                         'Science':10,'Current Affairs':15,'Art & Culture':5}
    },
    'UPSC_CSAT': {
        'label': 'UPSC Prelims CSAT Paper II',
        'total_q': 80, 'marks': 200, 'minutes': 120, 'neg': 0.83,
        'distribution': {'Comprehension':28,'Logical Reasoning':22,'Analytical':12,
                         'Numeracy':12,'Data Interpretation':6}
    },
    'UPSC_MAINS_GS1': {'label':'UPSC Mains GS Paper I','total_q':20,'marks':250,'minutes':180,'neg':0,'distribution':{'History':4,'Art & Culture':3,'Society':4,'Geography':5,'Modern India':4}},
    'UPSC_MAINS_GS2': {'label':'UPSC Mains GS Paper II','total_q':20,'marks':250,'minutes':180,'neg':0,'distribution':{'Polity':6,'Governance':5,'Social Justice':4,'International Relations':5}},
    'UPSC_MAINS_GS3': {'label':'UPSC Mains GS Paper III','total_q':20,'marks':250,'minutes':180,'neg':0,'distribution':{'Economy':6,'Agriculture':3,'Science & Tech':3,'Environment':3,'Security':5}},
    'UPSC_MAINS_GS4': {'label':'UPSC Mains GS Paper IV (Ethics)','total_q':12,'marks':250,'minutes':180,'neg':0,'distribution':{'Theory':4,'Case Studies':8}},
    'UPSC_ESSAY':    {'label':'UPSC Mains Essay Paper','total_q':2,'marks':250,'minutes':180,'neg':0,'distribution':{'Philosophical':1,'Contemporary':1}},
    'UPPSC_PRELIMS': {
        'label':'UPPSC Prelims GS Paper I',
        'total_q':150,'marks':200,'minutes':120,'neg':0.33,
        'distribution': {'History':18,'Polity':18,'Geography':15,'Economy':16,'Science':14,
                         'Current Affairs':17,'UP Special':16,'Environment':14,'Art & Culture':11,'Science & Tech':11}
    },
    'BPSC_PRELIMS': {'label':'BPSC Prelims GS','total_q':150,'marks':150,'minutes':120,'neg':0.25,
                     'distribution': {'History':20,'Polity':18,'Geography':20,'Economy':15,'Science':15,'Bihar Special':20,'Current Affairs':22,'Environment':10,'Static GK':10}},
    'MPPSC_PRELIMS': {'label':'MPPSC Prelims GS','total_q':100,'marks':100,'minutes':120,'neg':0.33,
                      'distribution': {'History':12,'Polity':12,'Geography':12,'Economy':10,'Science':10,'MP Special':15,'Current Affairs':15,'Environment':8,'Static':6}},
}


def _gen_predictive_q_for_slot(subject, exam_type, pyq_context, pattern_hint):
    """Generate one question for a slot — mix of PYQ pattern + AI new."""
    cfg = load_config()
    if exam_type in ('UPSC_PRELIMS_GS','UPPSC_PRELIMS','BPSC_PRELIMS','MPPSC_PRELIMS','UPSC_CSAT'):
        system = ("You are an exam paper setter. Generate ONE MCQ in UPSC/State PSC pattern for the "
                  "given subject. Test analytical understanding, not trivia. Use one of these patterns: "
                  "statement-based (I, II, III), match-the-following, arrange-in-sequence, "
                  "'With reference to X, consider the following', 'How many of the above are correct'. "
                  "Return strict JSON: "
                  '{"question":"...","option_a":"...","option_b":"...","option_c":"...","option_d":"...",'
                  '"correct":"A|B|C|D","explanation":"2 lines"}. '
                  "The question must be plausible as real exam question.")
        user = (f"SUBJECT: {subject}\nEXAM: {exam_type}\nPATTERN: {pattern_hint}\n\n"
                f"Recent related PYQ context:\n{pyq_context[:600] if pyq_context else 'None'}\n\n"
                "Generate one fresh MCQ.")
    else:
        # Mains/Essay
        system = ("You are a UPSC Mains paper setter. Generate ONE Mains-style question "
                  "(150 or 250 words) with proper directive word (Discuss/Examine/Critically examine/"
                  "Analyse/Comment/Evaluate/Elucidate). Return strict JSON: "
                  '{"question":"... (150 words)","directive":"Discuss","marks":10,"explanation":"Model skeleton in 4-5 bullets"}')
        user = f"SUBJECT: {subject}\nEXAM: {exam_type}\nRecent PYQ context:\n{pyq_context[:500] if pyq_context else 'None'}\n\nGenerate."
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=600)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        return _lazy_json.loads(content)
    except Exception:
        return None


@app.route('/predictive-paper')
def predictive_paper_home():
    papers = PredictivePaper.query.order_by(PredictivePaper.created_at.desc()).limit(30).all()
    return render_template('predictive_home.html', papers=papers, presets=PAPER_PRESETS)


@app.route('/predictive-paper/create', methods=['POST'])
def predictive_paper_create():
    key = request.form.get('exam_type', 'UPSC_PRELIMS_GS')
    p = PAPER_PRESETS.get(key, PAPER_PRESETS['UPSC_PRELIMS_GS'])
    paper = PredictivePaper(
        name=f"{p['label']} — {_dt.now().strftime('%d %b %Y')}",
        exam_type=key, total_questions=p['total_q'], total_marks=p['marks'],
        duration_minutes=p['minutes'], negative_marking=p['neg'],
        subject_distribution=_lazy_json.dumps(p['distribution']),
        status='generating'
    )
    db.session.add(paper); db.session.commit()
    return redirect(url_for('predictive_paper_generate', pid=paper.id))


@app.route('/predictive-paper/<int:pid>/generate', methods=['GET', 'POST'])
def predictive_paper_generate(pid):
    paper = PredictivePaper.query.get_or_404(pid)
    dist = _lazy_json.loads(paper.subject_distribution or '{}')
    is_mcq = paper.exam_type in ('UPSC_PRELIMS_GS','UPSC_CSAT','UPPSC_PRELIMS','BPSC_PRELIMS','MPPSC_PRELIMS')

    q_num = 1
    total_slots = sum(dist.values())

    for subject, count in dist.items():
        # Fetch existing PYQs from this subject
        pyq_qs = Question.query.filter(Question.topic.ilike(f'%{subject}%')).limit(count).all()
        used_ids = set()
        for pq in pyq_qs:
            if pq.id in used_ids: continue
            used_ids.add(pq.id)
            if q_num > paper.total_questions: break
            db.session.add(PredictiveQ(
                paper_id=paper.id, q_number=q_num, subject=subject,
                question=pq.text[:1500],
                correct=(pq.correct_answer or '').upper()[:1],
                explanation=pq.explanation or '',
                source_type='PYQ', source_year=pq.year,
                qtype='MCQ' if is_mcq else 'Mains'
            ))
            q_num += 1
        db.session.commit()

        # Fill remaining slots with AI-generated
        needed = count - len(pyq_qs)
        if needed <= 0: continue
        pyq_ctx = ' | '.join([q.text[:100] for q in pyq_qs[:3]])
        for i in range(needed):
            if q_num > paper.total_questions: break
            data = _gen_predictive_q_for_slot(subject, paper.exam_type, pyq_ctx, 'statement-based')
            if not data or not data.get('question'):
                # skip
                continue
            db.session.add(PredictiveQ(
                paper_id=paper.id, q_number=q_num, subject=subject,
                question=data.get('question','')[:1500],
                option_a=data.get('option_a','')[:500],
                option_b=data.get('option_b','')[:500],
                option_c=data.get('option_c','')[:500],
                option_d=data.get('option_d','')[:500],
                correct=(data.get('correct','') or '').upper()[:1],
                explanation=data.get('explanation','')[:1000],
                source_type='AI_NEW', qtype='MCQ' if is_mcq else 'Mains'
            ))
            q_num += 1
            db.session.commit()
            _lazy_time.sleep(1.5)

    paper.status = 'ready'
    db.session.commit()
    flash(f'Paper generated: {paper.total_questions} questions across {len(dist)} subjects.')
    return redirect(url_for('predictive_paper_view', pid=paper.id))


@app.route('/predictive-paper/<int:pid>')
def predictive_paper_view(pid):
    paper = PredictivePaper.query.get_or_404(pid)
    questions = PredictiveQ.query.filter_by(paper_id=paper.id).order_by(PredictiveQ.q_number).all()
    return render_template('predictive_view.html', paper=paper, questions=questions)


@app.route('/predictive-paper/<int:pid>/print')
def predictive_paper_print(pid):
    paper = PredictivePaper.query.get_or_404(pid)
    questions = PredictiveQ.query.filter_by(paper_id=paper.id).order_by(PredictiveQ.q_number).all()
    return render_template('predictive_print.html', paper=paper, questions=questions)


@app.route('/predictive-paper/<int:pid>/delete', methods=['POST'])
def predictive_paper_delete(pid):
    p = PredictivePaper.query.get_or_404(pid)
    db.session.delete(p); db.session.commit()
    return redirect(url_for('predictive_paper_home'))


# ---------- Optional Subject Hub ----------
OPTIONAL_SUBJECTS = {
    'PSIR': {'label': 'Political Science & International Relations', 'papers': ['Political Theory', 'Indian Government & Politics', 'Comparative Politics', 'International Relations', 'India & the World']},
    'Sociology': {'label': 'Sociology', 'papers': ['Sociology as Discipline', 'Sociology of India', 'Social Thinkers', 'Stratification', 'Social Change']},
    'History': {'label': 'History', 'papers': ['Ancient India', 'Medieval India', 'Modern India', 'World History', 'Post-Independence']},
    'Geography': {'label': 'Geography', 'papers': ['Physical Geography', 'Human Geography', 'Regional Planning', 'Indian Geography', 'Cartography']},
    'PublicAd': {'label': 'Public Administration', 'papers': ['Administrative Theory', 'Indian Administration', 'Public Policy', 'Governance', 'Development Admin']},
    'Anthropology': {'label': 'Anthropology', 'papers': ['Physical Anthropology', 'Social Anthropology', 'Prehistory', 'Indian Anthropology', 'Tribal Studies']},
    'Economics': {'label': 'Economics', 'papers': ['Microeconomics', 'Macroeconomics', 'Indian Economy', 'Public Finance', 'Development Economics']},
    'Philosophy': {'label': 'Philosophy', 'papers': ['Western Philosophy', 'Indian Philosophy', 'Ethics', 'Logic', 'Socio-Political Philosophy']},
    'Hindi': {'label': 'Hindi Literature', 'papers': ['Hindi Sahitya ka Itihas', 'Kavya', 'Gadya', 'Bhasha Vigyan', 'Prayojanmoolak Hindi']},
    'English': {'label': 'English Literature', 'papers': ['British Literature', 'American Literature', 'Indian Writing', 'Literary Criticism', 'Modern Literature']},
}


@app.route('/optional')
def optional_hub():
    return render_template('optional_hub.html', subjects=OPTIONAL_SUBJECTS)


@app.route('/optional/<key>')
def optional_subject(key):
    subj = OPTIONAL_SUBJECTS.get(key)
    if not subj:
        flash('Subject not found.')
        return redirect(url_for('optional_hub'))
    # Fetch PYQs matching this optional
    pyqs = Question.query.filter(
        Question.topic.ilike(f'%{subj["label"]}%') |
        Question.topic.ilike(f'%{key}%')
    ).limit(30).all()
    return render_template('optional_subject.html', key=key, subj=subj, pyqs=pyqs)


@app.route('/optional/<key>/generate-question', methods=['POST'])
def optional_generate_question(key):
    subj = OPTIONAL_SUBJECTS.get(key)
    if not subj:
        return {'error': 'Subject not found'}, 404
    paper = request.form.get('paper', subj['papers'][0])
    prompt = (f"You are a UPSC Optional Subject paper setter for {subj['label']}. "
              f"Generate ONE 20-mark Mains question from '{paper}' worth 250 words. "
              "Include: full question with directive word, model answer skeleton (5-6 bullets), "
              "and key thinkers/theories to cite. Return strict JSON: "
              '{"question":"...","skeleton":"...","references":"..."}')
    try:
        content, _ = _lazy_call_any_ai(prompt, f"TOPIC: {paper}. Generate now.", max_tokens=800)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        return _lazy_json.loads(content)
    except Exception as e:
        return {'error': str(e)[:200]}, 500


# ---------- Ethics Case Study Bank ----------
class EthicsCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300))
    scenario = db.Column(db.Text, nullable=False)
    stakeholders = db.Column(db.Text)
    dilemma = db.Column(db.Text)
    options = db.Column(db.Text)
    framework = db.Column(db.Text)
    verdict = db.Column(db.Text)
    source = db.Column(db.String(100))       # PYQ, AI_NEW
    year = db.Column(db.Integer)
    theme = db.Column(db.String(100))        # Integrity, Conflict, Whistleblowing, etc
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


ETHICS_THEMES = ['Integrity', 'Objectivity', 'Conflict of Interest', 'Whistleblowing',
                 'Public Service Values', 'Empathy', 'Accountability', 'Work Culture',
                 'Gender Justice', 'Environmental Ethics', 'Digital Ethics', 'Political Neutrality']


@app.route('/ethics')
def ethics_home():
    theme = request.args.get('theme', '').strip()
    q = EthicsCase.query
    if theme:
        q = q.filter(EthicsCase.theme == theme)
    cases = q.order_by(EthicsCase.created_at.desc()).limit(100).all()
    themes_present = sorted(set(c.theme for c in cases if c.theme))
    return render_template('ethics_home.html', cases=cases, themes=ETHICS_THEMES, themes_present=themes_present, active=theme)


@app.route('/ethics/generate', methods=['POST'])
def ethics_generate():
    theme = request.form.get('theme', 'Integrity')
    prompt = (f"You are a UPSC GS4 (Ethics) paper setter. Generate ONE realistic case study "
              f"(250 words) on the theme '{theme}' — set in Indian administration context. "
              "Return strict JSON:\n"
              '{"title":"...","scenario":"3-4 paragraph realistic case with 3-4 stakeholders",'
              '"stakeholders":"bullet list of key stakeholders and their interests",'
              '"dilemma":"core ethical dilemma in 2 lines",'
              '"options":"3-4 possible courses of action with pros/cons each",'
              '"framework":"Apply: (a) values involved, (b) ethical principles from GS4 syllabus, '
              '(c) relevant thinkers/case law, (d) consequentialist + deontological view",'
              '"verdict":"Recommended action + reasoning in 4-5 lines"}')
    try:
        content, _ = _lazy_call_any_ai(prompt, f"Theme: {theme}. Generate case study now.", max_tokens=1500)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        data = _lazy_json.loads(content)
        case = EthicsCase(
            title=data.get('title','')[:300],
            scenario=data.get('scenario',''),
            stakeholders=data.get('stakeholders',''),
            dilemma=data.get('dilemma',''),
            options=data.get('options',''),
            framework=data.get('framework',''),
            verdict=data.get('verdict',''),
            source='AI_NEW', theme=theme
        )
        db.session.add(case); db.session.commit()
        flash(f'Case study on "{theme}" generated.')
    except Exception as e:
        flash(f'Failed: {str(e)[:150]}')
    return redirect(url_for('ethics_home'))


@app.route('/ethics/<int:cid>')
def ethics_view(cid):
    case = EthicsCase.query.get_or_404(cid)
    return render_template('ethics_view.html', case=case)


@app.route('/ethics/<int:cid>/delete', methods=['POST'])
def ethics_delete(cid):
    c = EthicsCase.query.get_or_404(cid)
    db.session.delete(c); db.session.commit()
    return redirect(url_for('ethics_home'))


@app.route('/ethics/preload', methods=['POST'])
def ethics_preload():
    """Generate 5 cases across different themes in one go."""
    themes = ['Integrity', 'Conflict of Interest', 'Whistleblowing', 'Empathy', 'Public Service Values']
    created = 0
    for t in themes:
        prompt = (f"UPSC GS4 Ethics case study on theme: {t}. Indian administration context, 250 words. "
                  "Strict JSON: {title, scenario, stakeholders, dilemma, options, framework, verdict}")
        try:
            content, _ = _lazy_call_any_ai(prompt, f"Theme: {t}.", max_tokens=1400)
            content = content.strip().strip('`').replace('```json','').replace('```','').strip()
            data = _lazy_json.loads(content)
            db.session.add(EthicsCase(
                title=data.get('title','')[:300], scenario=data.get('scenario',''),
                stakeholders=data.get('stakeholders',''), dilemma=data.get('dilemma',''),
                options=data.get('options',''), framework=data.get('framework',''),
                verdict=data.get('verdict',''), source='AI_NEW', theme=t
            ))
            db.session.commit(); created += 1
            _lazy_time.sleep(1.5)
        except Exception:
            continue
    flash(f'Preloaded {created} case studies across themes.')
    return redirect(url_for('ethics_home'))


# ---------- Essay Topics Hub ----------
class EssayTopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(400), nullable=False)
    category = db.Column(db.String(100))     # Philosophical, Contemporary, Quotation, Social
    difficulty = db.Column(db.String(20))    # Easy, Moderate, Hard
    pyq_year = db.Column(db.Integer)         # If this was an actual PYQ
    likely_2027 = db.Column(db.Boolean, default=False)
    overview = db.Column(db.Text)            # Opening thought
    dimensions = db.Column(db.Text)          # Multi-dimensional angles
    quotes = db.Column(db.Text)              # Relevant quotes to use
    data_points = db.Column(db.Text)         # Stats/facts to cite
    conclusion = db.Column(db.Text)          # Way forward
    source = db.Column(db.String(30))        # PYQ or AI_NEW
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


ESSAY_CATEGORIES = ['Philosophical', 'Contemporary', 'Society & Culture', 'Polity & Governance',
                    'Economy & Development', 'Science & Environment', 'Women & Youth', 'Education']


@app.route('/essay-hub')
def essay_hub():
    cat = request.args.get('cat', '').strip()
    q = EssayTopic.query
    if cat:
        q = q.filter(EssayTopic.category == cat)
    topics = q.order_by(EssayTopic.created_at.desc()).limit(200).all()
    pyq_topics = [t for t in topics if t.source == 'PYQ']
    ai_topics = [t for t in topics if t.source == 'AI_NEW']
    return render_template('essay_hub.html',
                           pyq_topics=pyq_topics,
                           ai_topics=ai_topics,
                           categories=ESSAY_CATEGORIES,
                           active=cat)


@app.route('/essay-hub/generate', methods=['POST'])
def essay_generate():
    cat = request.form.get('cat', 'Philosophical')
    context = request.form.get('context', '').strip()

    system = (f"You are a UPSC Essay paper setter. Generate ONE 125-mark Essay topic "
              f"in the '{cat}' category. Give: title (in quotes for quotation topics), "
              "opening thought, 5-6 dimensions to explore, 3 relevant quotes, 3 data points, "
              "conclusion direction. Return strict JSON:\n"
              '{"title":"...","difficulty":"Easy|Moderate|Hard","overview":"...",'
              '"dimensions":"1. ...\\n2. ...\\n3. ...","quotes":"1. ...\\n2. ...",'
              '"data_points":"1. ...\\n2. ...","conclusion":"..."}')
    user = f"Category: {cat}\nExtra context: {context or 'None'}\n\nGenerate one Essay topic."
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=1400)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        data = _lazy_json.loads(content)
        db.session.add(EssayTopic(
            title=data.get('title','')[:400],
            category=cat,
            difficulty=data.get('difficulty','Moderate')[:20],
            overview=data.get('overview',''),
            dimensions=data.get('dimensions',''),
            quotes=data.get('quotes',''),
            data_points=data.get('data_points',''),
            conclusion=data.get('conclusion',''),
            source='AI_NEW'
        ))
        db.session.commit()
        flash(f'Essay topic generated: {data.get("title","")[:60]}')
    except Exception as e:
        flash(f'Failed: {str(e)[:150]}')
    return redirect(url_for('essay_hub'))


@app.route('/essay-hub/seed-pyq', methods=['POST'])
def essay_seed_pyq():
    """Seed real UPSC Essay PYQ topics (2015-2024)."""
    PYQS = [
        ('"Forests are the best case studies for economic excellence"', 'Philosophical', 2024, 'Moderate'),
        ('"Poets are the unacknowledged legislators of the world"', 'Philosophical', 2024, 'Hard'),
        ('"History is a series of victories won by the scientific man over the romantic man"', 'Philosophical', 2023, 'Moderate'),
        ('"A ship in harbour is safe, but that is not what a ship is for"', 'Philosophical', 2023, 'Hard'),
        ('"Simplicity is the ultimate sophistication"', 'Philosophical', 2022, 'Easy'),
        ('"The time to repair the roof is when the sun is shining"', 'Contemporary', 2022, 'Moderate'),
        ('"You cannot step twice in the same river"', 'Philosophical', 2021, 'Hard'),
        ('"There is nothing either good or bad but thinking makes it so"', 'Philosophical', 2021, 'Hard'),
        ('"Life is a long lesson in humility"', 'Philosophical', 2020, 'Moderate'),
        ('"Wisdom finds truth but ego feels it"', 'Philosophical', 2019, 'Hard'),
        ('"Need brings wants but wants bring suffering"', 'Contemporary', 2019, 'Moderate'),
        ('"Reality is merely an illusion, albeit a very persistent one"', 'Philosophical', 2018, 'Hard'),
        ('"A people that values its privileges above its principles loses both"', 'Contemporary', 2017, 'Moderate'),
        ('"Joy is the simplest form of gratitude"', 'Philosophical', 2016, 'Easy'),
        ('"Fulfillment of human life is possible through sacrifice and not accumulation"', 'Philosophical', 2015, 'Moderate'),
    ]
    created = 0
    for title, cat, year, diff in PYQS:
        existing = EssayTopic.query.filter_by(title=title).first()
        if existing:
            continue
        db.session.add(EssayTopic(
            title=title, category=cat, difficulty=diff, pyq_year=year,
            source='PYQ',
            likely_2027=True if year >= 2022 else False
        ))
        created += 1
    db.session.commit()
    flash(f'Seeded {created} real UPSC Essay PYQ topics (2015-2024).')
    return redirect(url_for('essay_hub'))


@app.route('/essay-hub/<int:tid>/expand', methods=['POST'])
def essay_expand(tid):
    """Generate full framework for a stored topic."""
    topic = EssayTopic.query.get_or_404(tid)
    if topic.dimensions:
        return redirect(url_for('essay_view', tid=topic.id))
    system = (f"You are a UPSC Essay mentor. For the topic \"{topic.title}\", create: "
              "opening thought (2-3 lines), 6 dimensions to explore, 3-4 relevant quotes with authors, "
              "3-4 data points/statistics, conclusion direction. Strict JSON: "
              '{"overview":"...","dimensions":"...","quotes":"...","data_points":"...","conclusion":"..."}')
    try:
        content, _ = _lazy_call_any_ai(system, f"Expand topic: {topic.title}", max_tokens=1400)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        data = _lazy_json.loads(content)
        topic.overview = data.get('overview','')
        topic.dimensions = data.get('dimensions','')
        topic.quotes = data.get('quotes','')
        topic.data_points = data.get('data_points','')
        topic.conclusion = data.get('conclusion','')
        db.session.commit()
    except Exception as e:
        flash(f'Expand failed: {str(e)[:150]}')
    return redirect(url_for('essay_view', tid=topic.id))


@app.route('/essay-hub/<int:tid>')
def essay_view(tid):
    topic = EssayTopic.query.get_or_404(tid)
    return render_template('essay_view.html', topic=topic)


@app.route('/essay-hub/<int:tid>/delete', methods=['POST'])
def essay_delete(tid):
    t = EssayTopic.query.get_or_404(tid)
    db.session.delete(t); db.session.commit()
    return redirect(url_for('essay_hub'))


# ---------- Admit Card Generator ----------
class AdmitCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_name = db.Column(db.String(300))
    exam_body = db.Column(db.String(50))       # UPSC, UPPSC, BPSC, MPPSC, SSC
    candidate_name = db.Column(db.String(200))
    roll_number = db.Column(db.String(50))
    registration_no = db.Column(db.String(50))
    father_name = db.Column(db.String(200))
    mother_name = db.Column(db.String(200))
    dob = db.Column(db.String(20))
    gender = db.Column(db.String(20))
    category = db.Column(db.String(30))
    photo_url = db.Column(db.String(500))
    signature_url = db.Column(db.String(500))
    exam_date = db.Column(db.String(20))
    exam_time = db.Column(db.String(50))
    reporting_time = db.Column(db.String(50))
    exam_centre = db.Column(db.String(400))
    exam_city = db.Column(db.String(200))
    exam_code = db.Column(db.String(50))
    paper_details = db.Column(db.Text)         # JSON: [{paper: 'GS I', time: '09:30-11:30'}, ...]
    instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


ADMIT_PRESETS = {
    'UPSC_PRELIMS': {
        'exam_body': 'UPSC',
        'exam_name': 'Civil Services (Preliminary) Examination, 2026',
        'exam_code': '08/CSE(P)/2026',
        'papers': [{'paper':'Paper I — General Studies', 'time':'09:30 AM to 11:30 AM'},
                   {'paper':'Paper II — CSAT (Aptitude)', 'time':'02:30 PM to 04:30 PM'}],
    },
    'UPSC_MAINS': {
        'exam_body': 'UPSC',
        'exam_name': 'Civil Services (Main) Examination, 2026',
        'exam_code': '09/CSE(M)/2026',
        'papers': [{'paper':'Paper A — Indian Language', 'time':'09:00 AM to 12:00 PM'},
                   {'paper':'Paper B — English', 'time':'02:30 PM to 05:30 PM'}],
    },
    'UPPSC_PRELIMS': {
        'exam_body': 'UPPSC',
        'exam_name': 'Combined State / Upper Subordinate Services (Prelims) Exam, 2026',
        'exam_code': 'A-1/E-1/2026',
        'papers': [{'paper':'General Studies Paper I', 'time':'09:30 AM to 11:30 AM'},
                   {'paper':'General Studies Paper II (CSAT)', 'time':'02:30 PM to 04:30 PM'}],
    },
    'BPSC_PRELIMS': {
        'exam_body': 'BPSC',
        'exam_name': '68th Combined Competitive Examination (Prelims), 2026',
        'exam_code': 'CCE-68/2026',
        'papers': [{'paper':'General Studies', 'time':'12:00 PM to 02:00 PM'}],
    },
    'SSC_CGL': {
        'exam_body': 'SSC',
        'exam_name': 'Combined Graduate Level Examination (Tier-1), 2026',
        'exam_code': 'SSC/CGL/2026',
        'papers': [{'paper':'Session I', 'time':'09:00 AM to 10:00 AM'},
                   {'paper':'Session II', 'time':'10:30 AM to 12:30 PM'}],
    },
}

DEFAULT_INSTRUCTIONS = """1. Use of BLACK BALL POINT PEN for marking the OMR sheet is mandatory. Answers other than those marked by black ball point pen will NOT be evaluated.
2. Bring this e-Admit Card (printout), along with the ORIGINAL photo identity card as mentioned above, and BLACK BALL POINT PEN in each session to secure admission to the examination hall.
3. e-Admit Card must be preserved till the declaration of final results.
4. You are advised to enter the examination venue well in time (preferably one and a half hours before the commencement of the session) for face authentication/identity verification and frisking.
5. Please note that the entry into the examination venue shall be closed 30 minutes before the scheduled commencement of the examination.
6. Candidates must NOT carry any prohibited items (mobile phones, Bluetooth devices, calculators, books, notes) into the examination hall."""


@app.route('/admit-card')
def admit_card_home():
    cards = AdmitCard.query.order_by(AdmitCard.created_at.desc()).limit(30).all()
    return render_template('admit_home.html', cards=cards, presets=ADMIT_PRESETS)


@app.route('/admit-card/create', methods=['GET', 'POST'])
def admit_card_create():
    if request.method == 'GET':
        return render_template('admit_create.html', presets=ADMIT_PRESETS, defaults=DEFAULT_INSTRUCTIONS)
    preset_key = request.form.get('preset', 'UPSC_PRELIMS')
    preset = ADMIT_PRESETS.get(preset_key, ADMIT_PRESETS['UPSC_PRELIMS'])
    photo_url = request.form.get('photo_url', '').strip()
    if 'photo_file' in request.files:
        pf = request.files['photo_file']
        if pf and pf.filename:
            os.makedirs('static/admit_photos', exist_ok=True)
            fname = secure_filename(f"photo_{int(__import__('time').time())}_{pf.filename}")
            pf.save(os.path.join('static/admit_photos', fname))
            photo_url = f'/static/admit_photos/{fname}'
    sig_url = request.form.get('signature_url', '').strip()
    if 'signature_file' in request.files:
        sf = request.files['signature_file']
        if sf and sf.filename:
            os.makedirs('static/admit_photos', exist_ok=True)
            fname = secure_filename(f"sign_{int(__import__('time').time())}_{sf.filename}")
            sf.save(os.path.join('static/admit_photos', fname))
            sig_url = f'/static/admit_photos/{fname}'

    card = AdmitCard(
        exam_name=request.form.get('exam_name') or preset['exam_name'],
        exam_body=preset['exam_body'],
        exam_code=request.form.get('exam_code') or preset['exam_code'],
        candidate_name=request.form.get('candidate_name', '').strip(),
        roll_number=request.form.get('roll_number', '').strip(),
        registration_no=request.form.get('registration_no', '').strip(),
        father_name=request.form.get('father_name', '').strip(),
        mother_name=request.form.get('mother_name', '').strip(),
        dob=request.form.get('dob', '').strip(),
        gender=request.form.get('gender', '').strip(),
        category=request.form.get('category', '').strip(),
        photo_url=photo_url,
        signature_url=sig_url,
        exam_date=request.form.get('exam_date', '').strip(),
        exam_time=request.form.get('exam_time', '').strip(),
        reporting_time=request.form.get('reporting_time', '').strip(),
        exam_centre=request.form.get('exam_centre', '').strip(),
        exam_city=request.form.get('exam_city', '').strip(),
        paper_details=_lazy_json.dumps(preset['papers']),
        instructions=request.form.get('instructions') or DEFAULT_INSTRUCTIONS
    )
    db.session.add(card); db.session.commit()
    return redirect(url_for('admit_card_view', cid=card.id))


@app.route('/admit-card/<int:cid>')
def admit_card_view(cid):
    card = AdmitCard.query.get_or_404(cid)
    try:
        papers = _lazy_json.loads(card.paper_details or '[]')
    except Exception:
        papers = []
    return render_template('admit_view.html', card=card, papers=papers)


@app.route('/admit-card/<int:cid>/print')
def admit_card_print(cid):
    card = AdmitCard.query.get_or_404(cid)
    try:
        papers = _lazy_json.loads(card.paper_details or '[]')
    except Exception:
        papers = []
    return render_template('admit_print.html', card=card, papers=papers)


@app.route('/admit-card/<int:cid>/delete', methods=['POST'])
def admit_card_delete(cid):
    c = AdmitCard.query.get_or_404(cid)
    db.session.delete(c); db.session.commit()
    return redirect(url_for('admit_card_home'))


# ---------- Fusion Prediction Engine ----------
class PredictionRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    exam_type = db.Column(db.String(50))
    total_topics = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    topics = db.relationship('PredictionTopic', backref='run', lazy=True, cascade='all, delete-orphan')


class PredictionTopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('prediction_run.id'), nullable=False)
    topic = db.Column(db.String(300), nullable=False)
    subject = db.Column(db.String(100))
    scenario = db.Column(db.String(30))
    probability = db.Column(db.Float)
    pyq_count = db.Column(db.Integer, default=0)
    last_year = db.Column(db.Integer)
    cycle_due = db.Column(db.Boolean, default=False)
    reason = db.Column(db.Text)
    predicted_q = db.Column(db.Text)
    answer_hint = db.Column(db.Text)
    priority = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


def _fusion_score_topics(exam_type='UPSC_PRELIMS'):
    """7-layer scoring: PYQ freq + recency + cycle + subject spread + news."""
    from collections import Counter, defaultdict
    from datetime import datetime as _fdt
    year_now = _fdt.now().year

    # Layer 1 + 2: PYQ frequency & recency
    pyq_data = defaultdict(lambda: {'count': 0, 'years': [], 'subjects': Counter()})
    qs = Question.query.filter(Question.topic.isnot(None)).all()
    for q in qs:
        t = (q.topic or '').strip().title()
        if not t or len(t) < 3:
            continue
        pyq_data[t]['count'] += 1
        if q.year:
            pyq_data[t]['years'].append(q.year)
        if q.paper and q.paper.subject:
            pyq_data[t]['subjects'][q.paper.subject] += 1

    # Layer 4: News-current affairs linkage
    news_keywords = Counter()
    try:
        for art in NewsArticle.query.order_by(NewsArticle.fetched_at.desc()).limit(200).all():
            text = ((art.title or '') + ' ' + (art.summary_raw or '')).lower()
            for word in ['supreme court','constitution','rbi','gdp','climate','isro','parliament',
                         'bill','scheme','policy','budget','treaty','summit','election']:
                if word in text:
                    news_keywords[word] += 1
    except Exception:
        pass

    # Layer 5 + 6: Score each topic
    scored = []
    for topic, info in pyq_data.items():
        count = info['count']
        years = info['years']
        if not years:
            continue
        last_seen = max(years)
        years_since = year_now - last_seen
        distinct_years = len(set(years))

        recent_count = sum(1 for y in years if y >= year_now - 3)
        mid_count = sum(1 for y in years if year_now - 5 <= y < year_now - 3)
        older_count = count - recent_count - mid_count

        # Layered scoring
        weighted = recent_count * 3.0 + mid_count * 2.0 + older_count * 1.0
        spread_bonus = distinct_years * 0.5
        cycle_bonus = 3.0 if (3 <= years_since < 10) else 0.0
        news_bonus = 0.0
        topic_lower = topic.lower()
        for kw, freq in news_keywords.items():
            if kw in topic_lower or any(w in topic_lower for w in kw.split()):
                news_bonus += min(2.0, freq * 0.3)

        raw_score = weighted + spread_bonus + cycle_bonus + news_bonus
        subject = info['subjects'].most_common(1)[0][0] if info['subjects'] else 'General'

        scored.append({
            'topic': topic,
            'subject': subject,
            'raw_score': raw_score,
            'pyq_count': count,
            'last_year': last_seen,
            'years_since': years_since,
            'cycle_due': 3 <= years_since < 10,
            'distinct_years': distinct_years,
            'news_bonus': round(news_bonus, 2)
        })

    if not scored:
        return []

    # Normalize to 15-95%
    max_raw = max(s['raw_score'] for s in scored) or 1
    for s in scored:
        s['probability'] = round(min(95.0, max(15.0, (s['raw_score'] / max_raw) * 85 + 10)), 1)

    scored.sort(key=lambda x: -x['probability'])
    return scored[:80]


@app.route('/fusion')
def fusion_home():
    runs = PredictionRun.query.order_by(PredictionRun.created_at.desc()).limit(20).all()
    return render_template('fusion_home.html', runs=runs)


@app.route('/fusion/start', methods=['POST'])
def fusion_start():
    name = (request.form.get('name') or '').strip()
    if not name:
        name = f"Fusion Run {_dt.now().strftime('%d %b %Y %H:%M')}"
    exam_type = request.form.get('exam_type', 'UPSC_PRELIMS')
    run = PredictionRun(name=name, exam_type=exam_type)
    db.session.add(run)
    db.session.commit()
    return redirect(url_for('fusion_run', rid=run.id))


@app.route('/fusion/<int:rid>')
def fusion_run(rid):
    run = PredictionRun.query.get_or_404(rid)
    topics = PredictionTopic.query.filter_by(run_id=rid).order_by(PredictionTopic.priority).all()
    perennial = [t for t in topics if t.scenario == 'Perennial']
    rising = [t for t in topics if t.scenario == 'Rising']
    wildcard = [t for t in topics if t.scenario == 'Wildcard']
    return render_template('fusion_run.html',
                           run=run, topics=topics,
                           perennial=perennial,
                           rising=rising,
                           wildcard=wildcard)


@app.route('/fusion/<int:rid>/compute', methods=['POST'])
def fusion_compute(rid):
    run = PredictionRun.query.get_or_404(rid)
    if PredictionTopic.query.filter_by(run_id=rid).count() > 0:
        flash('Topics already computed for this run.')
        return redirect(url_for('fusion_run', rid=rid))

    scored = _fusion_score_topics(run.exam_type)
    if not scored:
        flash('No PYQ data available. Upload past papers and run Auto-Extract first.')
        return redirect(url_for('fusion_run', rid=rid))

    total = len(scored)
    for i, s in enumerate(scored):
        if i < total * 0.4:
            scenario = 'Perennial'
        elif i < total * 0.8:
            scenario = 'Rising'
        else:
            scenario = 'Wildcard'

        reason = (f"PYQ count: {s['pyq_count']} · Last seen: {s['last_year']} · "
                  f"Years spread: {s['distinct_years']}"
                  + (f" · Cycle due" if s['cycle_due'] else "")
                  + (f" · News boost +{s['news_bonus']}" if s['news_bonus'] > 0 else ""))

        db.session.add(PredictionTopic(
            run_id=rid,
            topic=s['topic'][:300],
            subject=s['subject'][:100] if s['subject'] else 'General',
            scenario=scenario,
            probability=s['probability'],
            pyq_count=s['pyq_count'],
            last_year=s['last_year'],
            cycle_due=s['cycle_due'],
            reason=reason,
            priority=i + 1
        ))
    run.total_topics = total
    db.session.commit()
    flash(f'Computed {total} topic predictions across 3 scenarios.')
    return redirect(url_for('fusion_run', rid=rid))


@app.route('/fusion/topic/<int:tid>/generate-q', methods=['POST'])
def fusion_generate_q(tid):
    t = PredictionTopic.query.get_or_404(tid)
    if t.predicted_q:
        return {'ok': True, 'q': t.predicted_q, 'answer': t.answer_hint or ''}

    system = (
        "You are a UPSC Prelims paper setter. For the topic below, generate ONE likely "
        "MCQ in UPSC format. Return strict JSON only:\n"
        '{"question":"full MCQ with statement-based or direct format",'
        '"options":"A) ...\\nB) ...\\nC) ...\\nD) ...",'
        '"correct":"A|B|C|D","answer":"2-3 line explanation"}\n'
        "Test analytical understanding, not trivia."
    )
    user = (f"TOPIC: {t.topic}\nSUBJECT: {t.subject}\n"
            f"SCENARIO: {t.scenario}\nProbability: {t.probability}%\n\n"
            "Generate likely question with answer.")
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=600)
        content = content.strip().strip('`').replace('```json', '').replace('```', '').strip()
        data = _lazy_json.loads(content)
        t.predicted_q = (data.get('question', '') + '\n\n' + data.get('options', ''))[:2500]
        t.answer_hint = ('Answer: ' + data.get('correct', '') + '\n\n' + data.get('answer', ''))[:1500]
        db.session.commit()
        return {'ok': True, 'q': t.predicted_q, 'answer': t.answer_hint}
    except Exception as e:
        return {'error': str(e)[:200]}, 500


@app.route('/fusion/<int:rid>/delete', methods=['POST'])
def fusion_delete(rid):
    r = PredictionRun.query.get_or_404(rid)
    db.session.delete(r)
    db.session.commit()
    flash('Run deleted.')
    return redirect(url_for('fusion_home'))


# ---------- Advanced Answer Evaluator (7-Dimension Model) ----------
class AnswerEval(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    word_count = db.Column(db.Integer)
    paper_type = db.Column(db.String(20))       # GS1, GS2, GS3, GS4, Essay, Optional
    marks = db.Column(db.Integer, default=10)
    dim_scores = db.Column(db.Text)             # JSON {dim: score}
    overall = db.Column(db.Float)
    feedback = db.Column(db.Text)
    missing_points = db.Column(db.Text)
    strengths = db.Column(db.Text)
    weaknesses = db.Column(db.Text)
    model_skeleton = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


# UPSC-calibrated 7-dimension weights (from research)
EVAL_DIMENSIONS = {
    'comprehension':  {'name': 'Question Comprehension',    'weight': 2.0, 'max': 10},
    'factual':        {'name': 'Factual Accuracy',          'weight': 1.5, 'max': 10},
    'analytical':     {'name': 'Analytical Depth',          'weight': 2.0, 'max': 10},
    'coverage':       {'name': 'Key Points Coverage',       'weight': 1.5, 'max': 10},
    'current':        {'name': 'Current Affairs Integration','weight': 1.5, 'max': 10},
    'structure':      {'name': 'Answer Structure',          'weight': 1.5, 'max': 10},
    'density':        {'name': 'Point Density',             'weight': 1.0, 'max': 10},
}

# Paper-specific CA weight adjustments
CA_WEIGHTS_BY_PAPER = {'GS1': 0.5, 'GS2': 1.5, 'GS3': 1.5, 'GS4': 1.0, 'Essay': 1.2, 'Optional': 0.8}


@app.route('/adv-eval')
def adv_eval_home():
    evals = AnswerEval.query.order_by(AnswerEval.created_at.desc()).limit(50).all()
    avg = sum(e.overall for e in evals if e.overall) / len(evals) if evals else 0
    return render_template('adv_eval_home.html', evals=evals, avg=round(avg, 1), dims=EVAL_DIMENSIONS)


@app.route('/adv-eval/submit', methods=['POST'])
def adv_eval_submit():
    question = request.form.get('question', '').strip()
    answer = request.form.get('answer', '').strip()
    paper_type = request.form.get('paper_type', 'GS2')
    marks = int(request.form.get('marks', 10))

    if len(question) < 10:
        flash('Enter a full question.'); return redirect(url_for('adv_eval_home'))
    if len(answer.split()) < 30:
        flash('Answer must be at least 30 words.'); return redirect(url_for('adv_eval_home'))

    ca_weight = CA_WEIGHTS_BY_PAPER.get(paper_type, 1.0)

    system = (
        "You are a strict UPSC Mains examiner. Score this answer on 7 dimensions, EACH out of 10:\n"
        "1. COMPREHENSION — did the answer address the actual demand of the question?\n"
        "2. FACTUAL — are facts, figures, dates, names accurate?\n"
        "3. ANALYTICAL — depth of reasoning, causes/effects/trade-offs?\n"
        "4. COVERAGE — all important points from syllabus covered?\n"
        f"5. CURRENT_AFFAIRS — recent examples, schemes, events (weight adjusted for {paper_type})?\n"
        "6. STRUCTURE — Intro-Body-Conclusion clarity, flow?\n"
        "7. DENSITY — substantive info per line (no filler)?\n\n"
        "Return STRICT JSON only:\n"
        '{"comprehension":N,"factual":N,"analytical":N,"coverage":N,'
        '"current":N,"structure":N,"density":N,'
        '"missing_points":"bullet list of 3-5 key concepts student missed",'
        '"strengths":"2-3 lines",'
        '"weaknesses":"2-3 lines",'
        '"model_skeleton":"bulleted 6-8 point ideal answer structure"}\n'
        "No filler. No preamble. Only JSON."
    )
    user = (f"QUESTION ({marks} marks):\n{question}\n\n"
            f"PAPER: {paper_type}\nWORD COUNT: {len(answer.split())}\n\n"
            f"STUDENT ANSWER:\n{answer}\n\nScore now.")

    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=1400)
        content = content.strip().strip('`').replace('```json', '').replace('```', '').strip()
        data = _lazy_json.loads(content)
    except Exception as e:
        flash(f'Evaluation failed: {str(e)[:150]}')
        return redirect(url_for('adv_eval_home'))

    # Compute weighted overall
    total_weight = 0
    weighted_sum = 0
    for k, dim in EVAL_DIMENSIONS.items():
        w = dim['weight']
        if k == 'current':
            w = w * ca_weight
        score = float(data.get(k, 0) or 0)
        weighted_sum += score * w
        total_weight += 10 * w
    overall = round((weighted_sum / total_weight) * marks, 2) if total_weight else 0

    ev = AnswerEval(
        question=question[:1500],
        answer=answer[:5000],
        word_count=len(answer.split()),
        paper_type=paper_type,
        marks=marks,
        dim_scores=_lazy_json.dumps({k: float(data.get(k, 0) or 0) for k in EVAL_DIMENSIONS}),
        overall=overall,
        feedback='',
        missing_points=data.get('missing_points', ''),
        strengths=data.get('strengths', ''),
        weaknesses=data.get('weaknesses', ''),
        model_skeleton=data.get('model_skeleton', '')
    )
    db.session.add(ev); db.session.commit()
    return redirect(url_for('adv_eval_view', eid=ev.id))


@app.route('/adv-eval/<int:eid>')
def adv_eval_view(eid):
    ev = AnswerEval.query.get_or_404(eid)
    try:
        scores = _lazy_json.loads(ev.dim_scores or '{}')
    except Exception:
        scores = {}
    ca_weight = CA_WEIGHTS_BY_PAPER.get(ev.paper_type, 1.0)
    # Build weighted contribution
    weighted = {}
    for k, dim in EVAL_DIMENSIONS.items():
        w = dim['weight'] * (ca_weight if k == 'current' else 1.0)
        weighted[k] = {
            'name': dim['name'],
            'score': scores.get(k, 0),
            'weight': w,
            'contribution': round(scores.get(k, 0) * w / 10, 2)
        }
    return render_template('adv_eval_view.html', ev=ev, weighted=weighted)


@app.route('/adv-eval/<int:eid>/delete', methods=['POST'])
def adv_eval_delete(eid):
    ev = AnswerEval.query.get_or_404(eid)
    db.session.delete(ev); db.session.commit()
    return redirect(url_for('adv_eval_home'))


# ---------- Simple Exam Trainer ----------
class SimpleExamAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_type = db.Column(db.String(50))
    subject = db.Column(db.String(50))
    question = db.Column(db.Text)
    user_answer = db.Column(db.String(5))
    correct_answer = db.Column(db.String(5))
    is_correct = db.Column(db.Boolean)
    attempted_at = db.Column(db.DateTime, default=db.func.current_timestamp())


SIMPLE_EXAMS = {
    'SSC_CGL':   {'label': 'SSC CGL', 'subjects': ['General Awareness','Quantitative Aptitude','Reasoning','English']},
    'SSC_CHSL':  {'label': 'SSC CHSL', 'subjects': ['General Awareness','Quantitative Aptitude','Reasoning','English']},
    'BANK_PO':   {'label': 'Bank PO', 'subjects': ['General Awareness','Quantitative Aptitude','Reasoning','English']},
    'BANK_CLERK':{'label': 'Bank Clerk', 'subjects': ['General Awareness','Quantitative Aptitude','Reasoning','English']},
    'RRB_NTPC':  {'label': 'RRB NTPC', 'subjects': ['General Awareness','Mathematics','Reasoning']},
    'RRB_GROUP_D':{'label': 'RRB Group D', 'subjects': ['General Science','Mathematics','Reasoning','General Awareness']},
    'UP_POLICE': {'label': 'UP Police Constable', 'subjects': ['General Knowledge','Reasoning','Numerical Aptitude','Mental Aptitude']},
    'UP_DAROGA': {'label': 'UP SI (Daroga)', 'subjects': ['General Knowledge','Reasoning','Numerical Aptitude','Law']},
    'BIHAR_POLICE':{'label': 'Bihar Police', 'subjects': ['General Knowledge','Reasoning','Numerical Aptitude','Hindi']},
    'DELHI_POLICE':{'label': 'Delhi Police', 'subjects': ['General Knowledge','Reasoning','Numerical Aptitude','English']},
}


# High-yield static topic banks (Lucent/Arihant style)
STATIC_TOPIC_MAP = {
    'General Awareness': ['Indian Polity Basics','Constitution Basics','Indian History','Geography','Economy Basics',
                          'Science Basics','Static GK','Current Affairs','Books & Authors','Sports',
                          'Awards & Honours','Important Days','Abbreviations','Full Forms','Currency & Capitals',
                          'State Symbols','National Parks','Rivers','Dams','Famous Personalities'],
    'General Knowledge': ['Indian History','Geography','Indian Polity','Economy','Science','Static GK',
                          'Current Affairs','UP Special','Sports','Books & Authors','Firsts in India',
                          'State Capitals','National Symbols','Important Days'],
    'General Science': ['Physics Basics','Chemistry Basics','Biology Basics','Human Body','Diseases',
                        'Vitamins & Minerals','Units of Measurement','Scientific Instruments','Inventions'],
    'Mathematics': ['Percentage','Average','Ratio','Profit & Loss','Time & Work','Speed Distance Time',
                    'Simple Interest','Compound Interest','Number System','HCF LCM','Algebra'],
    'Numerical Aptitude': ['Percentage','Average','Ratio','Profit & Loss','Time & Work','Speed Distance Time',
                           'Simple Interest','Number System'],
    'Reasoning': ['Series','Coding-Decoding','Blood Relations','Direction Sense','Syllogism','Analogy',
                  'Classification','Odd One Out','Number Puzzle','Alphabet Test'],
    'English': ['Synonyms','Antonyms','Idioms','One Word Substitution','Error Spotting','Fill in the Blanks',
                'Spelling','Sentence Correction'],
    'Hindi': ['पर्यायवाची','विलोम','मुहावरे','लोकोक्तियाँ','संधि','समास','वाक्य शुद्धि','तत्सम-तत्सम'],
    'Current Affairs': ['Recent Events','Government Schemes','Awards 2025-26','Appointments','Sports Events',
                        'International Affairs'],
    'Law': ['IPC Basics','CrPC Basics','Evidence Act','Constitutional Law Basics','Recent Judgments'],
    'Quantitative Aptitude': ['Percentage','Average','Ratio','Profit & Loss','Time & Work','Mensuration'],
}


def _simple_generate_q(exam_type, subject):
    """Generate one simple MCQ in Lucent/Arihant style."""
    topics = STATIC_TOPIC_MAP.get(subject, ['General Awareness'])
    import random as _rnd
    topic = _rnd.choice(topics)
    system = (
        f"You are a question setter for {exam_type} exams in India. Generate ONE simple "
        f"MCQ from '{topic}' — the kind found in Lucent GK / Arihant books. "
        "Direct factual question, not analytical. Return strict JSON:\n"
        '{"question":"...","option_a":"...","option_b":"...","option_c":"...","option_d":"...",'
        '"correct":"A|B|C|D","explanation":"one line"}'
    )
    user = f"Exam: {exam_type}\nSubject: {subject}\nTopic: {topic}\n\nGenerate one MCQ."
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=400)
        content = content.strip().strip('`').replace('```json', '').replace('```', '').strip()
        return _lazy_json.loads(content)
    except Exception as e:
        return None


@app.route('/simple-exam')
def simple_exam_home():
    # Get stats per exam
    from collections import defaultdict
    stats = defaultdict(lambda: {'t': 0, 'c': 0})
    for a in SimpleExamAttempt.query.all():
        stats[a.exam_type]['t'] += 1
        if a.is_correct:
            stats[a.exam_type]['c'] += 1
    stat_list = [{'exam': k, 'total': v['t'], 'correct': v['c'],
                  'accuracy': round(100 * v['c'] / v['t'], 1) if v['t'] else 0}
                 for k, v in stats.items()]
    return render_template('simple_home.html', exams=SIMPLE_EXAMS, stats=stat_list)


@app.route('/simple-exam/<exam>/<subject>')
def simple_exam_practice(exam, subject):
    info = SIMPLE_EXAMS.get(exam, {'label': exam})
    return render_template('simple_practice.html', exam=exam, exam_label=info['label'],
                           subject=subject, topics=STATIC_TOPIC_MAP.get(subject, []))


@app.route('/simple-exam/generate', methods=['POST'])
def simple_exam_generate():
    exam = request.form.get('exam')
    subject = request.form.get('subject')
    data = _simple_generate_q(exam, subject)
    if not data:
        return {'error': 'AI generation failed. Try again.'}, 500
    data['exam'] = exam
    data['subject'] = subject
    return data


@app.route('/simple-exam/submit', methods=['POST'])
def simple_exam_submit():
    exam = request.form.get('exam')
    subject = request.form.get('subject')
    question = request.form.get('question', '')
    user_ans = (request.form.get('user_answer') or '').upper()[:1]
    correct = (request.form.get('correct') or '').upper()[:1]
    is_correct = (user_ans == correct)
    db.session.add(SimpleExamAttempt(
        exam_type=exam, subject=subject, question=question[:500],
        user_answer=user_ans, correct_answer=correct, is_correct=is_correct
    ))
    db.session.commit()
    return {'ok': True, 'correct': is_correct, 'answer': correct}


@app.route('/simple-exam/stats')
def simple_exam_stats():
    from collections import defaultdict
    stats = defaultdict(lambda: {'t': 0, 'c': 0})
    for a in SimpleExamAttempt.query.all():
        key = f"{a.exam_type} · {a.subject}"
        stats[key]['t'] += 1
        if a.is_correct:
            stats[key]['c'] += 1
    rows = [{'key': k, 'total': v['t'], 'correct': v['c'],
             'accuracy': round(100 * v['c'] / v['t'], 1) if v['t'] else 0}
            for k, v in stats.items()]
    rows.sort(key=lambda x: x['accuracy'])
    return render_template('simple_stats.html', rows=rows)


# ---------- CSAT Specific Trainer ----------
# Add CSAT to SIMPLE_EXAMS (in place)
SIMPLE_EXAMS['UPSC_CSAT'] = {
    'label': 'UPSC CSAT (Paper II — Qualifying)',
    'subjects': ['Comprehension', 'Logical Reasoning', 'Basic Numeracy', 'Data Interpretation', 'Decision Making']
}

# Extend topic map
STATIC_TOPIC_MAP['Comprehension'] = [
    'Passage on Economy', 'Passage on Environment', 'Passage on Society',
    'Passage on Governance', 'Passage on Science', 'Passage on Culture',
    'Inference-based Passage', 'Assumption-based Passage', 'Tone-based Passage'
]
STATIC_TOPIC_MAP['Logical Reasoning'] = [
    'Syllogism', 'Blood Relations', 'Direction Sense', 'Coding-Decoding',
    'Statement & Assumption', 'Statement & Conclusion', 'Course of Action',
    'Cause & Effect', 'Series (Number/Letter)', 'Analogy', 'Odd One Out',
    'Seating Arrangement', 'Puzzles (Grouping)'
]
STATIC_TOPIC_MAP['Basic Numeracy'] = [
    'Number System', 'LCM/HCF', 'Percentage', 'Ratio & Proportion',
    'Average', 'Profit & Loss', 'Simple Interest', 'Compound Interest',
    'Time & Work', 'Time Speed Distance', 'Mixture & Alligation',
    'Permutation Combination', 'Probability', 'Mensuration Basics'
]
STATIC_TOPIC_MAP['Data Interpretation'] = [
    'Bar Graph', 'Line Graph', 'Pie Chart', 'Table-based DI', 'Mixed DI',
    'Caselet DI', 'Ratio-based DI'
]
STATIC_TOPIC_MAP['Decision Making'] = [
    'Ethical Dilemma', 'Public Service Scenario', 'Administrative Decision',
    'Resource Allocation', 'Crisis Management'
]


# CSAT strategy hints per section
CSAT_TIPS = {
    'Comprehension': 'Read the question first, then the passage. Answer ONLY what is asked. Do NOT bring outside knowledge. 2 min per question.',
    'Logical Reasoning': 'Attempt coding, series, blood relations first — highest accuracy. Save seating/puzzles for last (time-consuming).',
    'Basic Numeracy': 'SKIP if you cannot see the method in 20 seconds. Guess after eliminating 2 options. Class 6-10 NCERT-level is enough.',
    'Data Interpretation': 'Approximate, don\'t calculate exactly. Round numbers. Ratio-based DI is fastest.',
    'Decision Making': 'NO negative marking in this section. ATTEMPT ALL. Choose the most ethical, balanced, welfare-oriented option.'
}


class CSATSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    finished_at = db.Column(db.DateTime)
    total_attempted = db.Column(db.Integer, default=0)
    total_correct = db.Column(db.Integer, default=0)
    total_skipped = db.Column(db.Integer, default=0)
    score = db.Column(db.Float)
    passed = db.Column(db.Boolean)
    mode = db.Column(db.String(20))     # practice, sprint, full


class CSATQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('csat_session.id'), nullable=False)
    subject = db.Column(db.String(50))
    question = db.Column(db.Text)
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    correct = db.Column(db.String(5))
    explanation = db.Column(db.Text)
    user_answer = db.Column(db.String(5))
    is_correct = db.Column(db.Boolean)
    skipped = db.Column(db.Boolean, default=False)
    time_taken = db.Column(db.Integer)
    difficulty = db.Column(db.String(20))


@app.route('/csat')
def csat_home():
    # Pass stats — last 20 sessions
    sessions = CSATSession.query.order_by(CSATSession.started_at.desc()).limit(20).all()
    passed = sum(1 for s in sessions if s.passed)
    avg = round(sum(s.score for s in sessions if s.score) / len(sessions), 1) if sessions else 0
    return render_template('csat_home.html',
                           sessions=sessions,
                           passed=passed,
                           total=len(sessions),
                           avg=avg,
                           tips=CSAT_TIPS,
                           threshold=66.67)


@app.route('/csat/start', methods=['POST'])
def csat_start():
    mode = request.form.get('mode', 'practice')
    subject = request.form.get('subject', '')
    count = int(request.form.get('count', 10))
    sess = CSATSession(mode=mode)
    db.session.add(sess); db.session.flush()
    # Generate questions in parallel-ish (batched)
    for i in range(count):
        subj = subject if subject else _csat_pick_subject(mode, i)
        data = _csat_generate_q(subj)
        if not data:
            continue
        db.session.add(CSATQuestion(
            session_id=sess.id, subject=subj,
            question=data.get('question', ''),
            option_a=data.get('option_a', ''),
            option_b=data.get('option_b', ''),
            option_c=data.get('option_c', ''),
            option_d=data.get('option_d', ''),
            correct=(data.get('correct', '') or '').upper()[:1],
            explanation=data.get('explanation', ''),
            difficulty=data.get('difficulty', 'Moderate')
        ))
        db.session.commit()
        _lazy_time.sleep(1.2)
    return redirect(url_for('csat_take', sid=sess.id))


def _csat_pick_subject(mode, i):
    """Weighted subject pick for full/sprint mode."""
    if mode == 'sprint':
        # 30-Q sprint: 12 comprehension, 12 reasoning, 4 maths, 2 DI
        if i < 12: return 'Comprehension'
        if i < 24: return 'Logical Reasoning'
        if i < 28: return 'Basic Numeracy'
        return 'Data Interpretation'
    if mode == 'full':
        # 80-Q full: 25 comp, 30 reasoning, 15 maths, 10 DI
        if i < 25: return 'Comprehension'
        if i < 55: return 'Logical Reasoning'
        if i < 70: return 'Basic Numeracy'
        return 'Data Interpretation'
    # practice
    return 'Logical Reasoning'


def _csat_generate_q(subject):
    """Generate a CSAT-level MCQ with weighted difficulty."""
    import random as _rnd
    topics = STATIC_TOPIC_MAP.get(subject, ['Logical Reasoning'])
    topic = _rnd.choice(topics)

    if subject == 'Comprehension':
        system = (
            "You are a UPSC CSAT (Paper II) setter. Generate a reading comprehension MCQ. "
            "Include a passage of 150-200 words, then ONE question with 4 options. "
            "The question must test inference, assumption, tone, or main idea — NOT direct recall. "
            "Return strict JSON: "
            '{"passage":"...","question":"Q: ...","option_a":"...","option_b":"...","option_c":"...","option_d":"...",'
            '"correct":"A|B|C|D","explanation":"one line","difficulty":"Easy|Moderate|Hard"}'
        )
        user = f"Topic: {topic}. Generate a CSAT-level comprehension question."
    else:
        system = (
            f"You are a UPSC CSAT setter. Generate ONE MCQ for '{subject}' at CSAT difficulty — "
            "equivalent to Class 6-10 level, NOT JEE/NEET. "
            "Return strict JSON: "
            '{"question":"...","option_a":"...","option_b":"...","option_c":"...","option_d":"...",'
            '"correct":"A|B|C|D","explanation":"short method or reasoning","difficulty":"Easy|Moderate|Hard"}'
        )
        user = f"Subject: {subject}\nTopic: {topic}\n\nGenerate one CSAT-level MCQ."

    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=700)
        content = content.strip().strip('`').replace('```json', '').replace('```', '').strip()
        data = _lazy_json.loads(content)
        if subject == 'Comprehension' and data.get('passage'):
            data['question'] = 'PASSAGE:\n' + data['passage'] + '\n\nQUESTION:\n' + data.get('question', '')
        return data
    except Exception:
        return None


@app.route('/csat/<int:sid>')
def csat_take(sid):
    sess = CSATSession.query.get_or_404(sid)
    questions = CSATQuestion.query.filter_by(session_id=sid).all()
    return render_template('csat_take.html', sess=sess, questions=questions, tips=CSAT_TIPS)


@app.route('/csat/<int:sid>/submit', methods=['POST'])
def csat_submit(sid):
    sess = CSATSession.query.get_or_404(sid)
    questions = CSATQuestion.query.filter_by(session_id=sid).all()
    correct = wrong = skipped = 0
    for q in questions:
        ua = (request.form.get(f'q_{q.id}', '') or '').upper()[:1]
        if not ua:
            q.skipped = True
            skipped += 1
            continue
        q.user_answer = ua
        q.is_correct = (ua == (q.correct or ''))
        if q.is_correct: correct += 1
        else: wrong += 1
        try:
            q.time_taken = int(request.form.get(f't_{q.id}', 0) or 0)
        except Exception:
            pass
    # CSAT scoring: +2 correct, -0.66 wrong (only for non-decision-making)
    score = correct * 2 - wrong * 0.66
    sess.total_attempted = correct + wrong
    sess.total_correct = correct
    sess.total_skipped = skipped
    sess.score = round(score, 2)
    sess.passed = (score >= 66.67)
    sess.finished_at = _dt.now()
    db.session.commit()
    return redirect(url_for('csat_result', sid=sid))


@app.route('/csat/<int:sid>/result')
def csat_result(sid):
    sess = CSATSession.query.get_or_404(sid)
    questions = CSATQuestion.query.filter_by(session_id=sid).all()
    from collections import defaultdict
    sec_stats = defaultdict(lambda: {'t': 0, 'c': 0})
    for q in questions:
        if q.skipped: continue
        sec_stats[q.subject]['t'] += 1
        if q.is_correct: sec_stats[q.subject]['c'] += 1
    sec_list = [{'subj': k, 'total': v['t'], 'correct': v['c'],
                 'acc': round(100 * v['c'] / v['t'], 1) if v['t'] else 0}
                for k, v in sec_stats.items()]
    return render_template('csat_result.html', sess=sess, questions=questions, sec_list=sec_list, threshold=66.67)


# ---------- Topper Word Bank ----------
class TopperPhrase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phrase = db.Column(db.String(300), nullable=False)
    subject = db.Column(db.String(50))
    category = db.Column(db.String(50))
    power_level = db.Column(db.Integer, default=5)
    usage_count = db.Column(db.Integer, default=1)
    contexts = db.Column(db.Text)
    source = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class TopperCopy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topper_name = db.Column(db.String(200))
    year = db.Column(db.Integer)
    rank = db.Column(db.String(20))
    subject = db.Column(db.String(100))
    raw_text = db.Column(db.Text)
    filename = db.Column(db.String(300))
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())


HIGH_VALUE_PHRASES_SEED = [
    ("Constitutional morality", "Polity", "Constitutional", 9),
    ("Basic structure doctrine", "Polity", "Constitutional", 8),
    ("Separation of powers", "Polity", "Constitutional", 8),
    ("Rule of law", "Polity", "Constitutional", 9),
    ("Federal supremacy", "Polity", "Federalism", 7),
    ("Cooperative federalism", "Polity", "Federalism", 9),
    ("Competitive federalism", "Polity", "Federalism", 8),
    ("Last mile delivery", "Governance", "Service Delivery", 9),
    ("Whole of government approach", "Governance", "Administration", 9),
    ("Minimum government maximum governance", "Governance", "Administration", 8),
    ("Citizen-centric administration", "Governance", "Administration", 8),
    ("Good governance", "Governance", "Administration", 7),
    ("Transparency and accountability", "Governance", "Administration", 8),
    ("E-governance", "Governance", "Administration", 7),
    ("Inclusive growth", "Economy", "Development", 9),
    ("Trickle-down effect", "Economy", "Development", 7),
    ("Fiscal prudence", "Economy", "Fiscal", 8),
    ("Fiscal consolidation", "Economy", "Fiscal", 8),
    ("Monetary policy transmission", "Economy", "Monetary", 7),
    ("Balance of payments", "Economy", "External", 7),
    ("Current account deficit", "Economy", "External", 8),
    ("Ease of doing business", "Economy", "Reforms", 7),
    ("Atmanirbhar Bharat", "Economy", "Self-Reliance", 8),
    ("Sustainable development", "Environment", "Sustainability", 8),
    ("Climate justice", "Environment", "Climate", 9),
    ("Common but differentiated responsibilities", "Environment", "Climate", 8),
    ("Ecological security", "Environment", "Ecology", 8),
    ("Climate finance", "Environment", "Climate", 8),
    ("Environmental ethics", "Ethics", "Values", 7),
    ("Means and ends", "Ethics", "Values", 9),
    ("Conflict of interest", "Ethics", "Integrity", 9),
    ("Public trust doctrine", "Ethics", "Integrity", 8),
    ("Moral courage", "Ethics", "Integrity", 9),
    ("Ethical leadership", "Ethics", "Leadership", 8),
    ("Emotional intelligence", "Ethics", "Attitude", 9),
    ("Objectivity in public service", "Ethics", "Values", 8),
    ("Human dignity", "Society", "Rights", 8),
    ("Social justice", "Society", "Justice", 9),
    ("Distributive justice", "Society", "Justice", 8),
    ("Intergenerational equity", "Society", "Justice", 8),
    ("Vulnerable sections", "Society", "Welfare", 7),
    ("Welfare state", "Polity", "Welfare", 8),
    ("National interest", "IR", "Foreign Policy", 7),
    ("Strategic autonomy", "IR", "Foreign Policy", 9),
    ("Multi-alignment", "IR", "Foreign Policy", 8),
    ("Neighbourhood first", "IR", "Foreign Policy", 8),
    ("Act East Policy", "IR", "Foreign Policy", 7),
    ("Vision of New India", "Governance", "Vision", 7),
    ("Sabka Saath Sabka Vikas", "Governance", "Vision", 8),
    ("Vasudhaiva Kutumbakam", "Society", "Culture", 8),
]


@app.route('/word-bank')
def word_bank_home():
    subject_filter = request.args.get('subject', '').strip()
    q = TopperPhrase.query
    if subject_filter:
        q = q.filter(TopperPhrase.subject == subject_filter)
    phrases = q.order_by(TopperPhrase.power_level.desc()).limit(200).all()
    subjects = sorted(set(p.subject for p in TopperPhrase.query.all() if p.subject))
    copies = TopperCopy.query.order_by(TopperCopy.uploaded_at.desc()).limit(20).all()
    return render_template('word_bank_home.html',
                           phrases=phrases, subjects=subjects,
                           subject=subject_filter, copies=copies)


@app.route('/word-bank/seed', methods=['POST'])
def word_bank_seed():
    created = 0
    for phrase, subj, cat, level in HIGH_VALUE_PHRASES_SEED:
        existing = TopperPhrase.query.filter_by(phrase=phrase).first()
        if existing:
            continue
        db.session.add(TopperPhrase(
            phrase=phrase, subject=subj, category=cat,
            power_level=level, source='seed'
        ))
        created += 1
    db.session.commit()
    flash(f'Seeded {created} high-value phrases from topper patterns.')
    return redirect(url_for('word_bank_home'))


@app.route('/word-bank/extract', methods=['POST'])
def word_bank_extract():
    """Upload a topper answer PDF → AI extracts high-value phrases."""
    if 'file' not in request.files:
        flash('No file uploaded.'); return redirect(url_for('word_bank_home'))
    f = request.files['file']
    if not f or not f.filename.lower().endswith('.pdf'):
        flash('Please upload a PDF.'); return redirect(url_for('word_bank_home'))

    topper_name = request.form.get('topper_name', 'Unknown').strip()
    year = request.form.get('year', '').strip()
    rank = request.form.get('rank', '').strip()
    subject = request.form.get('subject', '').strip() or 'General'

    os.makedirs('uploads', exist_ok=True)
    fname = secure_filename(f"topcopy_{int(_lazy_time.time())}.pdf")
    path = os.path.join('uploads', fname)
    f.save(path)

    try:
        pages = extract_pages(path, use_ocr=True)
    except Exception as e:
        flash(f'PDF extract failed: {str(e)[:150]}'); return redirect(url_for('word_bank_home'))

    # Sample up to 30 pages for tokens
    text_sample = '\n'.join(p[1] for p in pages[:30])[:8000]

    # Save the copy
    try:
        yr = int(year) if year else None
    except ValueError:
        yr = None
    copy = TopperCopy(
        topper_name=topper_name, year=yr, rank=rank,
        subject=subject, raw_text=text_sample, filename=fname
    )
    db.session.add(copy); db.session.commit()

    # AI extracts power phrases
    system = (
        "You are analyzing a UPSC topper's handwritten answer copy (OCR text). "
        "Extract 15-25 HIGH-VALUE PHRASES that examiners reward — technical terms, "
        "constitutional phrases, governance vocabulary, ethics terminology, policy terms. "
        "Return strict JSON only:\n"
        '{"phrases":[{"phrase":"exact phrase from text","subject":"Polity|Economy|Governance|'
        'Ethics|Environment|IR|Society|History|Geography","category":"Constitutional|Federalism|'
        'Administration|Development|Climate|Integrity|Vision","power_level":8}]}\n'
        "Rules: Only 1-5 word phrases. Real terms, not sentences. Skip generic words."
    )
    user = f"SUBJECT: {subject}\n\nCOPY TEXT:\n{text_sample[:6000]}\n\nExtract high-value phrases."
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=1500)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        data = _lazy_json.loads(content)
    except Exception as e:
        flash(f'AI extraction failed: {str(e)[:150]}'); return redirect(url_for('word_bank_home'))

    added = 0
    for p in data.get('phrases', []):
        phrase = (p.get('phrase') or '').strip()
        if not phrase or len(phrase) > 60:
            continue
        existing = TopperPhrase.query.filter_by(phrase=phrase).first()
        if existing:
            existing.usage_count = (existing.usage_count or 1) + 1
            continue
        try:
            lvl = int(p.get('power_level', 7))
        except Exception:
            lvl = 7
        db.session.add(TopperPhrase(
            phrase=phrase,
            subject=(p.get('subject') or subject)[:50],
            category=(p.get('category') or '')[:50],
            power_level=max(1, min(10, lvl)),
            source='topper_extract'
        ))
        added += 1
    db.session.commit()
    flash(f'Extracted {added} high-value phrases from {topper_name}.')
    return redirect(url_for('word_bank_home'))


@app.route('/word-bank/phrase/<int:pid>/delete', methods=['POST'])
def word_bank_delete(pid):
    p = TopperPhrase.query.get_or_404(pid)
    db.session.delete(p); db.session.commit()
    return redirect(url_for('word_bank_home'))


def _get_phrases_for_subject(subject, max_n=10):
    """Retrieve top phrases for a subject to inject into AI answers."""
    q = TopperPhrase.query
    if subject:
        q = q.filter(TopperPhrase.subject == subject)
    rows = q.order_by(TopperPhrase.power_level.desc()).limit(max_n).all()
    if not rows:
        rows = TopperPhrase.query.order_by(TopperPhrase.power_level.desc()).limit(max_n).all()
    return [r.phrase for r in rows]


# ---------- Strategic Assist (clean) ----------
@app.route('/sa')
def sa_home():
    return render_template('assist_home.html')


@app.route('/sa/prelims-hint', methods=['POST'])
def sa_prelims_hint():
    question = request.form.get('question', '').strip()
    a = request.form.get('option_a', '').strip()
    b = request.form.get('option_b', '').strip()
    c = request.form.get('option_c', '').strip()
    d = request.form.get('option_d', '').strip()
    if not question:
        return {'error': 'Question missing'}, 400
    system = (
        "You are a UPSC Prelims elimination coach. Analyze each option in 30 seconds. "
        "Return strict JSON: "
        '{"analysis":[{"option":"A","verdict":"Safe|Suspect|Eliminate","reason":"1-line"},'
        '{"option":"B","verdict":"...","reason":"..."},'
        '{"option":"C","verdict":"...","reason":"..."},'
        '{"option":"D","verdict":"...","reason":"..."}],'
        '"final_tip":"30-word strategy hint"}'
    )
    user = f"QUESTION: {question}\n\nA) {a}\nB) {b}\nC) {c}\nD) {d}\n\nAnalyze."
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=700)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        return _lazy_json.loads(content)
    except Exception as e:
        return {'error': str(e)[:200]}, 500


@app.route('/sa/mains-hint', methods=['POST'])
def sa_mains_hint():
    question = request.form.get('question', '').strip()
    draft = request.form.get('draft', '').strip()
    if not question:
        return {'error': 'Question missing'}, 400
    system = (
        "You are a UPSC Mains answer-writing coach. Return strict JSON: "
        '{"stage":"Intro|Body|Conclusion",'
        '"next_line":"exact 25-40 word sentence to write next",'
        '"next_points":["angle 1","angle 2","angle 3"],'
        '"danger":"what to avoid next",'
        '"word_budget_left":"words left"}'
    )
    user = f"QUESTION: {question}\n\nDRAFT:\n{draft or '(empty)'}\n\nSuggest next move."
    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=900)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        return _lazy_json.loads(content)
    except Exception as e:
        return {'error': str(e)[:200]}, 500


# ---------- Topper Clone (Style DNA) ----------
class TopperDNA(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topper_name = db.Column(db.String(200))
    year = db.Column(db.Integer)
    rank = db.Column(db.String(30))
    optional = db.Column(db.String(100))
    paper = db.Column(db.String(100))
    tone = db.Column(db.String(50))
    signature_phrases = db.Column(db.Text)
    structure_pattern = db.Column(db.Text)
    transition_words = db.Column(db.Text)
    diagram_types = db.Column(db.Text)
    quotes_used = db.Column(db.Text)
    data_points = db.Column(db.Text)
    examples_used = db.Column(db.Text)
    intro_style = db.Column(db.Text)
    conclusion_style = db.Column(db.Text)
    word_count_avg = db.Column(db.Integer)
    sample_answer = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class CloneAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    selected_toppers = db.Column(db.Text)
    answer = db.Column(db.Text)
    similarity_score = db.Column(db.Float)
    word_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


@app.route('/topper-clone')
def topper_clone_home():
    dnas = TopperDNA.query.order_by(TopperDNA.created_at.desc()).all()
    answers = CloneAnswer.query.order_by(CloneAnswer.created_at.desc()).limit(20).all()
    return render_template('topper_clone_home.html', dnas=dnas, answers=answers)


@app.route('/topper-clone/upload', methods=['POST'])
def topper_clone_upload():
    """Upload a topper PDF → extract style DNA → delete PDF."""
    if 'file' not in request.files:
        flash('No file.'); return redirect(url_for('topper_clone_home'))
    f = request.files['file']
    if not f or not f.filename.lower().endswith('.pdf'):
        flash('PDF required.'); return redirect(url_for('topper_clone_home'))

    name = request.form.get('topper_name', 'Unknown').strip()
    year = request.form.get('year', '').strip()
    rank = request.form.get('rank', '').strip()
    optional = request.form.get('optional', '').strip()
    paper = request.form.get('paper', 'GS2').strip()

    os.makedirs('uploads', exist_ok=True)
    fname = secure_filename(f"topper_temp_{int(_lazy_time.time())}.pdf")
    path = os.path.join('uploads', fname)
    f.save(path)

    # Extract text
    try:
        pages = extract_pages(path, use_ocr=True)
    except Exception as e:
        try: os.remove(path)
        except: pass
        flash(f'PDF extract failed: {str(e)[:150]}')
        return redirect(url_for('topper_clone_home'))

    text = '\n'.join(p[1] for p in pages[:40])[:15000]

    if len(text.strip()) < 500:
        try: os.remove(path)
        except: pass
        flash('PDF has too little text. Try a clearer scan.')
        return redirect(url_for('topper_clone_home'))

    system = (
        "You are a forensic analyst of UPSC topper answer copies. Analyze the text and extract the "
        "topper's STYLE DNA — the exact patterns that make their answers score high. "
        "Return strict JSON only:\n"
        '{"tone":"formal|balanced|assertive|analytical",'
        '"signature_phrases":["exact 2-5 word phrase 1","phrase 2",...max 25 phrases],'
        '"structure_pattern":"describe how intro-body-conclusion flows (2-3 lines)",'
        '"transition_words":["Moreover","Furthermore","However",...max 15],'
        '"diagram_types":["flowchart","table","cycle",...max 5],'
        '"quotes_used":["exact quote — author",...max 5],'
        '"data_points":["exact stat or fact used",...max 8],'
        '"examples_used":["example 1","example 2",...max 6],'
        '"intro_style":"1-2 lines on how they open answers",'
        '"conclusion_style":"1-2 lines on how they close",'
        '"word_count_avg":150,'
        '"sample_answer":"the single strongest 150-250 word answer from the text, verbatim"}'
    )
    user = f"PAPER: {paper}\n\nCOPY TEXT:\n{text}\n\nExtract style DNA now."

    try:
        content, _ = _lazy_call_any_ai(system, user, max_tokens=2500)
        content = content.strip().strip('`').replace('```json','').replace('```','').strip()
        data = _lazy_json.loads(content)
    except Exception as e:
        try: os.remove(path)
        except: pass
        flash(f'AI extraction failed: {str(e)[:150]}')
        return redirect(url_for('topper_clone_home'))

    # Delete PDF — we only keep the DNA
    try: os.remove(path)
    except: pass

    try:
        yr = int(year) if year else None
    except ValueError:
        yr = None

    dna = TopperDNA(
        topper_name=name, year=yr, rank=rank, optional=optional, paper=paper,
        tone=(data.get('tone') or 'balanced')[:50],
        signature_phrases=_lazy_json.dumps(data.get('signature_phrases', [])[:25]),
        structure_pattern=(data.get('structure_pattern') or '')[:1000],
        transition_words=_lazy_json.dumps(data.get('transition_words', [])[:15]),
        diagram_types=_lazy_json.dumps(data.get('diagram_types', [])[:5]),
        quotes_used=_lazy_json.dumps(data.get('quotes_used', [])[:5]),
        data_points=_lazy_json.dumps(data.get('data_points', [])[:8]),
        examples_used=_lazy_json.dumps(data.get('examples_used', [])[:6]),
        intro_style=(data.get('intro_style') or '')[:500],
        conclusion_style=(data.get('conclusion_style') or '')[:500],
        word_count_avg=int(data.get('word_count_avg') or 150),
        sample_answer=(data.get('sample_answer') or '')[:2000]
    )
    db.session.add(dna); db.session.commit()
    flash(f'Style DNA extracted from {name}. PDF deleted — only 10 KB stored.')
    return redirect(url_for('topper_clone_home'))


@app.route('/topper-clone/generate', methods=['POST'])
def topper_clone_generate():
    """Generate an answer cloned from selected toppers' DNA."""
    question = request.form.get('question', '').strip()
    if len(question) < 10:
        return {'error': 'Enter a full question'}, 400

    ids = request.form.getlist('topper_ids')
    if not ids:
        return {'error': 'Select at least one topper'}, 400

    dnas = []
    for tid in ids[:5]:
        try:
            d = TopperDNA.query.get(int(tid))
            if d: dnas.append(d)
        except: continue
    if not dnas:
        return {'error': 'No valid toppers selected'}, 400

    # Build combined style signature
    phrases, transitions, quotes, data_pts, examples = [], [], [], [], []
    structures = []
    intros = []
    conclusions = []
    samples = []
    for d in dnas:
        try: phrases += _lazy_json.loads(d.signature_phrases or '[]')
        except: pass
        try: transitions += _lazy_json.loads(d.transition_words or '[]')
        except: pass
        try: quotes += _lazy_json.loads(d.quotes_used or '[]')
        except: pass
        try: data_pts += _lazy_json.loads(d.data_points or '[]')
        except: pass
        try: examples += _lazy_json.loads(d.examples_used or '[]')
        except: pass
        if d.structure_pattern: structures.append(d.structure_pattern)
        if d.intro_style: intros.append(d.intro_style)
        if d.conclusion_style: conclusions.append(d.conclusion_style)
        if d.sample_answer: samples.append(f"[{d.topper_name}]: {d.sample_answer}")

    system = (
        "You are a MIRROR — a Topper Clone. Your job is to write a UPSC Mains answer that "
        "SOUNDS LIKE IT WAS WRITTEN BY THE TOPPER(S) whose style DNA is provided. "
        "CRITICAL RULES:\n"
        "1) 70-80% of the answer must use the EXACT phrases, structure, and language from the toppers.\n"
        "2) Only 20-30% should be new sentences that fit the question.\n"
        "3) Use the toppers' intro style, transition words, conclusion style.\n"
        "4) Include 2-3 toppers' phrases per paragraph — do NOT paraphrase; use them verbatim.\n"
        "5) Use the exact quotes, data points, and examples the toppers used.\n"
        "6) Match their tone and structure.\n"
        "7) Format exactly like a topper: bullet points, headings, sub-points, arrows if used.\n"
        "8) NO AI-style filler words like 'delve', 'crucial', 'pivotal', 'moreover' (unless topper used).\n"
        "9) Target 250 words (15-mark) or 150 words (10-mark).\n"
        "Return plain text only — the answer itself. No JSON, no explanation."
    )
    user = (
        f"QUESTION:\n{question}\n\n"
        f"TOPPERS BEING CLONED: {', '.join([d.topper_name + ' (AIR ' + (d.rank or 'N/A') + ')' for d in dnas])}\n\n"
        f"SIGNATURE PHRASES TO REUSE (verbatim):\n{_lazy_json.dumps(list(set(phrases))[:40])}\n\n"
        f"TRANSITION WORDS THEY USE:\n{_lazy_json.dumps(list(set(transitions))[:20])}\n\n"
        f"STRUCTURE PATTERNS:\n{' | '.join(structures)[:1000]}\n\n"
        f"INTRO STYLES:\n{' | '.join(intros)[:600]}\n\n"
        f"CONCLUSION STYLES:\n{' | '.join(conclusions)[:600]}\n\n"
        f"QUOTES THEY USE:\n{_lazy_json.dumps(list(set(quotes))[:10])}\n\n"
        f"DATA POINTS THEY CITE:\n{_lazy_json.dumps(list(set(data_pts))[:12])}\n\n"
        f"EXAMPLES THEY USE:\n{_lazy_json.dumps(list(set(examples))[:8])}\n\n"
        f"SAMPLE ANSWERS TO MATCH STYLE:\n{chr(10).join(samples)[:3000]}\n\n"
        "Now write the answer in this cloned style. 70-80% their words, 20-30% new."
    )

    try:
        answer, _ = _lazy_call_any_ai(system, user, max_tokens=1800)
    except Exception as e:
        return {'error': str(e)[:200]}, 500

    # Rough similarity % — count how many signature phrases appear
    matched = sum(1 for p in set(phrases) if p.lower() in answer.lower())
    total = max(1, len(set(phrases)))
    similarity = round(100 * matched / total, 1)

    db.session.add(CloneAnswer(
        question=question[:1500],
        selected_toppers=_lazy_json.dumps([d.topper_name for d in dnas]),
        answer=answer[:8000],
        similarity_score=similarity,
        word_count=len(answer.split())
    ))
    db.session.commit()

    return {
        'answer': answer,
        'similarity': similarity,
        'word_count': len(answer.split()),
        'toppers_used': [d.topper_name for d in dnas]
    }


@app.route('/topper-clone/<int:did>/delete', methods=['POST'])
def topper_clone_delete(did):
    d = TopperDNA.query.get_or_404(did)
    db.session.delete(d); db.session.commit()
    flash('DNA deleted.')
    return redirect(url_for('topper_clone_home'))


# ---------- Topper Twin — Full Text Edition ----------
class TopperFullText(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topper_name = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer)
    rank = db.Column(db.String(30))
    optional = db.Column(db.String(100))
    paper = db.Column(db.String(50))             # GS1, GS2, GS3, GS4, Essay, Optional
    full_text = db.Column(db.Text)                # complete text of the copy
    word_count = db.Column(db.Integer)
    paragraph_count = db.Column(db.Integer)
    source = db.Column(db.String(50), default='pdf_upload')
    drive_url = db.Column(db.String(500))         # if backed up to Google Drive
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class TopperParagraph(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topper_id = db.Column(db.Integer, db.ForeignKey('topper_full_text.id'), nullable=False)
    para_index = db.Column(db.Integer)            # order in the copy
    arg_type = db.Column(db.String(30))           # intro, body, evidence, counter, conclusion
    subject = db.Column(db.String(80))            # tagged subject
    topic = db.Column(db.String(200))             # tagged topic
    text = db.Column(db.Text, nullable=False)
    word_count = db.Column(db.Integer)
    key_terms = db.Column(db.Text)                # JSON list of key terms for retrieval
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


def _chunk_into_paragraphs(text, target_words=90):
    """Split full text into meaningful paragraphs of ~target_words."""
    import re as _r
    # Normalize whitespace
    text = _r.sub(r'\r\n', '\n', text)
    text = _r.sub(r'\n{3,}', '\n\n', text)
    text = _r.sub(r'[ \t]+', ' ', text)
    blocks = [b.strip() for b in text.split('\n\n') if len(b.strip()) > 40]
    paragraphs = []
    for block in blocks:
        words = block.split()
        if len(words) <= target_words * 2:
            paragraphs.append(' '.join(words))
        else:
            # Split long blocks by sentence into ~90-word chunks
            sentences = _r.split(r'(?<=[.!?])\s+', block)
            current = []
            current_words = 0
            for s in sentences:
                sw = len(s.split())
                if current_words + sw > target_words and current:
                    paragraphs.append(' '.join(current))
                    current = [s]
                    current_words = sw
                else:
                    current.append(s)
                    current_words += sw
            if current:
                paragraphs.append(' '.join(current))
    # Filter very short fragments
    return [p for p in paragraphs if len(p.split()) >= 30]


def _classify_paragraph(text, index, total):
    """Heuristic type tag + AI-assisted (done later)."""
    tl = text.lower()
    if index == 0 or any(k in tl[:80] for k in ['introduction', 'context', 'background', 'refers to']):
        return 'intro'
    if index >= total - 2 or any(k in tl[-200:] for k in ['conclusion', 'way forward', 'thus', 'therefore', 'to sum up']):
        return 'conclusion'
    if any(k in tl for k in ['however', 'on the other hand', 'critics argue', 'counter', 'challenge']):
        return 'counter'
    if any(k in tl for k in ['for example', 'for instance', 'case of', 'such as', 'e.g.']):
        return 'evidence'
    return 'body'


@app.route('/twin')
def twin_home():
    toppers = TopperFullText.query.order_by(TopperFullText.created_at.desc()).all()
    # Aggregate stats
    from collections import Counter
    total_words = sum(t.word_count or 0 for t in toppers)
    total_paras = sum(t.paragraph_count or 0 for t in toppers)
    # Group by paper
    papers = Counter(t.paper for t in toppers if t.paper)
    return render_template('twin_home.html',
                           toppers=toppers,
                           total_words=total_words,
                           total_paras=total_paras,
                           papers=dict(papers))


@app.route('/twin/upload', methods=['POST'])
def twin_upload():
    """Upload topper PDF or paste text → store full corpus + paragraphs."""
    topper_name = request.form.get('topper_name', '').strip()
    if not topper_name:
        flash('Topper name required.')
        return redirect(url_for('twin_home'))

    year = request.form.get('year', '').strip()
    rank = request.form.get('rank', '').strip()
    optional = request.form.get('optional', '').strip()
    paper = request.form.get('paper', 'GS2').strip()
    pasted_text = request.form.get('pasted_text', '').strip()

    full_text = ''

    # Path A: pasted text
    if pasted_text and len(pasted_text) > 200:
        full_text = pasted_text
    # Path B: PDF upload
    elif 'file' in request.files:
        f = request.files['file']
        if f and f.filename.lower().endswith('.pdf'):
            os.makedirs('uploads', exist_ok=True)
            fname = secure_filename(f"twin_temp_{int(_lazy_time.time())}.pdf")
            path = os.path.join('uploads', fname)
            f.save(path)
            try:
                pages = extract_pages(path, use_ocr=True)
                full_text = '\n\n'.join(p[1] for p in pages)
            except Exception as e:
                try: os.remove(path)
                except: pass
                flash(f'PDF extract failed: {str(e)[:150]}')
                return redirect(url_for('twin_home'))
            finally:
                try: os.remove(path)
                except: pass

    if len(full_text.strip()) < 500:
        flash('Not enough text. Paste at least 500 characters or upload a clear PDF.')
        return redirect(url_for('twin_home'))

    # Chunk into paragraphs
    paragraphs = _chunk_into_paragraphs(full_text, target_words=90)
    if len(paragraphs) < 3:
        flash('Could not split into paragraphs. Text may be too short or unclear.')
        return redirect(url_for('twin_home'))

    try:
        yr = int(year) if year else None
    except ValueError:
        yr = None

    total_words = len(full_text.split())

    topper = TopperFullText(
        topper_name=topper_name,
        year=yr,
        rank=rank,
        optional=optional,
        paper=paper,
        full_text=full_text[:100000],   # cap at ~100K chars
        word_count=total_words,
        paragraph_count=len(paragraphs),
        source='pdf_upload' if not pasted_text else 'pasted'
    )
    db.session.add(topper); db.session.flush()

    for i, para in enumerate(paragraphs):
        arg_type = _classify_paragraph(para, i, len(paragraphs))
        db.session.add(TopperParagraph(
            topper_id=topper.id,
            para_index=i,
            arg_type=arg_type,
            text=para[:5000],
            word_count=len(para.split())
        ))
    db.session.commit()

    flash(f'{topper_name} added: {total_words} words, {len(paragraphs)} paragraphs. PDF deleted.')
    return redirect(url_for('twin_home'))


@app.route('/twin/<int:tid>/delete', methods=['POST'])
def twin_delete(tid):
    t = TopperFullText.query.get_or_404(tid)
    TopperParagraph.query.filter_by(topper_id=t.id).delete()
    db.session.delete(t)
    db.session.commit()
    flash('Topper deleted.')
    return redirect(url_for('twin_home'))


# ---------- Topper Twin — RAG Retrieval ----------
def _find_relevant_paragraphs(question, topper_ids, per_topper=4, total=20):
    """Return top-N paragraphs from selected toppers matching the question."""
    import re as _r
    from collections import Counter as _Cnt
    from sqlalchemy import or_ as _or

    if not topper_ids:
        return []

    # Extract keywords
    stop = {'the','a','an','of','in','on','and','or','to','for','with','is','are','was','were',
            'be','been','being','that','this','it','its','as','by','at','from','into','about',
            'which','who','what','when','where','why','how','has','have','had','will','would',
            'can','could','should','may','might','their','there','they','than','then',
            'also','such','said','says','according','new','recent','discuss','examine',
            'critically','comment','analyse','analyze','evaluate','elucidate'}
    words = [w.lower().strip('.,?!;:()[]"') for w in _r.findall(r'\w+', question)]
    words = [w for w in words if len(w) > 3 and w not in stop]
    if not words:
        return []
    top_words = [w for w, _ in _Cnt(words).most_common(12)]

    # SQL filter — match any keyword
    filters = []
    for w in top_words:
        filters.append(TopperParagraph.text.ilike(f'%{w}%'))
    try:
        candidates = TopperParagraph.query.filter(
            TopperParagraph.topper_id.in_(topper_ids),
            _or(*filters)
        ).limit(200).all()
    except Exception:
        return []

    # Score by keyword overlap
    scored = []
    for p in candidates:
        ptl = (p.text or '').lower()
        score = sum(1 for w in top_words if w in ptl)
        if score >= 2:
            scored.append((score, p))

    scored.sort(key=lambda x: -x[0])

    # Cap per topper so we blend fairly
    per_topper_count = _Cnt()
    final = []
    for score, p in scored:
        if per_topper_count[p.topper_id] >= per_topper:
            continue
        final.append(p)
        per_topper_count[p.topper_id] += 1
        if len(final) >= total:
            break
    return final


@app.route('/twin/generate', methods=['POST'])
def twin_generate():
    """Generate answer by blending paragraphs from selected toppers."""
    question = request.form.get('question', '').strip()
    if len(question) < 10:
        return {'error': 'Enter a full question'}, 400

    ids = request.form.getlist('topper_ids')
    if not ids:
        return {'error': 'Select at least one topper'}, 400

    topper_ids = []
    for tid in ids[:6]:
        try:
            topper_ids.append(int(tid))
        except ValueError:
            continue
    if not topper_ids:
        return {'error': 'Invalid topper selection'}, 400

    # Fetch selected toppers
    toppers = TopperFullText.query.filter(TopperFullText.id.in_(topper_ids)).all()
    if not toppers:
        return {'error': 'Toppers not found'}, 404

    # Retrieve relevant paragraphs
    paragraphs = _find_relevant_paragraphs(question, topper_ids, per_topper=5, total=25)

    if not paragraphs:
        return {'error': 'No matching content found in selected topper copies. Try different toppers or upload more copies.'}, 404

    # Build context — full paragraphs grouped by topper + type
    context_parts = []
    for p in paragraphs:
        t = TopperFullText.query.get(p.topper_id)
        context_parts.append(
            f"[{t.topper_name if t else 'Topper'} · {p.arg_type} · {p.word_count}w]\n{p.text}"
        )
    context = '\n\n---\n\n'.join(context_parts)

    system = (
        "You are a Topper Twin. Your job is to produce an answer that SOUNDS LIKE IT WAS WRITTEN BY "
        "the topper(s) whose paragraphs are provided. Use their words, arguments, phrases, quotes, "
        "examples VERBATIM wherever possible.\n\n"
        "STRICT RULES:\n"
        "1) 75-85% of the output must be direct verbatim text from the provided paragraphs.\n"
        "2) Only 15-25% should be new sentences to create smooth transitions and address the specific question.\n"
        "3) Structure: INTRO (from an intro paragraph) → 3-5 BODY arguments (from body/evidence paras) → "
        "COUNTER (if available) → CONCLUSION (from a conclusion para).\n"
        "4) Keep their exact phrasing, terms, examples. Do NOT paraphrase aggressively.\n"
        "5) Blend paragraphs from multiple toppers — do not use just one topper for the whole answer.\n"
        "6) Preserve their punctuation style, bullet style, and structural markers.\n"
        "7) No AI-filler words: do NOT use 'delve', 'crucial', 'pivotal', 'it is important to note' "
        "unless it appeared in the source paragraphs.\n"
        "8) Output ONLY the final answer. No preamble, no explanation.\n"
        "9) Target length: 250 words (15-mark) or 150 words (10-mark). Match the question's demand."
    )
    user = (
        f"QUESTION:\n{question}\n\n"
        f"TOPPER PARAGRAPHS TO BLEND (source material):\n{context}\n\n"
        "Now compose the answer using 75-85% verbatim from the source material above."
    )

    try:
        answer, _ = _lazy_call_any_ai(system, user, max_tokens=2000)
    except Exception as e:
        return {'error': str(e)[:200]}, 500

    # Compute verbatim similarity — how many 6-word shingles from source appear in output
    import re as _r
    def shingles(text, n=6):
        words = _r.findall(r'\w+', (text or '').lower())
        return set(' '.join(words[i:i+n]) for i in range(len(words) - n + 1))

    src_shingles = shingles(context, 6)
    ans_shingles = shingles(answer, 6)
    if src_shingles:
        overlap = len(src_shingles & ans_shingles) / max(1, len(ans_shingles))
        similarity = round(overlap * 100, 1)
    else:
        similarity = 0.0

    return {
        'answer': answer,
        'similarity': similarity,
        'word_count': len(answer.split()),
        'paragraphs_used': len(paragraphs),
        'toppers_used': [t.topper_name for t in toppers],
        'source_paras': [
            {
                'topper': (TopperFullText.query.get(p.topper_id).topper_name if TopperFullText.query.get(p.topper_id) else 'Topper'),
                'type': p.arg_type,
                'text': p.text[:300] + ('...' if len(p.text) > 300 else '')
            }
            for p in paragraphs[:8]
        ]
    }


@app.route('/twin/<int:tid>/view')
def twin_view(tid):
    """Show all paragraphs stored for a topper."""
    t = TopperFullText.query.get_or_404(tid)
    paragraphs = TopperParagraph.query.filter_by(topper_id=tid).order_by(TopperParagraph.para_index).all()
    return render_template('twin_view.html', topper=t, paragraphs=paragraphs)


@app.route('/twin/stats')
def twin_stats():
    """Show cumulative stats — total words, paragraphs, papers."""
    from collections import Counter
    toppers = TopperFullText.query.all()
    total_words = sum(t.word_count or 0 for t in toppers)
    total_paras = sum(t.paragraph_count or 0 for t in toppers)
    papers = Counter(t.paper for t in toppers if t.paper)
    years = Counter(t.year for t in toppers if t.year)
    opt = Counter(t.optional for t in toppers if t.optional)
    return render_template('twin_stats.html',
                           toppers=toppers,
                           total_words=total_words,
                           total_paras=total_paras,
                           papers=dict(papers),
                           years=dict(sorted(years.items())),
                           opt=dict(opt))


# ---------- Twin: Batch Upload & Drive Integration ----------
@app.route('/twin/batch', methods=['GET', 'POST'])
def twin_batch():
    """Paste multi-topper text — split by markers."""
    if request.method == 'GET':
        return render_template('twin_batch.html')

    raw = request.form.get('batch_text', '').strip()
    if len(raw) < 500:
        flash('Need at least 500 characters.')
        return redirect(url_for('twin_batch'))

    default_paper = request.form.get('default_paper', 'GS2')

    # Split by markers like "===TOPPER: Name | Year: 2022 | Rank: 5 ==="
    import re as _r
    blocks = []
    pattern = _r.compile(r'^===TOPPER:\s*(.+?)\s*===\s*$', _r.MULTILINE)
    matches = list(pattern.finditer(raw))

    if not matches:
        flash('No ===TOPPER: Name === markers found. Add them to split multiple copies.')
        return redirect(url_for('twin_batch'))

    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(raw)
        header = m.group(1)
        body = raw[start:end].strip()
        # Parse header "Name | Year: 2022 | Rank: 5"
        parts = [p.strip() for p in header.split('|')]
        name = parts[0]
        year = None
        rank = ''
        optional = ''
        for p in parts[1:]:
            if p.lower().startswith('year'):
                try: year = int(p.split(':')[1].strip())
                except: pass
            elif p.lower().startswith('rank'):
                rank = p.split(':')[1].strip()
            elif p.lower().startswith('optional'):
                optional = p.split(':')[1].strip()
        if body and len(body) > 200:
            blocks.append({'name': name, 'year': year, 'rank': rank, 'optional': optional, 'text': body})

    if not blocks:
        flash('No valid blocks found.')
        return redirect(url_for('twin_batch'))

    added = 0
    for b in blocks:
        paragraphs = _chunk_into_paragraphs(b['text'], target_words=90)
        if len(paragraphs) < 3:
            continue
        t = TopperFullText(
            topper_name=b['name'][:200],
            year=b['year'],
            rank=b['rank'],
            optional=b['optional'],
            paper=default_paper,
            full_text=b['text'][:100000],
            word_count=len(b['text'].split()),
            paragraph_count=len(paragraphs),
            source='batch_paste'
        )
        db.session.add(t); db.session.flush()
        for i, para in enumerate(paragraphs):
            db.session.add(TopperParagraph(
                topper_id=t.id, para_index=i,
                arg_type=_classify_paragraph(para, i, len(paragraphs)),
                text=para[:5000],
                word_count=len(para.split())
            ))
        added += 1
    db.session.commit()
    flash(f'Added {added} toppers in batch.')
    return redirect(url_for('twin_home'))


@app.route('/twin/<int:tid>/export')
def twin_export(tid):
    """Export topper as JSON for backup / Drive."""
    t = TopperFullText.query.get_or_404(tid)
    paragraphs = TopperParagraph.query.filter_by(topper_id=tid).order_by(TopperParagraph.para_index).all()
    data = {
        'topper_name': t.topper_name,
        'year': t.year,
        'rank': t.rank,
        'optional': t.optional,
        'paper': t.paper,
        'word_count': t.word_count,
        'paragraphs': [{'idx': p.para_index, 'type': p.arg_type, 'text': p.text} for p in paragraphs]
    }
    from flask import Response
    return Response(
        _lazy_json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment;filename=topper_{t.id}.json'}
    )


@app.route('/twin/import', methods=['POST'])
def twin_import():
    """Import topper from exported JSON."""
    if 'file' not in request.files:
        flash('No file.'); return redirect(url_for('twin_home'))
    f = request.files['file']
    if not f or not f.filename.endswith('.json'):
        flash('JSON required.'); return redirect(url_for('twin_home'))
    try:
        data = _lazy_json.loads(f.read().decode('utf-8'))
    except Exception as e:
        flash(f'Invalid JSON: {str(e)[:100]}'); return redirect(url_for('twin_home'))

    t = TopperFullText(
        topper_name=(data.get('topper_name') or 'Imported')[:200],
        year=data.get('year'),
        rank=data.get('rank') or '',
        optional=data.get('optional') or '',
        paper=data.get('paper') or 'GS2',
        full_text='(imported)',
        word_count=data.get('word_count') or 0,
        paragraph_count=len(data.get('paragraphs', [])),
        source='import'
    )
    db.session.add(t); db.session.flush()
    for p in data.get('paragraphs', []):
        db.session.add(TopperParagraph(
            topper_id=t.id,
            para_index=int(p.get('idx') or 0),
            arg_type=p.get('type') or 'body',
            text=(p.get('text') or '')[:5000],
            word_count=len((p.get('text') or '').split())
        ))
    db.session.commit()
    flash(f"Imported {t.topper_name}.")
    return redirect(url_for('twin_home'))


@app.route('/twin/<int:tid>/set-drive', methods=['POST'])
def twin_set_drive(tid):
    t = TopperFullText.query.get_or_404(tid)
    url = request.form.get('drive_url', '').strip()
    t.drive_url = url[:500]
    db.session.commit()
    flash('Drive URL saved.')
    return redirect(url_for('twin_view', tid=tid))


# ---------- Backblaze B2 Storage ----------
import os
B2_KEY_ID = os.environ.get('B2_KEY_ID', '3bc292d12855')
B2_APP_KEY = os.environ.get('B2_APP_KEY', '005fbc7629739a7606c8d0154bc6e7fbb06eb3894c')
B2_BUCKET = os.environ.get('B2_BUCKET', 'ias-machine-storage500')

_b2_api = None
_b2_bucket = None


def _b2_connect():
    """Lazy-connect to B2. Returns (bucket, api) or (None, None) on failure."""
    global _b2_api, _b2_bucket
    if _b2_bucket:
        return _b2_bucket, _b2_api
    try:
        from b2sdk.v2 import B2Api, InMemoryAccountInfo
        info = InMemoryAccountInfo()
        api = B2Api(info)
        api.authorize_account("production", B2_KEY_ID, B2_APP_KEY)
        bucket = api.get_bucket_by_name(B2_BUCKET)
        _b2_api = api
        _b2_bucket = bucket
        return bucket, api
    except Exception as e:
        print(f"B2 connect failed: {e}")
        return None, None


def b2_upload_bytes(data, remote_path, content_type='application/octet-stream'):
    """Upload bytes to B2. Returns file_id or None."""
    bucket, api = _b2_connect()
    if not bucket:
        return None
    try:
        file_info = bucket.upload_bytes(data, remote_path, content_type=content_type)
        return file_info.id_
    except Exception as e:
        print(f"B2 upload failed: {e}")
        return None


def b2_upload_file(local_path, remote_path):
    """Upload a local file to B2."""
    bucket, api = _b2_connect()
    if not bucket:
        return None
    try:
        with open(local_path, 'rb') as f:
            data = f.read()
        file_info = bucket.upload_bytes(data, remote_path)
        return file_info.id_
    except Exception as e:
        print(f"B2 upload file failed: {e}")
        return None


def b2_download_bytes(remote_path):
    """Download file bytes from B2. Returns bytes or None."""
    bucket, api = _b2_connect()
    if not bucket:
        return None
    try:
        downloaded = bucket.download_file_by_name(remote_path)
        import io
        buf = io.BytesIO()
        downloaded.save(buf)
        return buf.getvalue()
    except Exception as e:
        print(f"B2 download failed: {e}")
        return None


def b2_delete(remote_path):
    """Delete a file from B2."""
    bucket, api = _b2_connect()
    if not bucket:
        return False
    try:
        file_info = bucket.get_file_info_by_name(remote_path)
        bucket.delete_file_version(file_info.id_, remote_path)
        return True
    except Exception as e:
        print(f"B2 delete failed: {e}")
        return False


@app.route('/b2/status')
def b2_status():
    """Check B2 connection and list stored files."""
    bucket, api = _b2_connect()
    if not bucket:
        return {'connected': False, 'error': 'Cannot connect to B2'}
    try:
        files = []
        for f, _ in bucket.ls(recursive=True, latest_only=True):
            files.append({
                'name': f.file_name,
                'size': f.size,
                'uploaded': str(f.upload_timestamp)
            })
        return {
            'connected': True,
            'bucket': B2_BUCKET,
            'file_count': len(files),
            'files': files[:50]
        }
    except Exception as e:
        return {'connected': True, 'error': str(e)[:200]}


@app.route('/twin/<int:tid>/backup-to-b2', methods=['POST'])
def twin_backup_b2(tid):
    """Backup a topper's full JSON to B2."""
    t = TopperFullText.query.get_or_404(tid)
    paragraphs = TopperParagraph.query.filter_by(topper_id=tid).order_by(TopperParagraph.para_index).all()
    payload = {
        'topper_name': t.topper_name,
        'year': t.year,
        'rank': t.rank,
        'optional': t.optional,
        'paper': t.paper,
        'word_count': t.word_count,
        'paragraph_count': t.paragraph_count,
        'paragraphs': [{'idx': p.para_index, 'type': p.arg_type, 'text': p.text} for p in paragraphs]
    }
    data = _lazy_json.dumps(payload, ensure_ascii=False).encode('utf-8')
    remote = f"toppers/{t.id}_{secure_filename(t.topper_name)}.json"
    file_id = b2_upload_bytes(data, remote, content_type='application/json')
    if file_id:
        t.drive_url = f"b2://{B2_BUCKET}/{remote}"
        db.session.commit()
        flash(f'Backed up to B2: {remote}')
    else:
        flash('B2 backup failed. Check console.')
    return redirect(url_for('twin_view', tid=tid))


@app.route('/b2/backup-all', methods=['POST'])
def b2_backup_all():
    """Backup every topper in DB to B2."""
    toppers = TopperFullText.query.all()
    count = 0
    for t in toppers:
        paragraphs = TopperParagraph.query.filter_by(topper_id=t.id).order_by(TopperParagraph.para_index).all()
        payload = {
            'topper_name': t.topper_name,
            'year': t.year, 'rank': t.rank, 'optional': t.optional, 'paper': t.paper,
            'word_count': t.word_count, 'paragraph_count': t.paragraph_count,
            'paragraphs': [{'idx': p.para_index, 'type': p.arg_type, 'text': p.text} for p in paragraphs]
        }
        data = _lazy_json.dumps(payload, ensure_ascii=False).encode('utf-8')
        remote = f"toppers/{t.id}_{secure_filename(t.topper_name)}.json"
        if b2_upload_bytes(data, remote, content_type='application/json'):
            count += 1
    flash(f'Backed up {count} toppers to B2.')
    return redirect(url_for('twin_home'))


@app.route('/b2/restore/<int:tid>', methods=['POST'])
def b2_restore(tid):
    """Restore a topper from B2 backup."""
    # Find by listing bucket
    bucket, api = _b2_connect()
    if not bucket:
        flash('Cannot connect to B2.'); return redirect(url_for('twin_home'))
    target_prefix = f"toppers/{tid}_"
    found = None
    for f, _ in bucket.ls(recursive=True, latest_only=True):
        if f.file_name.startswith(target_prefix):
            found = f.file_name
            break
    if not found:
        flash(f'No backup found for topper #{tid}.')
        return redirect(url_for('twin_home'))
    data = b2_download_bytes(found)
    if not data:
        flash('Download failed.'); return redirect(url_for('twin_home'))
    try:
        payload = _lazy_json.loads(data.decode('utf-8'))
    except Exception as e:
        flash(f'Invalid backup: {str(e)[:100]}'); return redirect(url_for('twin_home'))
    # Delete existing then re-create
    old = TopperFullText.query.get(tid)
    if old:
        TopperParagraph.query.filter_by(topper_id=tid).delete()
        db.session.delete(old); db.session.commit()
    t = TopperFullText(
        topper_name=(payload.get('topper_name') or 'Restored')[:200],
        year=payload.get('year'), rank=payload.get('rank') or '',
        optional=payload.get('optional') or '', paper=payload.get('paper') or 'GS2',
        full_text='(restored from B2)',
        word_count=payload.get('word_count') or 0,
        paragraph_count=payload.get('paragraph_count') or 0,
        source='b2_restore'
    )
    db.session.add(t); db.session.flush()
    for p in payload.get('paragraphs', []):
        db.session.add(TopperParagraph(
            topper_id=t.id, para_index=int(p.get('idx') or 0),
            arg_type=p.get('type') or 'body',
            text=(p.get('text') or '')[:5000],
            word_count=len((p.get('text') or '').split())
        ))
    db.session.commit()
    flash(f'Restored {t.topper_name} from B2.')
    return redirect(url_for('twin_view', tid=t.id))


# ---------- Google Drive Integration ----------
import json as _djson
from pathlib import Path

DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '')
DRIVE_KEY_PATH = os.path.join(os.path.dirname(__file__), 'config', 'gdrive_key.json')

_drive_service = None


def _drive_connect():
    """Connect to Google Drive via service account. Returns service or None."""
    global _drive_service
    if _drive_service:
        return _drive_service
    if not os.path.exists(DRIVE_KEY_PATH):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_KEY_PATH,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        _drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return _drive_service
    except Exception as e:
        print(f"Drive connect failed: {e}")
        return None


def drive_upload_bytes(data, filename, folder_id=None, mime='application/json'):
    """Upload bytes to Drive folder. Returns file_id or None."""
    service = _drive_connect()
    if not service:
        return None
    folder = folder_id or DRIVE_FOLDER_ID
    if not folder:
        return None
    try:
        from googleapiclient.http import MediaInMemoryUpload
        file_metadata = {'name': filename, 'parents': [folder]}
        media = MediaInMemoryUpload(data, mimetype=mime, resumable=False)
        created = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, size',
            supportsAllDrives=True
        ).execute()
        return created.get('id')
    except Exception as e:
        print(f"Drive upload failed: {e}")
        return None


def drive_list_files():
    """List files in the folder."""
    service = _drive_connect()
    if not service or not DRIVE_FOLDER_ID:
        return []
    try:
        result = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            fields='files(id, name, size, createdTime)',
            pageSize=100,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        return result.get('files', [])
    except Exception as e:
        print(f"Drive list failed: {e}")
        return []


def drive_delete_file(file_id):
    service = _drive_connect()
    if not service:
        return False
    try:
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        return True
    except Exception:
        return False


def drive_download_bytes(file_id):
    service = _drive_connect()
    if not service:
        return None
    try:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception as e:
        print(f"Drive download failed: {e}")
        return None


@app.route('/drive/status')
def drive_status():
    """Check Drive connection."""
    service = _drive_connect()
    if not service:
        return {'connected': False, 'error': 'Cannot connect. Check key file + share folder with service account.'}
    if not DRIVE_FOLDER_ID:
        return {'connected': True, 'error': 'DRIVE_FOLDER_ID not set.'}
    files = drive_list_files()
    return {
        'connected': True,
        'folder_id': DRIVE_FOLDER_ID,
        'file_count': len(files),
        'files': files[:20]
    }


@app.route('/twin/<int:tid>/backup-drive', methods=['POST'])
def twin_backup_drive(tid):
    """Backup topper JSON to Drive."""
    t = TopperFullText.query.get_or_404(tid)
    paragraphs = TopperParagraph.query.filter_by(topper_id=tid).order_by(TopperParagraph.para_index).all()
    payload = {
        'topper_name': t.topper_name, 'year': t.year, 'rank': t.rank,
        'optional': t.optional, 'paper': t.paper,
        'word_count': t.word_count, 'paragraph_count': t.paragraph_count,
        'paragraphs': [{'idx': p.para_index, 'type': p.arg_type, 'text': p.text} for p in paragraphs]
    }
    data = _lazy_json.dumps(payload, ensure_ascii=False).encode('utf-8')
    filename = f"topper_{t.id}_{secure_filename(t.topper_name)}.json"
    file_id = drive_upload_bytes(data, filename)
    if file_id:
        t.drive_url = f"gdrive://{file_id}"
        db.session.commit()
        flash(f'Backed up to Drive: {filename}')
    else:
        flash('Drive upload failed. Check service account + folder sharing.')
    return redirect(url_for('twin_view', tid=tid))


@app.route('/drive/backup-all-twin', methods=['POST'])
def drive_backup_all_twin():
    toppers = TopperFullText.query.all()
    count = 0
    for t in toppers:
        paragraphs = TopperParagraph.query.filter_by(topper_id=t.id).order_by(TopperParagraph.para_index).all()
        payload = {
            'topper_name': t.topper_name, 'year': t.year, 'rank': t.rank,
            'optional': t.optional, 'paper': t.paper,
            'word_count': t.word_count, 'paragraph_count': t.paragraph_count,
            'paragraphs': [{'idx': p.para_index, 'type': p.arg_type, 'text': p.text} for p in paragraphs]
        }
        data = _lazy_json.dumps(payload, ensure_ascii=False).encode('utf-8')
        fn = f"topper_{t.id}_{secure_filename(t.topper_name)}.json"
        if drive_upload_bytes(data, fn):
            count += 1
    flash(f'Backed up {count} toppers to Drive.')
    return redirect(url_for('twin_home'))


@app.route('/drive/upload-file', methods=['POST'])
def drive_upload_file_route():
    """Upload any file (PDF, image) to Drive."""
    if 'file' not in request.files:
        flash('No file.'); return redirect(url_for('drive_status'))
    f = request.files['file']
    if not f or not f.filename:
        flash('Empty file.'); return redirect(url_for('drive_status'))
    data = f.read()
    mime = f.content_type or 'application/octet-stream'
    file_id = drive_upload_bytes(data, secure_filename(f.filename), mime=mime)
    if file_id:
        flash(f'Uploaded {f.filename} to Drive.')
    else:
        flash('Upload failed.')
    return redirect(url_for('drive_status'))


# ---------- Quick Upload (One-Step) ----------
def _is_text_layer_pdf(filepath, sample_pages=3):
    """Check if PDF has real text (not scanned images)."""
    try:
        import pypdfium2 as _pdf
        pdf = _pdf.PdfDocument(filepath)
        text_found = 0
        for i in range(min(sample_pages, len(pdf))):
            try:
                tp = pdf[i].get_textpage()
                txt = tp.get_text_range().strip()
                if len(txt) > 100:
                    text_found += 1
            except Exception:
                pass
        pdf.close()
        return text_found >= 2
    except Exception:
        return False


@app.route('/library/quick-upload', methods=['POST'])
def library_quick_upload():
    """One-step upload: compress → B2 → auto-extract → library."""
    if 'file' not in request.files:
        return {'error': 'No file'}, 400
    f = request.files['file']
    if not f or not f.filename.lower().endswith('.pdf'):
        return {'error': 'PDF required'}, 400

    # Check file size (PythonAnywhere cap ~100 MB)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > 60 * 1024 * 1024:
        return {'error': f'File is {round(size/1024/1024, 1)} MB. PythonAnywhere allows max 60 MB. Please compress the PDF on your phone using a free app (PDF Compressor / iLovePDF) first — this reduces 177 MB to ~40-60 MB.'}, 400

    title = request.form.get('title', '').strip() or f.filename.replace('.pdf', '')
    subject = request.form.get('subject', '').strip() or 'General'
    category = request.form.get('category', 'book')

    # Save temporarily
    os.makedirs('uploads', exist_ok=True)
    fname = secure_filename(f"quick_{int(_lazy_time.time())}.pdf")
    filepath = os.path.join('uploads', fname)
    f.save(filepath)

    size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)

    # Detect text-layer
    is_text = _is_text_layer_pdf(filepath)

    # Upload to B2 (permanent copy)
    b2_url = None
    try:
        with open(filepath, 'rb') as fh:
            data = fh.read()
        remote = f"books/{secure_filename(title)}.pdf"
        file_id = b2_upload_bytes(data, remote, content_type='application/pdf')
        if file_id:
            b2_url = f"b2://{B2_BUCKET}/{remote}"
    except Exception as e:
        print(f"B2 upload failed: {e}")

    # Extract text if text-layer
    pages_data = []
    if is_text:
        try:
            import pypdfium2 as _pdf
            pdf = _pdf.PdfDocument(filepath)
            total = len(pdf)
            cap = min(total, 400)  # cap to avoid CPU limit
            for i in range(cap):
                try:
                    tp = pdf[i].get_textpage()
                    txt = tp.get_text_range().strip()
                except Exception:
                    txt = ''
                if txt:
                    pages_data.append((i + 1, txt, False))
            pdf.close()
        except Exception as e:
            print(f"Extract failed: {e}")

    # Create book record
    book = Book(
        title=title[:300],
        author=request.form.get('author', '').strip(),
        subject=subject[:100],
        topic='',
        category=category,
        filename=b2_url or fname
    )
    db.session.add(book)
    db.session.flush()

    for pnum, text, ocr in pages_data:
        db.session.add(Page(book_id=book.id, page_number=pnum, text=text, ocr_used=ocr))
    db.session.commit()

    # Delete local file if B2 stored
    if b2_url:
        try: os.remove(filepath)
        except: pass

    status = 'text_extracted' if pages_data else 'pdf_only'
    return {
        'ok': True,
        'book_id': book.id,
        'title': title,
        'pages': len(pages_data),
        'size_mb': size_mb,
        'b2_url': b2_url,
        'status': status
    }


@app.route('/library/quick-upload-page')
def library_quick_upload_page():
    return render_template('quick_upload.html')


# ---------- Chunked Upload (Big Files) ----------
import shutil as _shutil

CHUNK_DIR = 'chunk_uploads'
os.makedirs(CHUNK_DIR, exist_ok=True)


@app.route('/library/chunk-upload', methods=['POST'])
def library_chunk_upload():
    """Receive one chunk of a large file."""
    upload_id = request.form.get('upload_id', '').strip()
    chunk_index = int(request.form.get('chunk_index', 0))
    total_chunks = int(request.form.get('total_chunks', 1))
    filename = secure_filename(request.form.get('filename', 'upload.pdf'))
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    subject = request.form.get('subject', '').strip() or 'General'
    category = request.form.get('category', 'book')

    if not upload_id or 'chunk' not in request.files:
        return {'error': 'Missing chunk or upload_id'}, 400

    # Save chunk
    chunk = request.files['chunk']
    upload_dir = os.path.join(CHUNK_DIR, upload_id)
    os.makedirs(upload_dir, exist_ok=True)
    chunk_path = os.path.join(upload_dir, f"part_{chunk_index:04d}.bin")
    chunk.save(chunk_path)

    # Check if all chunks received
    received = sorted([
        int(f.replace('part_', '').replace('.bin', ''))
        for f in os.listdir(upload_dir)
        if f.startswith('part_') and f.endswith('.bin')
    ])

    if len(received) < total_chunks:
        return {'ok': True, 'status': 'received', 'chunks_received': len(received), 'total': total_chunks}

    # All chunks here — reassemble
    final_name = f"assembled_{upload_id}.pdf"
    final_path = os.path.join('uploads', final_name)
    os.makedirs('uploads', exist_ok=True)

    try:
        with open(final_path, 'wb') as out:
            for i in range(total_chunks):
                cp = os.path.join(upload_dir, f"part_{i:04d}.bin")
                if not os.path.exists(cp):
                    return {'error': f'Missing chunk {i}'}, 500
                with open(cp, 'rb') as cf:
                    while True:
                        buf = cf.read(4 * 1024 * 1024)
                        if not buf:
                            break
                        out.write(buf)
    except Exception as e:
        return {'error': f'Reassembly failed: {str(e)[:150]}'}, 500

    # Cleanup chunks
    try: _shutil.rmtree(upload_dir)
    except: pass

    size_mb = round(os.path.getsize(final_path) / (1024 * 1024), 2)

    # Detect text-layer
    is_text = _is_text_layer_pdf(final_path)

    # Upload to B2
    b2_url = None
    try:
        with open(final_path, 'rb') as fh:
            data = fh.read()
        remote = f"books/{secure_filename(title or filename)}.pdf"
        file_id = b2_upload_bytes(data, remote, content_type='application/pdf')
        if file_id:
            b2_url = f"b2://{B2_BUCKET}/{remote}"
    except Exception as e:
        print(f"B2 upload failed: {e}")

    # Extract text if text-layer
    pages_data = []
    if is_text:
        try:
            import pypdfium2 as _pdf
            pdf = _pdf.PdfDocument(final_path)
            total = len(pdf)
            cap = min(total, 500)
            for i in range(cap):
                try:
                    tp = pdf[i].get_textpage()
                    txt = tp.get_text_range().strip()
                except Exception:
                    txt = ''
                if txt:
                    pages_data.append((i + 1, txt, False))
            pdf.close()
        except Exception as e:
            print(f"Extract failed: {e}")

    book = Book(
        title=(title or filename)[:300],
        author=author[:200],
        subject=subject[:100],
        topic='',
        category=category,
        filename=b2_url or final_name
    )
    db.session.add(book)
    db.session.flush()

    for pnum, text, ocr in pages_data:
        db.session.add(Page(book_id=book.id, page_number=pnum, text=text, ocr_used=ocr))
    db.session.commit()

    # Delete local file after successful processing
    try: os.remove(final_path)
    except: pass

    status = 'text_extracted' if pages_data else 'pdf_only'
    return {
        'ok': True,
        'status': 'complete',
        'book_id': book.id,
        'title': book.title,
        'pages': len(pages_data),
        'size_mb': size_mb,
        'extract_status': status
    }


@app.route('/library/chunk-cleanup', methods=['POST'])
def library_chunk_cleanup():
    """Cleanup abandoned chunk uploads older than 1 hour."""
    import time as _t
    now = _t.time()
    cleaned = 0
    try:
        for entry in os.listdir(CHUNK_DIR):
            path = os.path.join(CHUNK_DIR, entry)
            if os.path.isdir(path):
                age = now - os.path.getmtime(path)
                if age > 3600:
                    _shutil.rmtree(path, ignore_errors=True)
                    cleaned += 1
    except Exception:
        pass
    return {'cleaned': cleaned}


# ---------- iCopy Notebook Embed ----------
@app.route('/icopy')
def icopy_notebook():
    return render_template('icopy.html')


# ---------- Prelims Answer Key System ----------
class AnswerKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam = db.Column(db.String(50))          # UPSC_PRELIMS, UPPSC, SSC_CGL, etc
    year = db.Column(db.Integer)
    paper = db.Column(db.String(50))         # GS1, CSAT, GS_Paper_II, etc
    q_number = db.Column(db.Integer)
    correct_option = db.Column(db.String(2)) # A/B/C/D
    explanation = db.Column(db.Text)
    source = db.Column(db.String(30))        # official, ai_parsed, manual
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class AnswerKeySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    exam = db.Column(db.String(50))
    year = db.Column(db.Integer)
    paper = db.Column(db.String(50))
    total_questions = db.Column(db.Integer)
    uploaded_by = db.Column(db.String(50), default='admin')
    source = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


EXAM_PATTERNS_FOR_KEY = {
    'UPSC_PRELIMS_GS1': {'exam':'UPSC_PRELIMS', 'paper':'GS1', 'total':100},
    'UPSC_PRELIMS_CSAT': {'exam':'UPSC_PRELIMS', 'paper':'CSAT', 'total':80},
    'UPPSC_PRELIMS': {'exam':'UPPSC', 'paper':'GS1', 'total':150},
    'BPSC_PRELIMS': {'exam':'BPSC', 'paper':'GS1', 'total':150},
    'MPPSC_PRELIMS': {'exam':'MPPSC', 'paper':'GS1', 'total':100},
    'SSC_CGL': {'exam':'SSC_CGL', 'paper':'GS', 'total':100},
    'SSC_CHSL': {'exam':'SSC_CHSL', 'paper':'GS', 'total':100},
    'RRB_NTPC': {'exam':'RRB_NTPC', 'paper':'GS', 'total':100},
    'UP_POLICE': {'exam':'UP_POLICE', 'paper':'GS', 'total':150},
    'CUSTOM': {'exam':'CUSTOM', 'paper':'GS', 'total':100},
}


def _ai_parse_answer_key(text, exam_pattern='UPSC_PRELIMS_GS1'):
    """Send raw pasted key text to AI → structured Q→Answer dict."""
    preset = EXAM_PATTERNS_FOR_KEY.get(exam_pattern, EXAM_PATTERNS_FOR_KEY['CUSTOM'])
    system = (
        "You are parsing an UPSC / SSC / State PSC exam answer key. Extract every question number "
        "and its correct option. Return strict JSON: "
        '{"answers":[{"q":1,"answer":"B","explanation":"optional"},'
        '{"q":2,"answer":"C"},...]}\n'
        "Rules: answer must be A/B/C/D only. If explanations are given, include them. "
        "Handle formats like: 'Q1. (b)', '1-b', '1. B', 'Q-1 (B)', '1) B', '1:B' etc. "
        "If a question has multiple parts, split accordingly. Skip blanks."
    )
    user = f"EXAM: {preset['exam']} {preset['paper']}\nTotal questions expected: {preset['total']}\n\nRAW TEXT:\n{text[:8000]}\n\nParse now."
    content, _ = _lazy_call_any_ai(system, user, max_tokens=2500)
    content = content.strip().strip('`').replace('```json','').replace('```','').strip()
    return _lazy_json.loads(content)


@app.route('/answer-key')
def answer_key_home():
    sessions = AnswerKeySession.query.order_by(AnswerKeySession.created_at.desc()).limit(30).all()
    keys = AnswerKey.query.order_by(AnswerKey.created_at.desc()).limit(200).all()
    # Group for summary
    summary = {}
    for k in keys:
        key = f"{k.exam} · {k.year} · {k.paper}"
        summary.setdefault(key, 0)
        summary[key] += 1
    return render_template('answer_key_home.html',
                           sessions=sessions,
                           patterns=EXAM_PATTERNS_FOR_KEY,
                           summary=summary)


@app.route('/answer-key/parse', methods=['POST'])
def answer_key_parse():
    """Parse pasted text → preview before saving."""
    raw_text = request.form.get('raw_text', '').strip()
    exam_pattern = request.form.get('exam_pattern', 'UPSC_PRELIMS_GS1')
    if len(raw_text) < 20:
        return {'error': 'Paste at least a few answers'}, 400

    try:
        parsed = _ai_parse_answer_key(raw_text, exam_pattern)
        return {
            'ok': True,
            'pattern': exam_pattern,
            'count': len(parsed.get('answers', [])),
            'preview': parsed.get('answers', [])[:15],
            'all': parsed.get('answers', [])
        }
    except Exception as e:
        return {'error': f'AI parsing failed: {str(e)[:200]}'}, 500


@app.route('/answer-key/save', methods=['POST'])
def answer_key_save():
    """Save parsed answers to DB."""
    exam_pattern = request.form.get('exam_pattern', 'UPSC_PRELIMS_GS1')
    year_str = request.form.get('year', '').strip()
    answers_json = request.form.get('answers_json', '').strip()
    custom_name = request.form.get('name', '').strip()

    if not answers_json:
        flash('No answers to save.')
        return redirect(url_for('answer_key_home'))

    try:
        answers = _lazy_json.loads(answers_json)
    except Exception as e:
        flash(f'Invalid data: {str(e)[:100]}')
        return redirect(url_for('answer_key_home'))

    preset = EXAM_PATTERNS_FOR_KEY.get(exam_pattern, EXAM_PATTERNS_FOR_KEY['CUSTOM'])
    try:
        year = int(year_str) if year_str else None
    except ValueError:
        year = None

    session = AnswerKeySession(
        name=custom_name or f"{preset['exam']} {year or ''} {preset['paper']}".strip(),
        exam=preset['exam'],
        year=year,
        paper=preset['paper'],
        total_questions=len(answers),
        source='ai_parsed'
    )
    db.session.add(session)
    db.session.flush()

    saved = 0
    updated = 0
    for a in answers:
        try:
            qn = int(a.get('q', 0))
            opt = (a.get('answer') or '').upper()[:1]
            if qn < 1 or opt not in ['A','B','C','D']:
                continue
            existing = AnswerKey.query.filter_by(
                exam=preset['exam'], year=year, paper=preset['paper'], q_number=qn
            ).first()
            if existing:
                existing.correct_option = opt
                existing.explanation = a.get('explanation','')
                updated += 1
            else:
                db.session.add(AnswerKey(
                    exam=preset['exam'], year=year, paper=preset['paper'],
                    q_number=qn, correct_option=opt,
                    explanation=a.get('explanation','')[:1000],
                    source='ai_parsed'
                ))
                saved += 1
        except Exception:
            continue
    db.session.commit()
    flash(f'Saved {saved} new answers, updated {updated} existing.')
    return redirect(url_for('answer_key_home'))


@app.route('/answer-key/session/<int:sid>/delete', methods=['POST'])
def answer_key_session_delete(sid):
    s = AnswerKeySession.query.get_or_404(sid)
    # Delete all keys for this exam+year+paper
    AnswerKey.query.filter_by(exam=s.exam, year=s.year, paper=s.paper).delete()
    db.session.delete(s)
    db.session.commit()
    flash('Answer key deleted.')
    return redirect(url_for('answer_key_home'))


@app.route('/answer-key/manual-add', methods=['POST'])
def answer_key_manual_add():
    """Add a single answer manually."""
    try:
        exam = request.form.get('exam')
        year = int(request.form.get('year'))
        paper = request.form.get('paper')
        qn = int(request.form.get('q_number'))
        opt = (request.form.get('correct_option') or '').upper()[:1]
    except (ValueError, TypeError):
        flash('Invalid input.'); return redirect(url_for('answer_key_home'))
    if opt not in ['A','B','C','D']:
        flash('Option must be A/B/C/D.'); return redirect(url_for('answer_key_home'))
    existing = AnswerKey.query.filter_by(exam=exam, year=year, paper=paper, q_number=qn).first()
    if existing:
        existing.correct_option = opt
    else:
        db.session.add(AnswerKey(exam=exam, year=year, paper=paper, q_number=qn,
                                 correct_option=opt, source='manual'))
    db.session.commit()
    flash(f'Saved Q{qn} = {opt}')
    return redirect(url_for('answer_key_home'))


def _lookup_answer(exam, year, paper, q_number):
    """Lookup the correct option for a PYQ."""
    return AnswerKey.query.filter_by(
        exam=exam, year=year, paper=paper, q_number=q_number
    ).first()


@app.route('/pyq-score', methods=['GET', 'POST'])
def pyq_score():
    """Student takes a PYQ and gets auto-scored."""
    result = None
    if request.method == 'POST':
        exam = request.form.get('exam')
        year = request.form.get('year')
        paper = request.form.get('paper')
        try:
            year = int(year)
        except ValueError:
            year = None
        # Get all answer keys for this paper
        keys = AnswerKey.query.filter_by(exam=exam, year=year, paper=paper).all()
        correct = wrong = blank = 0
        details = []
        for k in keys:
            ua = (request.form.get(f'q_{k.q_number}') or '').upper()[:1]
            status = 'blank'
            if ua:
                if ua == k.correct_option:
                    correct += 1
                    status = 'correct'
                else:
                    wrong += 1
                    status = 'wrong'
            else:
                blank += 1
            details.append({
                'q': k.q_number,
                'user': ua or '—',
                'correct_ans': k.correct_option,
                'status': status
            })
        # Scoring: +2 correct, -0.66 wrong
        score = correct * 2 - wrong * 0.66
        result = {
            'exam': exam, 'year': year, 'paper': paper,
            'correct': correct, 'wrong': wrong, 'blank': blank,
            'total': len(keys), 'score': round(score, 2),
            'max_marks': len(keys) * 2,
            'details': details
        }
    # Build list of available papers
    papers = db.session.query(
        AnswerKey.exam, AnswerKey.year, AnswerKey.paper
    ).distinct().all()
    available = [{'exam': p[0], 'year': p[1], 'paper': p[2]} for p in papers if p[1]]
    return render_template('pyq_score.html', result=result, available=available)


# ---------- Universal Paste Box ----------
class QuickPaste(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    detected_type = db.Column(db.String(30))       # answer_key, question, note, book_text, unknown
    subject = db.Column(db.String(100))
    topic = db.Column(db.String(200))
    saved_to_table = db.Column(db.String(50))      # AnswerKey, Question, Note, etc
    saved_record_id = db.Column(db.Integer)
    source = db.Column(db.String(30), default='google_lens')  # google_lens, manual_paste, ocr
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class StudyNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(100))
    topic = db.Column(db.String(200))
    tags = db.Column(db.Text)
    source = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


def _ai_detect_paste_type(text):
    """AI classifies pasted text: answer key / question / book text / note."""
    system = (
        "Classify the pasted text. Return strict JSON only:\n"
        '{"type":"answer_key|question|book_text|note",'
        '"subject":"Polity|Economy|History|Geography|Science|Environment|GK|Current Affairs|Reasoning|Maths|English|Hindi|General",'
        '"topic":"short topic (3-5 words)",'
        '"confidence":0-100}\n\n'
        "Rules:\n"
        "- answer_key: single letters A/B/C/D mapped to question numbers, OR 'Q1. (b) Q2. (c)' pattern\n"
        "- question: starts with 'Q' or contains 'Consider the following statements' or 'Which of the following'\n"
        "- book_text: multi-paragraph factual content, textbook style\n"
        "- note: short fact or bullet or user-written reminder"
    )
    user = f"TEXT:\n{text[:2000]}\n\nClassify now."
    content, _ = _lazy_call_any_ai(system, user, max_tokens=300)
    content = content.strip().strip('`').replace('```json','').replace('```','').strip()
    return _lazy_json.loads(content)


@app.route('/paste')
def paste_home():
    recent = QuickPaste.query.order_by(QuickPaste.created_at.desc()).limit(30).all()
    return render_template('paste_home.html', recent=recent)


@app.route('/paste/process', methods=['POST'])
def paste_process():
    """Take pasted text → AI classifies → save to correct table."""
    text = request.form.get('content', '').strip()
    if len(text) < 10:
        return {'error': 'Paste at least 10 characters'}, 400

    # Detect type
    try:
        detection = _ai_detect_paste_type(text)
    except Exception as e:
        detection = {'type': 'note', 'subject': 'General', 'topic': '', 'confidence': 0}
        print(f"Detection failed: {e}")

    det_type = detection.get('type', 'note')
    subject = detection.get('subject', 'General')
    topic = detection.get('topic', '')

    saved_to = 'None'
    saved_id = None
    message = ''

    # Route based on type
    if det_type == 'answer_key':
        try:
            parsed = _ai_parse_answer_key(text, 'CUSTOM')
            answers = parsed.get('answers', [])
            year = _dt.now().year  # default — user can edit
            # Save as generic answer key for year
            count = 0
            for a in answers:
                try:
                    qn = int(a.get('q', 0))
                    opt = (a.get('answer') or '').upper()[:1]
                    if qn < 1 or opt not in ['A','B','C','D']:
                        continue
                    existing = AnswerKey.query.filter_by(
                        exam='PASTED', year=year, paper=subject, q_number=qn
                    ).first()
                    if existing:
                        existing.correct_option = opt
                    else:
                        db.session.add(AnswerKey(
                            exam='PASTED', year=year, paper=subject,
                            q_number=qn, correct_option=opt, source='paste'
                        ))
                        count += 1
                except Exception:
                    continue
            db.session.commit()
            saved_to = 'AnswerKey'
            message = f'Saved {count} answer key entries'
        except Exception as e:
            saved_to = 'Error'
            message = f'Parse failed: {str(e)[:100]}'

    elif det_type == 'question':
        # Save as a Question under "Pasted" paper
        paper = Book.query.filter_by(title='Pasted Questions', category='paper').first()
        if not paper:
            paper = Book(title='Pasted Questions', author='', subject=subject,
                         topic='', category='paper', filename='pasted')
            db.session.add(paper); db.session.flush()
        q = Question(
            paper_id=paper.id,
            question_number='',
            text=text[:5000],
            topic=topic[:200],
            year=_dt.now().year,
            marks=None,
            qtype='GS'
        )
        db.session.add(q); db.session.commit()
        saved_to = 'Question'
        saved_id = q.id
        message = 'Saved as Question'

    elif det_type == 'book_text':
        # Save as StudyNote (book excerpt)
        note = StudyNote(
            content=text[:20000],
            subject=subject,
            topic=topic[:200],
            source='book_text_paste'
        )
        db.session.add(note); db.session.commit()
        saved_to = 'StudyNote'
        saved_id = note.id
        message = 'Saved as Book Excerpt'

    else:
        # Note
        note = StudyNote(
            content=text[:20000],
            subject=subject,
            topic=topic[:200],
            source='paste'
        )
        db.session.add(note); db.session.commit()
        saved_to = 'StudyNote'
        saved_id = note.id
        message = 'Saved as Note'

    # Log
    log = QuickPaste(
        content=text[:10000],
        detected_type=det_type,
        subject=subject[:100],
        topic=topic[:200],
        saved_to_table=saved_to,
        saved_record_id=saved_id,
        source=request.form.get('source', 'manual_paste')
    )
    db.session.add(log); db.session.commit()

    return {
        'ok': True,
        'detected_type': det_type,
        'subject': subject,
        'topic': topic,
        'confidence': detection.get('confidence', 0),
        'saved_to': saved_to,
        'saved_id': saved_id,
        'message': message
    }


@app.route('/paste/<int:pid>/delete', methods=['POST'])
def paste_delete(pid):
    p = QuickPaste.query.get_or_404(pid)
    db.session.delete(p); db.session.commit()
    return redirect(url_for('paste_home'))


@app.route('/notes')
def notes_home():
    """Browse all study notes collected from pastes, book uploads, etc."""
    subject = request.args.get('subject', '').strip()
    q = StudyNote.query
    if subject:
        q = q.filter(StudyNote.subject == subject)
    notes = q.order_by(StudyNote.created_at.desc()).limit(200).all()
    subjects = [s[0] for s in db.session.query(StudyNote.subject).distinct().all() if s[0]]
    return render_template('notes_home.html', notes=notes, subjects=subjects, active=subject)


@app.route('/notes/<int:nid>/delete', methods=['POST'])
def note_delete(nid):
    n = StudyNote.query.get_or_404(nid)
    db.session.delete(n); db.session.commit()
    return redirect(url_for('notes_home'))


# ---------- Sync OCR (Mobile Upload → Laptop OCR) ----------
# Note: ocr_status column added to Book via ALTER in next step
# Values: 'pending' | 'processing' | 'complete' | 'pdf_only' | None (old books)

def _ensure_ocr_status_column():
    """Add ocr_status column if missing."""
    from sqlalchemy import text
    try:
        db.session.execute(text("ALTER TABLE book ADD COLUMN ocr_status VARCHAR(30) DEFAULT NULL"))
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


@app.route('/b2/pending-books')
def b2_pending_books():
    """List books that need OCR (for laptop sync script)."""
    try:
        rows = db.session.execute(
            __import__('sqlalchemy').text(
                "SELECT id, title, filename, category FROM book "
                "WHERE ocr_status = 'pending' OR ocr_status IS NULL"
            )
        ).fetchall()
    except Exception:
        rows = []
    return {
        'count': len(rows),
        'books': [
            {'id': r[0], 'title': r[1], 'filename': r[2], 'category': r[3]}
            for r in rows if r[2] and str(r[2]).startswith('b2://')
        ]
    }


@app.route('/b2/fetch-pdf/<int:book_id>')
def b2_fetch_pdf(book_id):
    """Laptop downloads PDF from B2 via this route."""
    from flask import Response
    book = Book.query.get_or_404(book_id)
    if not book.filename or not book.filename.startswith('b2://'):
        return {'error': 'Book is not stored on B2'}, 400
    # Parse b2://bucket/path
    parts = book.filename.replace('b2://', '').split('/', 1)
    if len(parts) != 2:
        return {'error': 'Invalid B2 filename'}, 400
    _, remote_path = parts
    data = b2_download_bytes(remote_path)
    if not data:
        return {'error': 'B2 download failed'}, 500
    return Response(data, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment;filename=book_{book_id}.pdf'})


@app.route('/b2/mark-ocr-complete/<int:book_id>', methods=['POST'])
def b2_mark_ocr_complete(book_id):
    """Laptop calls this after OCR — marks book complete + accepts page text."""
    from sqlalchemy import text
    book = Book.query.get_or_404(book_id)
    try:
        db.session.execute(
            text("UPDATE book SET ocr_status = 'complete' WHERE id = :bid"),
            {'bid': book_id}
        )
        db.session.commit()
        return {'ok': True, 'book_id': book_id}
    except Exception as e:
        db.session.rollback()
        return {'error': str(e)[:200]}, 500


@app.route('/b2/upload-text/<int:book_id>', methods=['POST'])
def b2_upload_text(book_id):
    """Laptop uploads OCR'd page text for a book."""
    book = Book.query.get_or_404(book_id)
    payload = request.get_json(silent=True) or {}
    pages = payload.get('pages', [])
    if not pages:
        return {'error': 'No pages provided'}, 400

    # Wipe existing pages for this book
    Page.query.filter_by(book_id=book_id).delete()
    db.session.commit()

    # Bulk insert
    batch = []
    for p in pages:
        try:
            pnum = int(p.get('page_number'))
            ptext = (p.get('text') or '').strip()
            if not ptext:
                continue
            batch.append(Page(book_id=book_id, page_number=pnum, text=ptext, ocr_used=True))
            if len(batch) >= 50:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []
        except Exception:
            continue
    if batch:
        db.session.bulk_save_objects(batch)
        db.session.commit()

    # Mark complete
    from sqlalchemy import text
    try:
        db.session.execute(text("UPDATE book SET ocr_status = 'complete' WHERE id = :bid"), {'bid': book_id})
        db.session.commit()
    except Exception:
        pass

    return {'ok': True, 'book_id': book_id, 'pages_inserted': len(pages)}


# ---------- OCR Queue Dashboard ----------
@app.route('/ocr-queue')
def ocr_queue():
    """Shows all books grouped by OCR status."""
    from sqlalchemy import text

    # Pull all books with their OCR status
    try:
        rows = db.session.execute(text("""
            SELECT id, title, author, subject, category, filename, ocr_status,
                   (SELECT COUNT(*) FROM page WHERE book_id = book.id) as page_count
            FROM book
            ORDER BY uploaded_at DESC
        """)).fetchall()
    except Exception as e:
        rows = []

    pending = []
    complete = []
    pdf_only = []
    no_status = []

    for r in rows:
        item = {
            'id': r[0], 'title': r[1], 'author': r[2], 'subject': r[3],
            'category': r[4], 'filename': r[5], 'ocr_status': r[6],
            'page_count': r[7], 'is_b2': r[5] and str(r[5]).startswith('b2://')
        }
        if item['ocr_status'] == 'complete' or (item['page_count'] and item['page_count'] > 5):
            complete.append(item)
        elif item['ocr_status'] == 'pending':
            pending.append(item)
        elif item['ocr_status'] == 'pdf_only':
            pdf_only.append(item)
        elif item['is_b2']:
            pending.append(item)  # B2 books without status = pending
        else:
            no_status.append(item)

    return render_template('ocr_queue.html',
                           pending=pending,
                           complete=complete,
                           pdf_only=pdf_only,
                           no_status=no_status,
                           total=len(rows))


@app.route('/ocr-queue/mark-pending/<int:book_id>', methods=['POST'])
def ocr_queue_mark_pending(book_id):
    """Mark a book as pending OCR."""
    from sqlalchemy import text
    db.session.execute(text("UPDATE book SET ocr_status = 'pending' WHERE id = :bid"), {'bid': book_id})
    db.session.commit()
    flash('Marked as pending. Run sync_ocr.py on laptop.')
    return redirect(url_for('ocr_queue'))


@app.route('/ocr-queue/mark-pdf-only/<int:book_id>', methods=['POST'])
def ocr_queue_mark_pdf_only(book_id):
    """Mark a book as pdf-only (skip OCR)."""
    from sqlalchemy import text
    db.session.execute(text("UPDATE book SET ocr_status = 'pdf_only' WHERE id = :bid"), {'bid': book_id})
    db.session.commit()
    flash('Marked as PDF-only. Will be skipped by OCR queue.')
    return redirect(url_for('ocr_queue'))


@app.route('/ocr-queue/list-json')
def ocr_queue_list_json():
    """JSON list for laptop script — all pending books ready to OCR."""
    from sqlalchemy import text
    try:
        rows = db.session.execute(text("""
            SELECT id, title, filename FROM book
            WHERE (ocr_status = 'pending' OR ocr_status IS NULL)
            AND filename LIKE 'b2://%'
            ORDER BY uploaded_at ASC
        """)).fetchall()
    except Exception:
        rows = []
    return {
        'count': len(rows),
        'pending': [{'id': r[0], 'title': r[1], 'filename': r[2]} for r in rows]
    }


# ---------- Storage Dashboard ----------
@app.route('/storage-dashboard')
def storage_dashboard():
    from sqlalchemy import text as _stext
    import os as _os

    # ----- Supabase stats -----
    db_stats = {'tables': [], 'total_rows': 0, 'estimated_mb': 0}
    try:
        tables = db.session.execute(_stext(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )).fetchall()
        for t in tables:
            tname = t[0]
            try:
                cnt = db.session.execute(_stext(f'SELECT COUNT(*) FROM "{tname}"')).scalar()
                db_stats['total_rows'] += cnt or 0
                db_stats['tables'].append({'name': tname, 'rows': cnt or 0})
            except Exception:
                continue
        db_stats['tables'].sort(key=lambda x: -x['rows'])
        # Get actual DB size via Postgres
        try:
            size_bytes = db.session.execute(_stext(
                "SELECT pg_database_size(current_database())"
            )).scalar() or 0
            db_stats['estimated_mb'] = round(size_bytes / (1024 * 1024), 2)
        except Exception:
            db_stats['estimated_mb'] = round(db_stats['total_rows'] * 0.001, 2)
    except Exception as e:
        db_stats['error'] = str(e)[:200]

    # ----- Supabase limit -----
    supabase_limit_mb = 500
    supabase_percent = round(100 * db_stats['estimated_mb'] / supabase_limit_mb, 2) if supabase_limit_mb else 0

    # ----- B2 stats -----
    b2_stats = {'connected': False, 'file_count': 0, 'total_mb': 0}
    try:
        bucket, api = _b2_connect()
        if bucket:
            b2_stats['connected'] = True
            total_bytes = 0
            count = 0
            for f, _ in bucket.ls(recursive=True, latest_only=True):
                total_bytes += f.size or 0
                count += 1
                if count >= 5000:
                    break
            b2_stats['file_count'] = count
            b2_stats['total_mb'] = round(total_bytes / (1024 * 1024), 2)
    except Exception as e:
        b2_stats['error'] = str(e)[:150]

    b2_limit_gb = 10
    b2_used_gb = round(b2_stats['total_mb'] / 1024, 3)
    b2_percent = round(100 * b2_used_gb / b2_limit_gb, 2) if b2_limit_gb else 0

    # ----- Drive stats -----
    drive_stats = {'connected': False, 'file_count': 0}
    try:
        service = _drive_connect()
        if service:
            drive_stats['connected'] = True
            files = drive_list_files()
            drive_stats['file_count'] = len(files)
    except Exception as e:
        drive_stats['error'] = str(e)[:150]

    # ----- PythonAnywhere local disk -----
    pa_stats = {'files': 0, 'size_mb': 0}
    try:
        root = _os.path.dirname(_os.path.abspath(__file__))
        total = 0
        count = 0
        for dirpath, dirnames, filenames in _os.walk(root):
            # Skip venv + chunk_uploads for cleaner numbers
            if 'venv' in dirpath or '__pycache__' in dirpath or 'chunk_uploads' in dirpath:
                continue
            for fn in filenames:
                try:
                    fp = _os.path.join(dirpath, fn)
                    total += _os.path.getsize(fp)
                    count += 1
                    if count >= 10000:
                        break
                except Exception:
                    pass
            if count >= 10000:
                break
        pa_stats['files'] = count
        pa_stats['size_mb'] = round(total / (1024 * 1024), 2)
    except Exception as e:
        pa_stats['error'] = str(e)[:150]

    pa_limit_mb = 512
    pa_percent = round(100 * pa_stats['size_mb'] / pa_limit_mb, 2) if pa_limit_mb else 0

    # ----- Table-by-table top usage -----
    top_tables = db_stats.get('tables', [])[:15]

    # ----- Total -----
    total_free_gb = round((supabase_limit_mb / 1024) + b2_limit_gb + 15 + (pa_limit_mb / 1024), 2)
    total_used_gb = round((db_stats['estimated_mb'] / 1024) + b2_used_gb + (pa_stats['size_mb'] / 1024), 3)
    total_percent = round(100 * total_used_gb / total_free_gb, 2) if total_free_gb else 0

    return render_template('storage_dashboard.html',
                           db=db_stats, db_limit=supabase_limit_mb, db_pct=supabase_percent,
                           b2=b2_stats, b2_limit=b2_limit_gb, b2_pct=b2_percent,
                           drive=drive_stats,
                           pa=pa_stats, pa_limit=pa_limit_mb, pa_pct=pa_percent,
                           top_tables=top_tables,
                           total_free=total_free_gb, total_used=total_used_gb,
                           total_pct=total_percent)


# ---------- Library Collections ----------
LIBRARY_COLLECTIONS = {
    'NCERT':          {'icon': '📗', 'label': 'NCERT'},
    'STANDARD':       {'icon': '📘', 'label': 'Standard Books'},
    'PYQ':            {'icon': '📕', 'label': 'Past Papers'},
    'TOPPER':         {'icon': '🏆', 'label': 'Topper Copies'},
    'MAGAZINE':       {'icon': '📰', 'label': 'Magazines'},
    'COACHING':       {'icon': '📋', 'label': 'Coaching Notes'},
    'NOTES':          {'icon': '📝', 'label': 'Notes'},
    'ANSWER_KEY':     {'icon': '🔑', 'label': 'Answer Keys'},
    'OPTIONAL':       {'icon': '📚', 'label': 'Optional Subject'},
    'CURRENT_AFFAIRS':{'icon': '📄', 'label': 'Current Affairs'},
    'OTHER':          {'icon': '📎', 'label': 'Other'},
}


@app.route('/library/auto-classify', methods=['POST'])
def library_auto_classify():
    """AI reads all book titles, assigns collection + year to each."""
    from sqlalchemy import text as _at
    books = Book.query.all()
    if not books:
        flash('No books to classify.')
        return redirect(url_for('library_home'))

    # Send titles in batch to AI (max 100 at a time)
    to_classify = []
    for b in books:
        to_classify.append({'id': b.id, 'title': b.title, 'author': b.author or '', 'subject': b.subject or ''})

    classified_count = 0
    batch_size = 80
    for i in range(0, len(to_classify), batch_size):
        batch = to_classify[i:i+batch_size]
        system = (
            "Classify each UPSC library book into a collection and detect year. Return strict JSON: "
            '{"items":[{"id":1,"collection":"NCERT|STANDARD|PYQ|TOPPER|MAGAZINE|COACHING|NOTES|ANSWER_KEY|OPTIONAL|CURRENT_AFFAIRS|OTHER","year":2023,"subject":"Polity","sub_subject":"Class 11"}]}\n'
            "Rules:\n"
            "- NCERT: contains 'NCERT', 'Class 6-12', or standard NCERT titles\n"
            "- STANDARD: Laxmikanth, Spectrum, Majid Husain, Ramesh Singh, Bipin Chandra etc\n"
            "- PYQ: contains 'UPSC', 'Prelims', 'Mains', '20XX', 'Paper'\n"
            "- TOPPER: 'Topper', 'Answer Copy', 'AIR', topper names\n"
            "- MAGAZINE: Yojana, Kurukshetra, EPW, monthly\n"
            "- COACHING: Drishti, Vision, Insights, Vajiram, Rau's\n"
            "- ANSWER_KEY: 'Answer Key', 'Solutions'\n"
            "- OPTIONAL: PSIR, Sociology, History, Geography (optional papers)\n"
            "- CURRENT_AFFAIRS: 'Current Affairs', 'CA', monthly compilations\n"
            "- year: extract from title if present, else null\n"
            "- subject: Polity / History / Geography / Economy / Environment / Science / Optional / GK / General"
        )
        user = "CLASSIFY:\n" + "\n".join([f'{b["id"]}: {b["title"][:120]}' for b in batch])
        try:
            content, _ = _lazy_call_any_ai(system, user, max_tokens=2500)
            content = content.strip().strip('`').replace('```json','').replace('```','').strip()
            data = _lazy_json.loads(content)
            for item in data.get('items', []):
                bid = item.get('id')
                col = (item.get('collection') or 'OTHER').upper()
                if col not in LIBRARY_COLLECTIONS:
                    col = 'OTHER'
                try:
                    year_val = int(item.get('year')) if item.get('year') else None
                except Exception:
                    year_val = None
                subj = (item.get('subject') or '')[:80]
                subsub = (item.get('sub_subject') or '')[:80]

                b = Book.query.get(bid)
                if b:
                    b.collection = col
                    if year_val:
                        b.year = year_val
                    if subj and not b.subject:
                        b.subject = subj
                    b.sub_subject = subsub
                    classified_count += 1
            db.session.commit()
            _lazy_time.sleep(1.5)
        except Exception as e:
            print(f"Batch classify failed: {str(e)[:150]}")
            continue

    flash(f'AI classified {classified_count} books into collections.')
    return redirect(url_for('library_home'))


@app.route('/library/move', methods=['POST'])
def library_move():
    """Manually assign collection to book(s)."""
    book_id = request.form.get('book_id')
    new_collection = request.form.get('collection', '').upper()
    new_year = request.form.get('year', '').strip()
    if new_collection not in LIBRARY_COLLECTIONS:
        flash('Invalid collection.')
        return redirect(url_for('library_home'))
    b = Book.query.get(int(book_id)) if book_id else None
    if not b:
        flash('Book not found.')
        return redirect(url_for('library_home'))
    b.collection = new_collection
    if new_year:
        try:
            b.year = int(new_year)
        except ValueError:
            pass
    db.session.commit()
    flash(f'Moved "{b.title[:40]}" to {new_collection}.')
    return redirect(request.referrer or url_for('library_home'))


@app.route('/library/bulk-move', methods=['POST'])
def library_bulk_move():
    """Bulk assign collection to multiple books."""
    ids = request.form.getlist('book_ids')
    new_collection = request.form.get('bulk_collection', '').upper()
    new_year = request.form.get('bulk_year', '').strip()
    if new_collection not in LIBRARY_COLLECTIONS or not ids:
        flash('Select books + valid collection.')
        return redirect(url_for('library_home'))
    count = 0
    for bid in ids:
        try:
            b = Book.query.get(int(bid))
            if b:
                b.collection = new_collection
                if new_year:
                    try:
                        b.year = int(new_year)
                    except ValueError:
                        pass
                count += 1
        except Exception:
            continue
    db.session.commit()
    flash(f'Moved {count} books to {new_collection}.')
    return redirect(url_for('library_home'))


# ---------- Offline Manager ----------
@app.route('/offline')
def offline_home():
    return render_template('offline.html')


# ---------- External Tools Hub (Local) ----------
EXTERNAL_TOOLS = [
    {
        'id': 'countries',
        'title': 'World Countries Explorer',
        'icon': '🌍',
        'url': '/static/tools/countries.html',
        'desc': 'Explore 250+ countries — leaders, districts, GDP, officials, and more.',
        'tags': ['World', 'Officials', 'Districts']
    },
    {
        'id': 'ias_hub',
        'title': 'IAS PDF Hub',
        'icon': '📚',
        'url': '/static/tools/ias_hub.html',
        'desc': 'Curated UPSC PDF sources — NCERTs, past papers, topper notes, magazines. One-click access.',
        'tags': ['PDFs', 'Resources', 'Free']
    },
]

@app.route('/tools')
def tools_home():
    tools = []
    for t in EXTERNAL_TOOLS:
        tools.append({
            'id': t['id'],
            'title': t['title'],
            'icon': t['icon'],
            'full_url': t['url'],
            'desc': t['desc'],
            'tags': t['tags']
        })
    return render_template('tools.html', tools=tools)


@app.route('/tools/embed/<tool_id>')
def tools_embed(tool_id):
    """Embed a tool in iframe inside app."""
    tool = next((t for t in EXTERNAL_TOOLS if t['id'] == tool_id), None)
    if not tool:
        flash('Tool not found.')
        return redirect(url_for('tools_home'))
    return render_template('tool_embed.html',
                           tool=tool,
                           full_url=tool['url'])


# ---------- B2-First Routing Overrides ----------
# These override/replace existing routes so files live in B2, not local disk.

def _is_b2_path(fname):
    return bool(fname) and str(fname).startswith('b2://')


def _b2_remote_from_url(b2_url):
    """Convert b2://bucket/path → remote path."""
    if not _is_b2_path(b2_url):
        return None
    parts = str(b2_url).replace('b2://', '').split('/', 1)
    return parts[1] if len(parts) == 2 else None


@app.route('/download/<int:book_id>')
def download_book(book_id):
    """Download — serves from B2 if b2://, else local."""
    from flask import Response, send_from_directory
    book = Book.query.get_or_404(book_id)
    if _is_b2_path(book.filename):
        remote = _b2_remote_from_url(book.filename)
        data = b2_download_bytes(remote)
        if not data:
            flash('B2 download failed.')
            return redirect(url_for('book_detail', book_id=book_id))
        return Response(
            data,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment;filename={secure_filename(book.title)}.pdf'}
        )
    return send_from_directory(app.config['UPLOAD_FOLDER'], book.filename, as_attachment=True)


@app.route('/read/<int:book_id>')
def read_book(book_id):
    """Inline PDF view — serves from B2 if b2://, else local."""
    from flask import Response, send_from_directory
    book = Book.query.get_or_404(book_id)
    if _is_b2_path(book.filename):
        remote = _b2_remote_from_url(book.filename)
        data = b2_download_bytes(remote)
        if not data:
            flash('B2 fetch failed. Re-upload book.')
            return redirect(url_for('book_detail', book_id=book_id))
        return Response(data, mimetype='application/pdf')
    return send_from_directory(app.config['UPLOAD_FOLDER'], book.filename, mimetype='application/pdf')


@app.route('/book/<int:book_id>/run-ocr', methods=['POST'])
def book_run_ocr(book_id):
    """OCR — pulls from B2 if needed, processes, deletes temp."""
    book = Book.query.get_or_404(book_id)
    tmp_path = None
    try:
        if _is_b2_path(book.filename):
            remote = _b2_remote_from_url(book.filename)
            data = b2_download_bytes(remote)
            if not data:
                flash('B2 fetch failed.')
                return redirect(url_for('book_detail', book_id=book_id))
            os.makedirs('uploads', exist_ok=True)
            tmp_path = os.path.join('uploads', f'ocr_tmp_{book_id}_{int(_lazy_time.time())}.pdf')
            with open(tmp_path, 'wb') as f:
                f.write(data)
            filepath = tmp_path
        else:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], book.filename)
            if not os.path.exists(filepath):
                flash('File missing on server.')
                return redirect(url_for('book_detail', book_id=book_id))

        Page.query.filter_by(book_id=book.id).delete()
        db.session.commit()

        pages = extract_pages(filepath, use_ocr=True)
        for pnum, text, ocr_used in pages:
            db.session.add(Page(book_id=book.id, page_number=pnum, text=text, ocr_used=ocr_used))
        db.session.commit()
        ocr_count = sum(1 for _, _, o in pages if o)
        flash(f'OCR complete — {len(pages)} pages processed ({ocr_count} via OCR).')
    except Exception as e:
        db.session.rollback()
        flash(f'OCR failed: {str(e)[:200]}')
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass
    return redirect(url_for('book_detail', book_id=book_id))


# ---------- Migration Tool ----------
@app.route('/library/migrate-to-b2', methods=['POST'])
def library_migrate_to_b2():
    """Move all local-only PDFs to B2 + update DB. Safe: skips b2:// already."""
    if not _b2_connect()[0]:
        flash('B2 not connected.')
        return redirect(url_for('library_home'))

    books = Book.query.all()
    migrated = 0
    freed_mb = 0.0
    skipped = 0
    errors = 0

    for b in books:
        if _is_b2_path(b.filename):
            skipped += 1
            continue
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], b.filename)
        if not os.path.exists(local_path):
            skipped += 1
            continue
        try:
            with open(local_path, 'rb') as f:
                data = f.read()
            remote = f"books/{secure_filename(b.title or b.filename)}.pdf"
            file_id = b2_upload_bytes(data, remote, content_type='application/pdf')
            if not file_id:
                errors += 1
                continue
            size_mb = len(data) / (1024 * 1024)
            freed_mb += size_mb
            b.filename = f"b2://{B2_BUCKET}/{remote}"
            db.session.commit()
            try:
                os.remove(local_path)
            except: pass
            migrated += 1
            _lazy_time.sleep(0.3)
        except Exception as e:
            print(f"Migrate fail {b.id}: {str(e)[:100]}")
            errors += 1
            continue

    flash(f'Migrated {migrated} books to B2 (freed {round(freed_mb, 1)} MB). Skipped {skipped}. Errors {errors}.')
    return redirect(url_for('library_home'))


@app.route('/library/disk-status')
def library_disk_status():
    """Show USER home directory usage on PythonAnywhere (not whole server)."""
    import os as _os
    home = _os.path.expanduser('~')
    quota_mb = 512  # PythonAnywhere free tier quota

    # Calculate actual user home usage by walking
    total_bytes = 0
    uploads_bytes = 0
    uploads_abs = _os.path.abspath(app.config['UPLOAD_FOLDER'])

    for dirpath, dirnames, filenames in _os.walk(home):
        # Skip __pycache__ for speed (small anyway)
        for fn in filenames:
            try:
                fp = _os.path.join(dirpath, fn)
                if _os.path.isfile(fp):
                    size = _os.path.getsize(fp)
                    total_bytes += size
                    if dirpath.startswith(uploads_abs):
                        uploads_bytes += size
            except Exception:
                pass

    used_mb = round(total_bytes / (1024 * 1024), 1)
    free_mb = round(max(0, quota_mb - used_mb), 1)
    percent = round(100 * used_mb / quota_mb, 1) if quota_mb else 0
    uploads_mb = round(uploads_bytes / (1024 * 1024), 1)

    return {
        'home_quota_mb': quota_mb,
        'home_used_mb': used_mb,
        'home_free_mb': free_mb,
        'home_percent': percent,
        'uploads_folder_mb': uploads_mb,
        'home_path': home,
    }


# ---------- Book Storage Status ----------
@app.route('/library/storage-status')
def library_storage_status():
    """Show every book + where its file lives (B2 vs local) + size."""
    import os as _os
    books = Book.query.order_by(Book.id.desc()).all()
    on_b2 = []
    local = []
    missing = []
    local_size_total = 0
    b2_count = 0

    for b in books:
        item = {
            'id': b.id,
            'title': b.title,
            'author': b.author,
            'subject': b.subject,
            'collection': b.collection,
            'filename': b.filename,
        }
        if _is_b2_path(b.filename):
            item['remote'] = _b2_remote_from_url(b.filename)
            on_b2.append(item)
            b2_count += 1
        else:
            lp = _os.path.join(app.config['UPLOAD_FOLDER'], b.filename or '')
            if _os.path.exists(lp):
                size = _os.path.getsize(lp)
                item['size_mb'] = round(size / (1024*1024), 2)
                local_size_total += size
                local.append(item)
            else:
                missing.append(item)

    return render_template('storage_status.html',
                           on_b2=on_b2,
                           local=local,
                           missing=missing,
                           b2_count=b2_count,
                           local_count=len(local),
                           missing_count=len(missing),
                           local_size_mb=round(local_size_total / (1024*1024), 2))


@app.route('/library/migrate-one/<int:book_id>', methods=['POST'])
def library_migrate_one(book_id):
    """Migrate a single book to B2."""
    b = Book.query.get_or_404(book_id)
    if _is_b2_path(b.filename):
        flash('Already on B2.')
        return redirect(url_for('library_storage_status'))
    lp = os.path.join(app.config['UPLOAD_FOLDER'], b.filename or '')
    if not os.path.exists(lp):
        flash('Local file missing.')
        return redirect(url_for('library_storage_status'))
    try:
        with open(lp, 'rb') as f:
            data = f.read()
        remote = f"books/{secure_filename(b.title or b.filename)}.pdf"
        file_id = b2_upload_bytes(data, remote, content_type='application/pdf')
        if not file_id:
            flash('B2 upload failed.')
            return redirect(url_for('library_storage_status'))
        b.filename = f"b2://{B2_BUCKET}/{remote}"
        db.session.commit()
        try: os.remove(lp)
        except: pass
        flash(f'Migrated "{b.title[:40]}".')
    except Exception as e:
        flash(f'Failed: {str(e)[:150]}')
    return redirect(url_for('library_storage_status'))


# ---------- CV / Resume Maker ----------
class CV(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    role = db.Column(db.String(200))
    template = db.Column(db.String(30), default='classic')
    data_json = db.Column(db.Text)
    photo_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


CV_TEMPLATES = {
    'classic':   {'label': '📜 Classic Professional', 'color': '#1a1a1a', 'font': 'serif'},
    'modern':    {'label': '⬛ Modern Minimalist',    'color': '#0d6efd', 'font': 'sans'},
    'twocol':    {'label': '📊 Two-Column',          'color': '#1a3a6b', 'font': 'sans'},
    'executive': {'label': '👔 Executive Bold',      'color': '#8b0000', 'font': 'serif'},
    'creative':  {'label': '🎨 Creative Accent',     'color': '#6f42c1', 'font': 'sans'},
    'academic':  {'label': '📚 Academic Long-Form',  'color': '#2d5016', 'font': 'serif'},
}


@app.route('/cv')
def cv_home():
    cvs = CV.query.order_by(CV.created_at.desc()).limit(50).all()
    return render_template('cv_home.html', cvs=cvs, templates=CV_TEMPLATES)


@app.route('/cv/new')
def cv_new():
    return render_template('cv_form.html', cv=None, templates=CV_TEMPLATES)


@app.route('/cv/<int:cid>/edit')
def cv_edit(cid):
    cv = CV.query.get_or_404(cid)
    try:
        data = _lazy_json.loads(cv.data_json or '{}')
    except Exception:
        data = {}
    return render_template('cv_form.html', cv=cv, data=data, templates=CV_TEMPLATES)


@app.route('/cv/save', methods=['POST'])
def cv_save():
    cid = request.form.get('cv_id', '').strip()
    name = request.form.get('name', '').strip()
    role = request.form.get('role', '').strip()
    template = request.form.get('template', 'classic').strip()

    # Build data
    data = {
        'email': request.form.get('email', '').strip(),
        'phone': request.form.get('phone', '').strip(),
        'address': request.form.get('address', '').strip(),
        'website': request.form.get('website', '').strip(),
        'linkedin': request.form.get('linkedin', '').strip(),
        'summary': request.form.get('summary', '').strip(),
        'education': [],
        'experience': [],
        'projects': [],
        'certifications': [],
        'skills': request.form.get('skills', '').strip(),
        'languages': request.form.get('languages', '').strip(),
        'hobbies': request.form.get('hobbies', '').strip(),
        'achievements': request.form.get('achievements', '').strip(),
    }

    # Education rows: edu_degree[], edu_inst[], edu_year[], edu_grade[]
    degrees = request.form.getlist('edu_degree')
    insts = request.form.getlist('edu_inst')
    years = request.form.getlist('edu_year')
    grades = request.form.getlist('edu_grade')
    for i, d in enumerate(degrees):
        if d.strip():
            data['education'].append({
                'degree': d.strip(),
                'institution': insts[i].strip() if i < len(insts) else '',
                'year': years[i].strip() if i < len(years) else '',
                'grade': grades[i].strip() if i < len(grades) else '',
            })

    # Experience: exp_role[], exp_company[], exp_duration[], exp_desc[]
    roles = request.form.getlist('exp_role')
    companies = request.form.getlist('exp_company')
    durations = request.form.getlist('exp_duration')
    descriptions = request.form.getlist('exp_desc')
    for i, r in enumerate(roles):
        if r.strip():
            data['experience'].append({
                'role': r.strip(),
                'company': companies[i].strip() if i < len(companies) else '',
                'duration': durations[i].strip() if i < len(durations) else '',
                'description': descriptions[i].strip() if i < len(descriptions) else '',
            })

    # Projects: proj_name[], proj_desc[]
    pnames = request.form.getlist('proj_name')
    pdescs = request.form.getlist('proj_desc')
    for i, p in enumerate(pnames):
        if p.strip():
            data['projects'].append({
                'name': p.strip(),
                'description': pdescs[i].strip() if i < len(pdescs) else '',
            })

    # Certifications: cert_name[], cert_issuer[], cert_year[]
    cnames = request.form.getlist('cert_name')
    cissuers = request.form.getlist('cert_issuer')
    cyears = request.form.getlist('cert_year')
    for i, c in enumerate(cnames):
        if c.strip():
            data['certifications'].append({
                'name': c.strip(),
                'issuer': cissuers[i].strip() if i < len(cissuers) else '',
                'year': cyears[i].strip() if i < len(cyears) else '',
            })

    # Photo upload
    photo_url = request.form.get('existing_photo', '').strip()
    if 'photo_file' in request.files:
        pf = request.files['photo_file']
        if pf and pf.filename:
            os.makedirs('static/cv_photos', exist_ok=True)
            fname = secure_filename(f"cv_{int(_lazy_time.time())}_{pf.filename}")
            pf.save(os.path.join('static/cv_photos', fname))
            photo_url = f'/static/cv_photos/{fname}'

    if cid:
        cv = CV.query.get(int(cid))
        if not cv:
            flash('CV not found.')
            return redirect(url_for('cv_home'))
        cv.name = name
        cv.role = role
        cv.template = template
        cv.data_json = _lazy_json.dumps(data)
        cv.photo_url = photo_url
    else:
        cv = CV(
            name=name, role=role, template=template,
            data_json=_lazy_json.dumps(data),
            photo_url=photo_url
        )
        db.session.add(cv)
    db.session.commit()
    return redirect(url_for('cv_view', cid=cv.id))


@app.route('/cv/<int:cid>')
def cv_view(cid):
    cv = CV.query.get_or_404(cid)
    try:
        data = _lazy_json.loads(cv.data_json or '{}')
    except Exception:
        data = {}
    return render_template('cv_view.html', cv=cv, data=data, templates=CV_TEMPLATES)


@app.route('/cv/<int:cid>/print')
def cv_print(cid):
    cv = CV.query.get_or_404(cid)
    try:
        data = _lazy_json.loads(cv.data_json or '{}')
    except Exception:
        data = {}
    return render_template('cv_print.html', cv=cv, data=data, templates=CV_TEMPLATES)


@app.route('/cv/<int:cid>/delete', methods=['POST'])
def cv_delete(cid):
    cv = CV.query.get_or_404(cid)
    if cv.photo_url and cv.photo_url.startswith('/static/cv_photos/'):
        try: os.remove(cv.photo_url.lstrip('/'))
        except: pass
    db.session.delete(cv)
    db.session.commit()
    flash('CV deleted.')
    return redirect(url_for('cv_home'))


# ---------- Study Toolkit ----------
@app.route('/toolkit')
def toolkit_home():
    return render_template('toolkit_home.html')


@app.route('/toolkit/notes')
def toolkit_notes():
    return render_template('toolkit_notes.html')


@app.route('/toolkit/timer')
def toolkit_timer():
    return render_template('toolkit_timer.html')


@app.route('/toolkit/recorder')
def toolkit_recorder():
    return render_template('toolkit_recorder.html')


# ---------- Study Toolkit ----------





# ---------- Theme Weights (restored) ----------
def _current_theme_weights():
    """Month-wise section weight multipliers."""
    from datetime import datetime as _dtnow
    m = _dtnow.now().month
    weights = {
        1:  {'Economy': 1.6, 'Polity': 1.2, 'Society': 1.1},
        2:  {'Economy': 1.8, 'Polity': 1.3, 'International': 1.1},
        3:  {'Economy': 1.5, 'Polity': 1.3, 'Environment': 1.2},
        4:  {'Environment': 1.7, 'International': 1.2, 'Economy': 1.1},
        5:  {'Environment': 1.8, 'Governance': 1.2, 'Science & Tech': 1.1},
        6:  {'Environment': 1.6, 'International': 1.2, 'Polity': 1.1},
        7:  {'Polity': 1.6, 'International': 1.4, 'Editorial': 1.2},
        8:  {'Polity': 1.7, 'International': 1.5, 'Sports': 1.3},
        9:  {'International': 1.6, 'Polity': 1.4, 'Science & Tech': 1.2},
        10: {'Awards & Honours': 1.8, 'Sports': 1.5, 'Environment': 1.3},
        11: {'Environment': 1.7, 'Awards & Honours': 1.5, 'International': 1.3},
        12: {'Sports': 1.5, 'Environment': 1.4, 'Awards & Honours': 1.3},
    }
    return weights.get(m, {})


def _current_theme_name():
    """Month-wise theme name for masthead."""
    from datetime import datetime as _dtnow
    m = _dtnow.now().month
    names = {
        1: 'Budget Focus', 2: 'Economic Survey Focus', 3: 'Union Budget Aftermath',
        4: 'Environment & Climate', 5: 'Monsoon & Biodiversity', 6: 'Green Policy',
        7: 'Parliament Session', 8: 'International Diplomacy', 9: 'Global Summits',
        10: 'Award Season', 11: 'Climate COP Focus', 12: 'Sports Year-End',
    }
    return names.get(m, 'Balanced Edition')

# ================= EXPANDED E-PAPER SECTIONS (Patch 1) =================
# Appended safely. Extends CORE at import time. Does not touch existing code.
try:
    _IAS_EXTRA_SECTIONS = [
        'History & Culture',
        'Geography',
        'Cinema & Awards',
        'Sports Extended',
        'Defence & Security',
        'Health & Biotech',
        'India Regional',
        'World Regional',
        'Reports & Indices',
        'Schemes & Policy',
    ]
    if isinstance(CORE, list):
        for _s in _IAS_EXTRA_SECTIONS:
            if _s not in CORE:
                CORE.append(_s)
except Exception as _e:
    import sys
    print('[sections-extend] failed:', _e, file=sys.stderr)

# ================= NEW RSS FEEDS (Patch 2) =================
def _ias_find_rss_list():
    import sys
    g = sys.modules.get('app', sys.modules[__name__]).__dict__
    hits = []
    for name, val in g.items():
        if not isinstance(val, list) or len(val) < 3:
            continue
        sample = val[:6]
        if not all(isinstance(x, dict) for x in sample):
            continue
        if not all(('name' in x and 'url' in x and 'category' in x) for x in sample):
            continue
        u = str(sample[0].get('url', '')).lower()
        if 'rss' in u or 'feed' in u or 'news.google' in u:
            hits.append((name, len(val), val))
    return hits

_ias_new_feeds = [
    {'name': 'ASI Monuments',   'url': 'https://news.google.com/rss/search?q=Archaeological+Survey+of+India+OR+ASI+monument+when:3d&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'History & Culture'},
    {'name': 'Heritage',        'url': 'https://news.google.com/rss/search?q=India+heritage+OR+culture+ministry+OR+UNESCO+India&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'History & Culture'},
    {'name': 'Disasters',       'url': 'https://news.google.com/rss/search?q=flood+India+OR+cyclone+OR+monsoon&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Geography'},
    {'name': 'Earth/Geog',      'url': 'https://news.google.com/rss/search?q=India+river+OR+glacier+OR+earthquake+OR+geography&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Geography'},
    {'name': 'Oscar',           'url': 'https://news.google.com/rss/search?q=Oscar+OR+Academy+Awards+India&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Cinema & Awards'},
    {'name': 'National Film',   'url': 'https://news.google.com/rss/search?q=National+Film+Awards+OR+Filmfare+India&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Cinema & Awards'},
    {'name': 'Olympics',        'url': 'https://news.google.com/rss/search?q=Olympics+OR+IOA+OR+India+olympic&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Sports Extended'},
    {'name': 'FIFA',            'url': 'https://news.google.com/rss/search?q=FIFA+World+Cup+OR+AIFF+OR+India+football&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Sports Extended'},
    {'name': 'Cricket',         'url': 'https://news.google.com/rss/search?q=cricket+India+BCCI+ICC&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Sports Extended'},
    {'name': 'DRDO/Defence',    'url': 'https://news.google.com/rss/search?q=DRDO+OR+Ministry+of+Defence+India+missile&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Defence & Security'},
    {'name': 'Armed Forces',    'url': 'https://news.google.com/rss/search?q=Indian+Army+Navy+Air+Force+exercise&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Defence & Security'},
    {'name': 'Health',          'url': 'https://news.google.com/rss/search?q=ICMR+OR+health+ministry+India+disease&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Health & Biotech'},
    {'name': 'Biotech/Pharma',  'url': 'https://news.google.com/rss/search?q=biotech+India+vaccine+OR+pharma&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Health & Biotech'},
    {'name': 'State News',      'url': 'https://news.google.com/rss/search?q=India+state+government+scheme+OR+chief+minister&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'India Regional'},
    {'name': 'World Powers',    'url': 'https://news.google.com/rss/search?q=United+States+China+European+Union+India+relations&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'World Regional'},
    {'name': 'Neighbours',      'url': 'https://news.google.com/rss/search?q=Pakistan+Bangladesh+Nepal+Sri+Lanka+India&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'World Regional'},
    {'name': 'Reports/Indices', 'url': 'https://news.google.com/rss/search?q=NITI+Aayog+OR+World+Bank+India+report+OR+index&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Reports & Indices'},
    {'name': 'Schemes',         'url': 'https://news.google.com/rss/search?q=India+government+scheme+launch+OR+PIB+policy&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Schemes & Policy'},
]

_ias_cands = _ias_find_rss_list()
print('[patch2] found', len(_ias_cands), 'candidate RSS lists')
for _n, _sz, _ in _ias_cands:
    print('  candidate:', _n, 'size =', _sz)

if _ias_cands:
    _tname, _, _tlist = _ias_cands[0]
    _existing = {x.get('name') for x in _tlist}
    _added = 0
    for _f in _ias_new_feeds:
        if _f['name'] not in _existing:
            _tlist.append(_f)
            _added += 1
    print(f'[patch2] appended {_added} feeds to "{_tname}" (now {len(_tlist)} total)')
else:
    print('[patch2] WARNING: no RSS list found.')
    print('[patch2] Run: grep -n "SOURCES\\|FEEDS\\|RSS_" ~/ias_machine/app.py | head -20')

# ================= SYNC MISSING SECTIONS (Patch 3) =================
# Runs before /epaper/lazy loads. Adds any CORE sections missing from
# today's existing DailyPaper. Fixes the local-variable CORE shadow bug.
try:
    @app.before_request
    def _ias_sync_epaper_sections():
        from flask import request as _rq
        if _rq.path != '/epaper/lazy' or _rq.method != 'GET':
            return None
        try:
            today = _dt.now().strftime('%Y-%m-%d')
            paper = DailyPaper.query.filter_by(date=today).first()
            if not paper:
                return None  # route will create fresh with all sections
            existing = {s.name for s in PaperSection.query.filter_by(paper_id=paper.id).all()}
            added = 0
            for name in CORE:
                if name not in existing:
                    db.session.add(PaperSection(paper_id=paper.id, name=name, status='pending'))
                    added += 1
            if added:
                db.session.commit()
                print(f'[sync-sections] added {added} new sections to {today} paper')
        except Exception as e:
            try: db.session.rollback()
            except Exception: pass
            import sys
            print('[sync-sections] error:', e, file=sys.stderr)
        return None
    print('[patch3] before_request sync registered')
except Exception as _e:
    import sys
    print('[patch3] FAILED:', _e, file=sys.stderr)

# ================= PATCH 4: Explicit section list + sync =================
IAS_EPAPER_SECTIONS = [
    'Front Page', 'Polity', 'Economy', 'International', 'Environment',
    'Science & Tech', 'Editorial', 'Society', 'Governance',
    'History & Culture', 'Geography', 'Cinema & Awards', 'Sports Extended',
    'Defence & Security', 'Health & Biotech', 'India Regional',
    'World Regional', 'Reports & Indices', 'Schemes & Policy',
]

try:
    @app.before_request
    def _ias_sync_epaper_sections_v2():
        from flask import request as _rq
        from datetime import datetime as _dtv2
        if _rq.path != '/epaper/lazy' or _rq.method != 'GET':
            return None
        try:
            today = _dtv2.now().strftime('%Y-%m-%d')
            paper = DailyPaper.query.filter_by(date=today).first()
            if not paper:
                return None
            existing = {s.name for s in PaperSection.query.filter_by(paper_id=paper.id).all()}
            added = 0
            for name in IAS_EPAPER_SECTIONS:
                if name not in existing:
                    db.session.add(PaperSection(paper_id=paper.id, name=name, status='pending'))
                    added += 1
            if added:
                db.session.commit()
                print(f'[sync-v2] added {added} sections to {today}')
        except Exception as e:
            try: db.session.rollback()
            except Exception: pass
            import sys
            print('[sync-v2] error:', e, file=sys.stderr)
        return None
    print('[patch4] registered. total sections =', len(IAS_EPAPER_SECTIONS))
except Exception as _e:
    import sys
    print('[patch4] FAILED:', _e, file=sys.stderr)

# ============ PATCH 5: Real per-section news sources ============
# Each section pulls from its own newspaper feeds, not a shared pool.
_ias_original_generate_section = _lazy_generate_section

def _ias_gnrss(q):
    return f'https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en'

IAS_SECTION_FEEDS = {
 'Front Page': [_ias_gnrss('site:pib.gov.in+when:1d'), _ias_gnrss('site:thehindu.com+when:1d')],
 'Polity': [_ias_gnrss('site:thehindu.com+(parliament+OR+supreme+court+OR+election+OR+constitution)+when:3d'),
            _ias_gnrss('site:indianexpress.com+(parliament+OR+supreme+court+OR+election)+when:3d'),
            _ias_gnrss('site:pib.gov.in+(bill+OR+act+OR+parliament)+when:3d')],
 'Economy': [_ias_gnrss('site:livemint.com+(economy+OR+RBI+OR+budget+OR+GDP+OR+inflation)+when:3d'),
             _ias_gnrss('site:thehindu.com+(economy+OR+RBI+OR+budget+OR+fiscal)+when:3d'),
             _ias_gnrss('site:indianexpress.com+(economy+OR+RBI+OR+budget)+when:3d')],
 'International': [_ias_gnrss('site:thehindu.com+(diplomacy+OR+bilateral+OR+UN+OR+foreign)+when:3d'),
                   _ias_gnrss('site:indianexpress.com+(diplomacy+OR+UN+OR+foreign+policy)+when:3d'),
                   _ias_gnrss('India+diplomacy+when:2d')],
 'Environment': [_ias_gnrss('site:downtoearth.org.in+when:3d'),
                 _ias_gnrss('site:thehindu.com+(climate+OR+environment+OR+COP+OR+biodiversity)+when:3d')],
 'Science & Tech': [_ias_gnrss('site:thehindu.com+(ISRO+OR+DRDO+OR+science+OR+technology)+when:3d'),
                    _ias_gnrss('site:pib.gov.in+(ISRO+OR+DRDO+OR+science+OR+research)+when:3d')],
 'Editorial': [_ias_gnrss('site:thehindu.com/opinion+when:3d'),
               _ias_gnrss('site:indianexpress.com/opinion+when:3d')],
 'Society': [_ias_gnrss('site:thehindu.com+(women+OR+caste+OR+education+OR+poverty)+when:3d'),
             _ias_gnrss('site:indianexpress.com+(society+OR+women+OR+education)+when:3d')],
 'Governance': [_ias_gnrss('site:pib.gov.in+(governance+OR+reform+OR+policy)+when:3d'),
                _ias_gnrss('site:thehindu.com+(governance+OR+reform+OR+transparency)+when:3d')],
 'History & Culture': [_ias_gnrss('site:thehindu.com+(heritage+OR+culture+OR+ASI+OR+monument)+when:7d'),
                       _ias_gnrss('site:pib.gov.in+(culture+OR+heritage+OR+archaeology)+when:7d')],
 'Geography': [_ias_gnrss('site:downtoearth.org.in+(flood+OR+cyclone+OR+glacier+OR+river)+when:3d'),
               _ias_gnrss('site:thehindu.com+(flood+OR+cyclone+OR+monsoon+OR+earthquake)+when:3d')],
 'Cinema & Awards': [_ias_gnrss('(National+Film+Awards+OR+Padma+Awards+OR+Oscar+OR+Jnanpith)+India+when:7d'),
                     _ias_gnrss('site:thehindu.com+(award+OR+honour+OR+Padma)+when:7d')],
 'Sports Extended': [_ias_gnrss('(Olympics+OR+FIFA+World+Cup+OR+Asian+Games+OR+Commonwealth+Games)+India+when:7d'),
                     _ias_gnrss('site:thehindu.com+(olympics+OR+asian+games+OR+fifa)+when:7d')],
 'Defence & Security': [_ias_gnrss('site:pib.gov.in+(defence+OR+army+OR+navy+OR+missile+OR+border)+when:3d'),
                        _ias_gnrss('site:thehindu.com+(defence+OR+security+OR+armed+forces)+when:3d')],
 'Health & Biotech': [_ias_gnrss('site:pib.gov.in+(health+OR+ICMR+OR+vaccine+OR+biotech)+when:3d'),
                      _ias_gnrss('site:thehindu.com+(health+OR+disease+OR+ICMR+OR+pharma)+when:3d')],
 'India Regional': [_ias_gnrss('site:thehindu.com+(state+OR+district+OR+governor)+when:2d'),
                    _ias_gnrss('site:indianexpress.com+(state+OR+district)+when:2d')],
 'World Regional': [_ias_gnrss('(United+States+OR+China+OR+European+Union+OR+Russia)+India+when:2d'),
                    _ias_gnrss('site:thehindu.com+(US+OR+China+OR+EU+OR+Russia)+when:2d')],
 'Reports & Indices': [_ias_gnrss('(NITI+Aayog+OR+World+Bank+OR+IMF+OR+index+OR+report)+India+when:7d'),
                       _ias_gnrss('site:pib.gov.in+(report+OR+index)+when:7d')],
 'Schemes & Policy': [_ias_gnrss('site:pib.gov.in+(scheme+OR+yojana+OR+mission)+when:3d'),
                      _ias_gnrss('site:thehindu.com+(scheme+OR+yojana)+when:3d')],
}

def _ias_clean_html(s):
    import re as _re
    if not s: return ''
    s = _re.sub(r'<[^>]+>', ' ', s)
    s = _re.sub(r'\s+', ' ', s)
    return s.strip()

def _ias_parse_rss(url):
    import requests
    from xml.etree import ElementTree as ET
    out = []
    try:
        r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200: return out
        root = ET.fromstring(r.content)
        for item in root.iter('item'):
            t = (item.findtext('title') or '').strip()
            l = (item.findtext('link') or '').strip()
            d = _ias_clean_html(item.findtext('description') or '')
            src = ''
            for s in item.iter('source'):
                src = (s.text or '').strip(); break
            if not t or not l: continue
            out.append({'title': t[:300], 'summary': d[:600], 'link': l, 'source': src or 'Google News'})
    except Exception:
        pass
    return out

def _ias_fetch_section_feeds(section_name, max_items=8):
    urls = IAS_SECTION_FEEDS.get(section_name, [])
    if not urls: return []
    all_items, seen = [], set()
    for u in urls:
        for art in _ias_parse_rss(u):
            k = art['title'].lower()[:80]
            if k in seen: continue
            seen.add(k)
            all_items.append(art)
            if len(all_items) >= max_items * 2: break
        if len(all_items) >= max_items * 2: break
    return all_items[:max_items]

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=8)
    if not fetched:
        return _ias_original_generate_section(paper, section)

    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass

    filtered = [a for a in fetched if a['title'][:80].lower() not in existing]
    if not filtered: filtered = fetched

    matching = filtered[:6]
    saved = 0
    for art in matching[:5]:
        try:
            system = ("You are a UPSC news editor. Return JSON: "
                      "{\"summary\":\"Full 150-word newspaper-style article with headline, "
                      "3-4 factual paragraphs, names, numbers, dates\","
                      "\"gs_paper\":\"GS1|GS2|GS3|GS4\",\"relevance\":8}")
            user = f"SECTION: {section.name}\nTITLE: {art['title']}\nCONTENT: {art['summary']}\nSummarize for UPSC."
            content = _lazy_call_any_ai(system, user, max_tokens=800)
            content = content.strip().strip('`').replace('```json','').replace('```','').strip()
            data = _lazy_json.loads(content)
            db.session.add(PaperArticle(
                section_id=section.id, title=art['title'][:300],
                summary=data.get('summary', art['summary'][:200]),
                source=art['source'], url=art['link'],
                gs_paper=data.get('gs_paper',''), relevance=data.get('relevance',6)))
            saved += 1
            _lazy_time.sleep(1.5)
        except Exception:
            continue
    if saved == 0:
        for art in matching[:3]:
            db.session.add(PaperArticle(
                section_id=section.id, title=art['title'][:300],
                summary=art['summary'][:300], source=art['source'],
                url=art['link'], gs_paper='', relevance=6))
    section.status = 'ready'
    db.session.commit()
    return saved

print('[patch5] real per-section feeds loaded:', len(IAS_SECTION_FEEDS), 'sections')

# ============ PATCH 6: Long articles + On This Day ============
import requests as _ias_req
import re as _ias_re

def _ias_fetch_article_body(url, max_chars=3000):
    """Fetch real article text from the news URL."""
    if not url: return ''
    try:
        r = _ias_req.get(url, timeout=10, allow_redirects=True,
                         headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        if r.status_code != 200: return ''
        html = r.text[:250000]
        paras = _ias_re.findall(r'<p[^>]*>(.*?)</p>', html, flags=_ias_re.DOTALL | _ias_re.IGNORECASE)
        chunks = []
        bad = ['cookie','subscribe','sign up','advertisement','read more',
               'also read','follow us','trending','download the app','click here']
        for p in paras:
            t = _ias_re.sub(r'<[^>]+>', ' ', p)
            t = _ias_re.sub(r'\s+', ' ', t).strip()
            if len(t) < 50: continue
            if any(b in t.lower() for b in bad): continue
            chunks.append(t)
            if sum(len(c) for c in chunks) > max_chars: break
        return ' '.join(chunks)[:max_chars]
    except Exception:
        return ''

# Re-wrap generator to fetch full body
_ias_prev_gen6 = _lazy_generate_section

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=8)
    if not fetched:
        return _ias_prev_gen6(paper, section)
    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass
    filtered = [a for a in fetched if a['title'][:80].lower() not in existing] or fetched

    saved = 0
    for art in filtered[:5]:
        try:
            body = _ias_fetch_article_body(art['link'], max_chars=2800)
            src = body if len(body) > 400 else art['summary']

            system = ("You are a senior UPSC news editor writing for The Aspirant's Times. "
                      "Return ONLY valid JSON, no markdown. "
                      '{"summary":"...","gs_paper":"GS2","relevance":8}. '
                      "The summary MUST be 170-200 words in 4 short paragraphs:\n"
                      "P1: lead (who/what/when/where).\n"
                      "P2: key facts, numbers, dates, names.\n"
                      "P3: background/context.\n"
                      "P4: why it matters for UPSC (Prelims fact or Mains angle).\n"
                      "Use ONLY given content. Never invent facts.")
            user = (f"SECTION: {section.name}\nTITLE: {art['title']}\n"
                    f"SOURCE: {art.get('source','')}\nCONTENT:\n{src}\n\nWrite now.")
            content = _lazy_call_any_ai(system, user, max_tokens=1500)
            content = content.strip().strip('`').replace('```json','').replace('```','').strip()
            if content.startswith('json'): content = content[4:].strip()
            data = _lazy_json.loads(content)
            summ = data.get('summary','')
            if len(summ) < 300:
                summ = (src or art['summary'])[:2500]
            db.session.add(PaperArticle(
                section_id=section.id, title=art['title'][:300], summary=summ,
                source=art['source'], url=art['link'],
                gs_paper=data.get('gs_paper',''), relevance=data.get('relevance',6)))
            saved += 1
            _lazy_time.sleep(1.5)
        except Exception:
            try:
                body = _ias_fetch_article_body(art['link'], max_chars=2000)
                txt = body if len(body) > 400 else art['summary']
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300],
                    summary=txt[:2500], source=art['source'],
                    url=art['link'], gs_paper='', relevance=6))
                saved += 1
            except Exception:
                continue
    section.status = 'ready'
    db.session.commit()
    return saved

# On This Day
_ias_otd_cache = {}
def _ias_this_day():
    from datetime import datetime as _dt6
    now = _dt6.utcnow()
    key = f'{now.month:02d}-{now.day:02d}'
    if key in _ias_otd_cache: return _ias_otd_cache[key]
    out = []
    try:
        u = f'https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/{now.month:02d}/{now.day:02d}'
        r = _ias_req.get(u, timeout=6, headers={'User-Agent':'IAS-Machine/1.0'})
        if r.status_code == 200:
            for e in (r.json().get('selected') or [])[:5]:
                t = (e.get('text') or '').strip()
                if t: out.append({'year': e.get('year'), 'text': t[:240]})
    except Exception: pass
    _ias_otd_cache[key] = out
    return out

try:
    @app.route('/epaper/this-day')
    def ias_this_day_route():
        from flask import jsonify
        return jsonify({'events': _ias_this_day()})
    print('[patch6] /epaper/this-day route registered')
except Exception as _e:
    import sys; print('[patch6] route err:', _e, file=sys.stderr)

print('[patch6] long-article fetcher loaded')

# ============ PATCH 7: Direct publisher RSS + full content ============
import requests as _ias_req7
import re as _ias_re7
from xml.etree import ElementTree as _ias_ET7

IAS_DIRECT_FEEDS = {
 'Front Page': [
    'https://www.thehindu.com/news/national/feeder/default.rss',
    'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',
 ],
 'Polity': [
    'https://www.thehindu.com/news/national/feeder/default.rss',
    'https://www.thehindu.com/topic/parliament/feeder/default.rss',
    'https://indianexpress.com/section/india/political-pulse/feed/',
    'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',
 ],
 'Economy': [
    'https://www.thehindu.com/business/Economy/feeder/default.rss',
    'https://www.thehindu.com/business/feeder/default.rss',
    'https://www.livemint.com/rss/economy',
    'https://indianexpress.com/section/business/economy/feed/',
 ],
 'International': [
    'https://www.thehindu.com/news/international/feeder/default.rss',
    'https://indianexpress.com/section/world/feed/',
 ],
 'Environment': [
    'https://www.downtoearth.org.in/rss/environment',
    'https://www.downtoearth.org.in/rss/climate-change',
    'https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss',
 ],
 'Science & Tech': [
    'https://www.thehindu.com/sci-tech/feeder/default.rss',
    'https://www.thehindu.com/sci-tech/technology/feeder/default.rss',
    'https://indianexpress.com/section/technology/feed/',
 ],
 'Editorial': [
    'https://www.thehindu.com/opinion/editorial/feeder/default.rss',
    'https://www.thehindu.com/opinion/op-ed/feeder/default.rss',
    'https://indianexpress.com/section/opinion/editorials/feed/',
 ],
 'Society': [
    'https://www.thehindu.com/society/feeder/default.rss',
    'https://indianexpress.com/section/lifestyle/feed/',
 ],
 'Governance': [
    'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',
    'https://www.thehindu.com/news/national/feeder/default.rss',
 ],
 'History & Culture': [
    'https://www.thehindu.com/society/history-and-culture/feeder/default.rss',
    'https://indianexpress.com/section/research/feed/',
 ],
 'Geography': [
    'https://www.downtoearth.org.in/rss',
    'https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss',
 ],
 'Cinema & Awards': [
    'https://www.thehindu.com/entertainment/movies/feeder/default.rss',
 ],
 'Sports Extended': [
    'https://www.thehindu.com/sport/feeder/default.rss',
    'https://indianexpress.com/section/sports/feed/',
 ],
 'Defence & Security': [
    'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',
    'https://www.thehindu.com/news/national/feeder/default.rss',
 ],
 'Health & Biotech': [
    'https://www.thehindu.com/sci-tech/health/feeder/default.rss',
    'https://indianexpress.com/section/lifestyle/health/feed/',
 ],
 'India Regional': [
    'https://www.thehindu.com/news/national/feeder/default.rss',
    'https://indianexpress.com/section/india/feed/',
 ],
 'World Regional': [
    'https://www.thehindu.com/news/international/feeder/default.rss',
    'https://indianexpress.com/section/world/feed/',
 ],
 'Reports & Indices': [
    'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',
    'https://www.thehindu.com/business/Economy/feeder/default.rss',
 ],
 'Schemes & Policy': [
    'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3',
    'https://www.thehindu.com/news/national/feeder/default.rss',
 ],
}

def _ias_parse_rss7(url):
    out = []
    try:
        r = _ias_req7.get(url, timeout=10,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; IASMachine/1.0)'})
        if r.status_code != 200: return out
        root = _ias_ET7.fromstring(r.content)
        ns = {'content': 'http://purl.org/rss/1.0/modules/content/'}
        for item in root.iter('item'):
            t = (item.findtext('title') or '').strip()
            l = (item.findtext('link') or '').strip()
            desc = item.findtext('description') or ''
            # Prefer content:encoded (full article)
            full = ''
            for el in item.findall('content:encoded', ns):
                full = el.text or ''; break
            if not full:
                for el in item.iter():
                    if el.tag.endswith('encoded') and el.text:
                        full = el.text; break
            body = full if len(full) > len(desc) else desc
            body = _ias_re7.sub(r'<[^>]+>', ' ', body)
            body = _ias_re7.sub(r'&nbsp;', ' ', body)
            body = _ias_re7.sub(r'&amp;', '&', body)
            body = _ias_re7.sub(r'&#8217;', "'", body)
            body = _ias_re7.sub(r'&#8220;|&#8221;', '"', body)
            body = _ias_re7.sub(r'\s+', ' ', body).strip()
            src = ''
            for s in item.iter('source'):
                src = (s.text or '').strip(); break
            if not src:
                m = _ias_re7.match(r'https?://(?:www\.)?([^/]+)', l)
                src = m.group(1) if m else ''
            if not t or not l: continue
            out.append({'title': t[:300], 'summary': body[:3000],
                        'link': l, 'source': src})
    except Exception:
        pass
    return out

def _ias_fetch_section_feeds(section_name, max_items=6):
    urls = IAS_DIRECT_FEEDS.get(section_name, [])
    if not urls: return []
    items, seen = [], set()
    for u in urls:
        for art in _ias_parse_rss7(u):
            k = art['title'].lower()[:80]
            if k in seen: continue
            seen.add(k)
            items.append(art)
            if len(items) >= max_items * 3: break
        if len(items) >= max_items * 3: break
    # Prefer items that have real body (>= 400 chars)
    rich = [a for a in items if len(a['summary']) >= 400]
    thin = [a for a in items if len(a['summary']) < 400]
    return (rich + thin)[:max_items]

_ias_prev_gen7 = _lazy_generate_section

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=6)
    if not fetched:
        return _ias_prev_gen7(paper, section)
    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass
    filtered = [a for a in fetched if a['title'][:80].lower() not in existing] or fetched

    saved = 0
    for art in filtered[:5]:
        body = art['summary']
        try:
            if len(body) >= 500:
                # We have real content — polish it into UPSC shape
                system = ("You are a UPSC news editor. Return ONLY JSON, no markdown: "
                          '{"summary":"...","gs_paper":"GS2","relevance":8}. '
                          "Rewrite the given article into 170-200 words, 4 short paragraphs: "
                          "P1 lead, P2 facts/numbers, P3 background, P4 UPSC relevance. "
                          "Keep ALL facts from source. Do not invent.")
                user = f"SECTION: {section.name}\nTITLE: {art['title']}\nSOURCE_TEXT:\n{body[:2500]}\n\nWrite now."
                content = _lazy_call_any_ai(system, user, max_tokens=1500)
                content = content.strip().strip('`').replace('```json','').replace('```','').strip()
                if content.startswith('json'): content = content[4:].strip()
                data = _lazy_json.loads(content)
                summ = data.get('summary','').strip()
                if len(summ) < 300: summ = body[:2500]
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300], summary=summ,
                    source=art['source'], url=art['link'],
                    gs_paper=data.get('gs_paper',''), relevance=data.get('relevance',6)))
            else:
                # Feed gave only a snippet — save the real snippet, no fake expansion
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300],
                    summary=body[:2500] if body else art['title'],
                    source=art['source'], url=art['link'],
                    gs_paper='', relevance=6))
            saved += 1
            _lazy_time.sleep(1.2)
        except Exception:
            try:
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300],
                    summary=body[:2500] if body else art['title'],
                    source=art['source'], url=art['link'],
                    gs_paper='', relevance=6))
                saved += 1
            except Exception:
                continue
    section.status = 'ready'
    db.session.commit()
    return saved

print('[patch7] direct publisher feeds loaded:', len(IAS_DIRECT_FEEDS))

# ============ PATCH 8: rss2json proxy (bypasses PA whitelist) ============
import requests as _ias_req8
import re as _ias_re8

def _ias_rss2json(rss_url, count=10):
    api = f'https://api.rss2json.com/v1/api.json?rss_url={rss_url}&count={count}'
    try:
        r = _ias_req8.get(api, timeout=15, headers={'User-Agent':'IAS-Machine/1.0'})
        if r.status_code != 200: return []
        data = r.json()
        if data.get('status') != 'ok': return []
        out = []
        for it in data.get('items', []):
            title = (it.get('title') or '').strip()
            link = (it.get('link') or '').strip()
            content = it.get('content') or ''
            desc = it.get('description') or ''
            body = content if len(content) > len(desc) else desc
            body = _ias_re8.sub(r'<[^>]+>', ' ', body)
            body = _ias_re8.sub(r'&nbsp;', ' ', body)
            body = _ias_re8.sub(r'&amp;', '&', body)
            body = _ias_re8.sub(r'&quot;|&#34;', '"', body)
            body = _ias_re8.sub(r'&#8217;|&#39;', "'", body)
            body = _ias_re8.sub(r'&#8220;|&#8221;', '"', body)
            body = _ias_re8.sub(r'&#8212;', '-', body)
            body = _ias_re8.sub(r'\s+', ' ', body).strip()
            if not title or not link: continue
            m = _ias_re8.match(r'https?://(?:www\.)?([^/]+)', link)
            src = m.group(1) if m else ''
            out.append({'title': title[:300], 'summary': body[:3000],
                        'link': link, 'source': src})
        return out
    except Exception:
        return []

def _ias_fetch_section_feeds(section_name, max_items=6):
    urls = IAS_DIRECT_FEEDS.get(section_name, [])
    if not urls: return []
    items, seen = [], set()
    for u in urls:
        for art in _ias_rss2json(u, count=10):
            k = art['title'].lower()[:80]
            if k in seen: continue
            seen.add(k)
            items.append(art)
    rich = [a for a in items if len(a['summary']) >= 400]
    thin = [a for a in items if len(a['summary']) < 400]
    return (rich + thin)[:max_items]

print('[patch8] rss2json proxy fetcher active')

# ============ PATCH 9: Full-article pipeline via r.jina.ai ============
import os as _ias_os9
import requests as _ias_req9
import re as _ias_re9

JINA_KEY = _ias_os9.environ.get('JINA_API_KEY', '').strip()

# Sources that WORK from PythonAnywhere (tested 2026-10-04):
IAS_LIVE_FEEDS = {
 'Front Page': [
    'https://feeds.feedburner.com/ndtvnews-latest',
    'https://feeds.bbci.co.uk/news/world/asia/india/rss.xml',
 ],
 'Polity': [
    'https://feeds.feedburner.com/ndtvnews-india-news',
    'https://feeds.bbci.co.uk/news/world/asia/india/rss.xml',
 ],
 'Economy': [
    'https://feeds.feedburner.com/ndtvnews-business',
    'https://feeds.bbci.co.uk/news/business/rss.xml',
 ],
 'International': [
    'https://feeds.bbci.co.uk/news/world/rss.xml',
    'https://feeds.feedburner.com/ndtvnews-world-news',
 ],
 'Environment': [
    'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
 ],
 'Science & Tech': [
    'https://feeds.bbci.co.uk/news/technology/rss.xml',
    'https://feeds.feedburner.com/ndtvnews-latest',
 ],
 'Editorial': [
    'https://feeds.bbci.co.uk/news/world/rss.xml',
    'https://feeds.feedburner.com/ndtvnews-india-news',
 ],
 'Society': [
    'https://feeds.feedburner.com/ndtvnews-cities',
    'https://feeds.bbci.co.uk/news/education/rss.xml',
 ],
 'Governance': [
    'https://feeds.feedburner.com/ndtvnews-india-news',
 ],
 'History & Culture': [
    'https://feeds.feedburner.com/ndtvnews-cities',
 ],
 'Geography': [
    'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
 ],
 'Cinema & Awards': [
    'https://feeds.feedburner.com/ndtvnews-entertainment',
 ],
 'Sports Extended': [
    'https://feeds.feedburner.com/ndtvnews-sports',
    'https://feeds.bbci.co.uk/news/world/rss.xml',
 ],
 'Defence & Security': [
    'https://feeds.feedburner.com/ndtvnews-india-news',
 ],
 'Health & Biotech': [
    'https://feeds.bbci.co.uk/news/health/rss.xml',
 ],
 'India Regional': [
    'https://feeds.feedburner.com/ndtvnews-cities',
    'https://feeds.bbci.co.uk/news/world/asia/india/rss.xml',
 ],
 'World Regional': [
    'https://feeds.bbci.co.uk/news/world/rss.xml',
 ],
 'Reports & Indices': [
    'https://feeds.bbci.co.uk/news/business/rss.xml',
    'https://feeds.feedburner.com/ndtvnews-business',
 ],
 'Schemes & Policy': [
    'https://feeds.feedburner.com/ndtvnews-india-news',
 ],
}

def _ias_parse_feed9(url, count=10):
    import xml.etree.ElementTree as ET
    out = []
    try:
        r = _ias_req9.get(url, timeout=12,
            headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'})
        if r.status_code != 200: return out
        root = ET.fromstring(r.content)
        ns = {'content':'http://purl.org/rss/1.0/modules/content/',
              'media':'http://search.yahoo.com/mrss/'}
        for item in root.iter('item'):
            t = (item.findtext('title') or '').strip()
            l = (item.findtext('link') or '').strip()
            desc = item.findtext('description') or ''
            full = ''
            for el in item.findall('content:encoded', ns):
                full = el.text or ''; break
            body = full if len(full) > len(desc) else desc
            body = _ias_re9.sub(r'<[^>]+>', ' ', body)
            for a,b in [('&nbsp;',' '),('&amp;','&'),('&quot;','"'),('&#39;',"'"),
                        ('&#8217;',"'"),('&#8220;','"'),('&#8221;','"'),('&#8212;','-')]:
                body = body.replace(a,b)
            body = _ias_re9.sub(r'\s+', ' ', body).strip()
            if not t or not l: continue
            m = _ias_re9.match(r'https?://(?:www\.)?([^/]+)', l)
            src = m.group(1) if m else ''
            out.append({'title': t[:300], 'summary': body[:4000],
                        'link': l, 'source': src})
            if len(out) >= count: break
    except Exception: pass
    return out

def _ias_jina_fetch(url, max_chars=4000):
    """Fetch full article text via r.jina.ai reader."""
    if not JINA_KEY: return ''
    try:
        api = f'https://r.jina.ai/{url}'
        h = {'Authorization': f'Bearer {JINA_KEY}', 'X-Return-Format': 'markdown'}
        r = _ias_req9.get(api, timeout=25, headers=h)
        if r.status_code != 200: return ''
        txt = r.text
        txt = _ias_re9.sub(r'!\[.*?\]\(.*?\)', '', txt)
        txt = _ias_re9.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)
        txt = _ias_re9.sub(r'#+\s*', '', txt)
        txt = _ias_re9.sub(r'\n{2,}', '\n\n', txt).strip()
        lines = [ln.strip() for ln in txt.split('\n') if len(ln.strip()) > 60]
        body = ' '.join(lines)
        return body[:max_chars]
    except Exception:
        return ''

def _ias_fetch_section_feeds(section_name, max_items=6):
    urls = IAS_LIVE_FEEDS.get(section_name, [])
    if not urls: return []
    items, seen = [], set()
    for u in urls:
        for art in _ias_parse_feed9(u, count=12):
            k = art['title'].lower()[:80]
            if k in seen: continue
            seen.add(k)
            items.append(art)
    return items[:max_items * 2]

_ias_prev_gen9 = _lazy_generate_section

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=6)
    if not fetched:
        return _ias_prev_gen9(paper, section)

    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass
    filtered = [a for a in fetched if a['title'][:80].lower() not in existing] or fetched

    saved = 0
    for art in filtered[:5]:
        try:
            # Try to fetch FULL article via jina
            full = _ias_jina_fetch(art['link'], max_chars=4000)
            source_text = full if len(full) > 600 else art['summary']
            if len(source_text) < 300:
                source_text = art['title']

            if len(source_text) >= 600:
                system = ("You are a UPSC news editor writing for The Aspirant's Times. "
                          "Return ONLY JSON, no markdown: "
                          '{"summary":"...","gs_paper":"GS2","relevance":8}. '
                          "Rewrite the source into 180-220 words, 4 short paragraphs: "
                          "P1 lead (who/what/when/where). P2 facts/numbers/dates/names. "
                          "P3 background/context. P4 why it matters for UPSC (Prelims fact or Mains angle). "
                          "Use ONLY facts present in source. Never invent. Write like The Hindu.")
                user = f"SECTION: {section.name}\nTITLE: {art['title']}\nSOURCE_TEXT:\n{source_text[:3500]}\n\nWrite."
                content = _lazy_call_any_ai(system, user, max_tokens=1800)
                content = content.strip().strip('`').replace('```json','').replace('```','').strip()
                if content.startswith('json'): content = content[4:].strip()
                data = _lazy_json.loads(content)
                summ = data.get('summary','').strip()
                if len(summ) < 400: summ = source_text[:3500]
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300], summary=summ,
                    source=art['source'], url=art['link'],
                    gs_paper=data.get('gs_paper',''), relevance=data.get('relevance',6)))
            else:
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300],
                    summary=source_text[:2500],
                    source=art['source'], url=art['link'],
                    gs_paper='', relevance=6))
            saved += 1
            _lazy_time.sleep(1.0)
        except Exception as e:
            try:
                db.session.rollback()
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300],
                    summary=(art['summary'] or art['title'])[:2500],
                    source=art['source'], url=art['link'],
                    gs_paper='', relevance=6))
                saved += 1
            except Exception:
                pass
    section.status = 'ready'
    db.session.commit()
    return saved

print('[patch9] live feeds:', len(IAS_LIVE_FEEDS), '| jina:', 'ON' if JINA_KEY else 'OFF')

# ============ PATCH 10: Robust key loading + test route ============
import os as _ias_os10
import requests as _ias_req10
import re as _ias_re10

# Read key from env OR .env file directly OR fallback
def _ias_read_key():
    k = _ias_os10.environ.get('JINA_API_KEY', '').strip()
    if k: return k
    try:
        with open(_ias_os10.path.expanduser('~/ias_machine/.env')) as f:
            for ln in f:
                if ln.startswith('JINA_API_KEY='):
                    return ln.split('=',1)[1].strip()
    except Exception: pass
    return 'jina_f0d572b40d3847feb99d2b5151302517N1kqTEaHskgTsyCi4YS4vDMzxirm'

JINA_KEY = _ias_read_key()
_ias_os10.environ['JINA_API_KEY'] = JINA_KEY

print('[patch10] JINA_KEY loaded, length =', len(JINA_KEY))

def _ias_jina_fetch(url, max_chars=4000):
    if not JINA_KEY: return ''
    try:
        api = f'https://r.jina.ai/{url}'
        h = {'Authorization': f'Bearer {JINA_KEY}',
             'X-Return-Format': 'markdown',
             'X-Timeout': '20'}
        r = _ias_req10.get(api, timeout=30, headers=h)
        if r.status_code != 200:
            print(f'[jina] HTTP {r.status_code} for {url[:80]}')
            return ''
        txt = r.text
        txt = _ias_re10.sub(r'!\[.*?\]\(.*?\)', '', txt)
        txt = _ias_re10.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)
        txt = _ias_re10.sub(r'#+\s*', '', txt)
        txt = _ias_re10.sub(r'\n{2,}', '\n\n', txt).strip()
        lines = [ln.strip() for ln in txt.split('\n') if len(ln.strip()) > 60]
        body = ' '.join(lines)
        return body[:max_chars]
    except Exception as e:
        print(f'[jina] err: {str(e)[:80]}')
        return ''

try:
    @app.route('/epaper/test-jina')
    def ias_test_jina():
        from flask import jsonify
        t = _ias_jina_fetch('https://www.bbc.com/news/world/asia/india', max_chars=800)
        return jsonify({'key_len': len(JINA_KEY), 'fetched_chars': len(t),
                        'preview': t[:500]})
except Exception as _e:
    import sys; print('[patch10] route err:', _e, file=sys.stderr)

# ============ PATCH 11: Clean jina extraction ============
import re as _ias_re11

def _ias_jina_fetch(url, max_chars=4000):
    import os as _os11, requests as _rq11
    key = _os11.environ.get('JINA_API_KEY','').strip()
    if not key: return ''
    try:
        r = _rq11.get(f'https://r.jina.ai/{url}', timeout=30,
            headers={'Authorization': f'Bearer {key}',
                     'X-Return-Format': 'markdown',
                     'X-Timeout': '20'})
        if r.status_code != 200:
            print(f'[jina] HTTP {r.status_code} {url[:60]}')
            return ''
        txt = r.text

        # Strip jina header
        if 'Markdown Content:' in txt:
            txt = txt.split('Markdown Content:', 1)[1]

        # Strip markdown images and links
        txt = _ias_re11.sub(r'!\[.*?\]\(.*?\)', '', txt)
        txt = _ias_re11.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', txt)

        # Drop nav-junk lines by keywords
        junk = ['advertisement','skip to content','sign in','subscribe',
                'watch live','listen live','bbc in other languages',
                'follow bbc','terms of use','privacy policy','cookies',
                'copyright','contact bbc','read more','related topics',
                'more from','share','save','email','whatsapp','facebook',
                'twitter','instagram','youtube','menu','navigation']
        lines = []
        for ln in txt.split('\n'):
            s = ln.strip()
            if len(s) < 60: continue
            sl = s.lower()
            if any(j in sl for j in junk): continue
            if s.startswith('#'): continue
            lines.append(s)

        body = ' '.join(lines)
        body = _ias_re11.sub(r'\s+', ' ', body).strip()
        return body[:max_chars]
    except Exception as e:
        print(f'[jina] err {str(e)[:80]}')
        return ''

print('[patch11] clean jina extractor active')

# ============ PATCH 14: Disable old noisy hooks, fix refresh button ============
# Patch 3's before_request references undefined CORE — kill it silently.
try:
    _ias_old_sync = None
    for _fn in list(app.before_request_funcs.get(None, [])):
        if getattr(_fn, '__name__', '') == '_ias_sync_epaper_sections':
            app.before_request_funcs[None].remove(_fn)
            print('[patch14] removed noisy _ias_sync_epaper_sections hook')
except Exception as _e:
    import sys; print('[patch14] cleanup err:', _e, file=sys.stderr)

# Inline refresh banner instead of floating overlay
try:
    @app.after_request
    def _ias_inject_refresh(resp):
        from flask import request as _rq
        if _rq.path != '/epaper/lazy': return resp
        if resp.mimetype != 'text/html': return resp
        try:
            body = resp.get_data(as_text=True)
        except Exception:
            return resp
        if 'ias-inline-refresh' in body: return resp
        snippet = '''
<div id="ias-inline-refresh" style="margin:8px 14px;padding:10px 12px;background:#fff8e1;border:1px solid #f0d98a;border-radius:8px;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:space-between;gap:10px;">
  <span id="ias-fresh-label" style="font-size:12px;color:#6b5900;font-weight:600;">🟢 just loaded</span>
  <button onclick="(function(){var u=new URL(location.href);u.searchParams.set('_t',Date.now());location.replace(u.toString());})()"
          style="background:#d4a017;color:#1a1a1a;border:none;padding:7px 14px;border-radius:14px;font-size:12px;font-weight:700;cursor:pointer;">
    ⟳ Refresh
  </button>
</div>
<script>
(function(){
  var t0 = Date.now();
  function tick(){
    var el = document.getElementById('ias-fresh-label');
    if(!el) return;
    var s = Math.floor((Date.now()-t0)/1000);
    var txt;
    if(s<5)       txt='🟢 just loaded';
    else if(s<60) txt='🟢 '+s+'s ago';
    else if(s<600)txt='🟡 '+Math.floor(s/60)+'m ago';
    else          txt='🟠 '+Math.floor(s/60)+'m ago — tap Refresh';
    el.textContent = txt;
  }
  setInterval(tick, 1000); tick();
})();
</script>
'''
        marker = '<div class="ep-toolbar'
        if marker in body:
            idx = body.find(marker)
            close = body.find('>', idx)
            if close != -1:
                body = body[:close+1] + snippet + body[close+1:]
        else:
            body = body.replace('</body>', snippet + '</body>', 1)
        resp.set_data(body)
        return resp
    print('[patch14] inline refresh banner registered')
except Exception as _e:
    import sys; print('[patch14] banner err:', _e, file=sys.stderr)

# ============ PATCH 15: Force long articles, no lazy snippets ============
_ias_prev_gen15 = _lazy_generate_section

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=6)
    if not fetched:
        return _ias_prev_gen15(paper, section)

    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass
    filtered = [a for a in fetched if a['title'][:80].lower() not in existing] or fetched

    saved = 0
    for art in filtered[:5]:
        try:
            full = _ias_jina_fetch(art['link'], max_chars=4000)
            has_full = len(full) > 400
            source_text = full if has_full else art['summary']

            if has_full:
                system = ("UPSC news editor. Return ONLY JSON, no markdown: "
                          '{"summary":"...","gs_paper":"GS2","relevance":8}. '
                          "Rewrite source into 180-220 words in 4 short paragraphs: "
                          "P1 lead (who/what/when/where). P2 facts, numbers, dates, names. "
                          "P3 background. P4 UPSC relevance (Prelims fact or Mains angle). "
                          "Use ONLY facts in source. Never invent.")
                user = (f"SECTION: {section.name}\nTITLE: {art['title']}\n"
                        f"SOURCE_TEXT:\n{source_text[:3500]}\n\nWrite.")
            else:
                system = ("You are a UPSC news editor writing for The Aspirant's Times. "
                          "Return ONLY JSON, no markdown: "
                          '{"summary":"...","gs_paper":"GS2","relevance":7}. '
                          "Write a 150-180 word UPSC news brief in 3 short paragraphs: "
                          "P1 the event (from headline/snippet). "
                          "P2 well-established background on the topic - policy, history, "
                          "institution, or geography involved (general knowledge only). "
                          "P3 why it matters for UPSC - Prelims fact or Mains angle. "
                          "Never invent specific numbers, dates, names, or quotes not in source. "
                          "If unsure about specifics, write generally. Write like The Hindu brief.")
                user = (f"SECTION: {section.name}\nHEADLINE: {art['title']}\n"
                        f"SOURCE: {art['source']}\nSNIPPET: {source_text[:600]}\n\nWrite.")

            content = _lazy_call_any_ai(system, user, max_tokens=1800)
            content = content.strip().strip('`').replace('```json','').replace('```','').strip()
            if content.startswith('json'): content = content[4:].strip()
            data = _lazy_json.loads(content)
            summ = data.get('summary','').strip()
            if len(summ) < 400:
                summ = (source_text or art['title'])[:2500]
            db.session.add(PaperArticle(
                section_id=section.id, title=art['title'][:300], summary=summ,
                source=art['source'], url=art['link'],
                gs_paper=data.get('gs_paper',''), relevance=data.get('relevance',7)))
            saved += 1
            _lazy_time.sleep(1.5)
        except Exception as e:
            print(f'[gen15] err {str(e)[:120]}')
            try: db.session.rollback()
            except Exception: pass
    section.status = 'ready'
    db.session.commit()
    return saved

# -------- Debug route --------
try:
    @app.route('/epaper/debug')
    def ias_debug():
        from flask import jsonify
        import os as _osd
        out = {}
        k = _osd.environ.get('JINA_API_KEY','').strip()
        out['jina_key_len'] = len(k)
        try:
            parsed = _ias_jina_fetch('https://www.bbc.com/news/world/asia/india', max_chars=800)
            out['jina_parsed_len'] = len(parsed)
            out['jina_preview'] = parsed[:350]
        except Exception as e:
            out['jina_err'] = str(e)[:200]
        try:
            rows = PaperArticle.query.order_by(PaperArticle.id.desc()).limit(6).all()
            out['recent'] = [{'t': (r.title or '')[:70], 'len': len(r.summary or ''),
                              'src': r.source} for r in rows]
        except Exception as e:
            out['db_err'] = str(e)[:200]
        return jsonify(out)
    print('[patch15] debug route /epaper/debug registered')
except Exception as _e:
    import sys; print('[patch15] route err:', _e, file=sys.stderr)

print('[patch15] guaranteed-long-articles loader active')

# ============ PATCH 17: Slower AI + save source text on AI failure ============
import time as _ias_time17
_ias_prev_gen17 = _lazy_generate_section

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=6)
    if not fetched:
        return _ias_prev_gen17(paper, section)

    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass
    filtered = [a for a in fetched if a['title'][:80].lower() not in existing] or fetched

    saved = 0
    for art in filtered[:4]:  # cap at 4 to reduce rate limit
        try:
            full = _ias_jina_fetch(art['link'], max_chars=4000)
            has_full = len(full) > 400
            source_text = full if has_full else art['summary']

            if has_full:
                system = ("UPSC news editor. Return ONLY JSON, no markdown: "
                          '{"summary":"...","gs_paper":"GS2","relevance":8}. '
                          "Rewrite source into 180-220 words in 4 short paragraphs: "
                          "P1 lead (who/what/when/where). P2 facts, numbers, dates, names. "
                          "P3 background. P4 UPSC relevance. Use ONLY facts in source. Never invent.")
                user = (f"SECTION: {section.name}\nTITLE: {art['title']}\n"
                        f"SOURCE_TEXT:\n{source_text[:3500]}\n\nWrite.")
            else:
                system = ("UPSC news editor. Return ONLY JSON: "
                          '{"summary":"...","gs_paper":"GS2","relevance":7}. '
                          "Write 150-180 words in 3 paragraphs: P1 event, "
                          "P2 well-established background, P3 UPSC angle. "
                          "Never invent numbers, dates, names.")
                user = f"SECTION: {section.name}\nHEADLINE: {art['title']}\nSNIPPET: {source_text[:500]}\nWrite."

            ai_ok = False
            try:
                content = _lazy_call_any_ai(system, user, max_tokens=1600)
                content = content.strip().strip('`').replace('```json','').replace('```','').strip()
                if content.startswith('json'): content = content[4:].strip()
                data = _lazy_json.loads(content)
                summ = data.get('summary','').strip()
                if len(summ) < 400:
                    summ = (source_text or art['title'])[:2500]
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300], summary=summ,
                    source=art['source'], url=art['link'],
                    gs_paper=data.get('gs_paper',''), relevance=data.get('relevance',7)))
                ai_ok = True
            except Exception as ai_e:
                print(f'[gen17] AI err in {section.name}: {str(ai_e)[:120]}')
                try: db.session.rollback()
                except Exception: pass

            if not ai_ok:
                # Fallback: save the jina/source text as the body (better than empty)
                body = (source_text or art['summary'] or art['title'])[:2500]
                db.session.add(PaperArticle(
                    section_id=section.id, title=art['title'][:300], summary=body,
                    source=art['source'], url=art['link'],
                    gs_paper='', relevance=6))

            saved += 1
            _ias_time17.sleep(3.5)  # slower — avoid Groq rate limit
        except Exception as e:
            print(f'[gen17] fatal {str(e)[:120]}')
            try: db.session.rollback()
            except Exception: pass

    # Only mark ready if we actually have articles
    try:
        cnt = PaperArticle.query.filter_by(section_id=section.id).count()
    except Exception:
        cnt = saved
    if cnt > 0:
        section.status = 'ready'
    else:
        section.status = 'pending'
    db.session.commit()
    return saved

print('[patch17] slower AI + fallback body saver active')

# ============ PATCH 18: Short real news, 4 per section, minimal AI ============
import re as _ias_re18
import time as _ias_time18

def _ias_jina_clean18(url, max_chars=1200):
    """Fetch + aggressively clean jina output. Returns first 2-3 real paragraphs."""
    import os as _os18, requests as _rq18
    key = _os18.environ.get('JINA_API_KEY','').strip()
    if not key: return ''
    try:
        r = _rq18.get(f'https://r.jina.ai/{url}', timeout=30,
            headers={'Authorization': f'Bearer {key}',
                     'X-Return-Format': 'markdown',
                     'X-Timeout': '20'})
        if r.status_code != 200: return ''
        txt = r.text
        if 'Markdown Content:' in txt:
            txt = txt.split('Markdown Content:', 1)[1]

        # Aggressive cleanup of links, images, brackets
        txt = _ias_re18.sub(r'!\[.*?\]\(.*?\)', '', txt)
        txt = _ias_re18.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', txt)
        txt = _ias_re18.sub(r'\[\]', '', txt)
        txt = _ias_re18.sub(r'\[', '', txt)
        txt = _ias_re18.sub(r'\]', '', txt)
        txt = _ias_re18.sub(r'#+\s*', '', txt)
        txt = _ias_re18.sub(r'\*+', '', txt)

        # Drop obvious junk lines
        junk_kw = ['advertisement','skip to','sign in','subscribe','watch live',
                   'listen live','follow us','read more','related topics',
                   'more from','share this','trending','cookie','privacy policy',
                   'terms of use','download the app','weather','temperature',
                   'aqi','caqi','pm2.5','pm10','humidity','wind speed',
                   'newsindia','navwap','navwas','desktop','spotlight']
        clean_paras = []
        for ln in txt.split('\n'):
            s = ln.strip()
            if len(s) < 60: continue
            sl = s.lower()
            if any(j in sl for j in junk_kw): continue
            # Skip lines that are mostly punctuation/numbers (nav junk)
            alpha = sum(c.isalpha() for c in s)
            if alpha < len(s) * 0.6: continue
            clean_paras.append(s)
            if len(' '.join(clean_paras)) > max_chars * 1.5: break

        body = ' '.join(clean_paras)
        body = _ias_re18.sub(r'\s+', ' ', body).strip()
        # Cut at sentence boundary near max_chars
        if len(body) > max_chars:
            cut = body[:max_chars]
            last_dot = cut.rfind('. ')
            if last_dot > max_chars * 0.6:
                body = cut[:last_dot+1]
            else:
                body = cut + '…'
        return body
    except Exception as e:
        print(f'[jina18] {str(e)[:80]}')
        return ''

_ias_prev_gen18 = _lazy_generate_section

def _lazy_generate_section(paper, section):
    fetched = _ias_fetch_section_feeds(section.name, max_items=10)
    if not fetched:
        return _ias_prev_gen18(paper, section)

    existing = set()
    try:
        rows = PaperArticle.query.join(PaperSection, PaperArticle.section_id == PaperSection.id)\
                .filter(PaperSection.paper_id == paper.id).all()
        for pa in rows: existing.add((pa.title or '')[:80].lower())
    except Exception: pass
    filtered = [a for a in fetched if a['title'][:80].lower() not in existing] or fetched

    saved = 0
    target = 4  # 4 short items per section
    for art in filtered[:target + 3]:
        if saved >= target: break
        try:
            # Try jina for real full-text paragraph
            body = _ias_jina_clean18(art['link'], max_chars=1100)
            has_body = len(body) > 250
            if not has_body:
                # Use RSS snippet
                body = (art['summary'] or '').strip()
                if len(body) < 60:
                    body = art['title']

            # If jina gave real text, save AS-IS (no AI). Otherwise ask AI for a short brief.
            if has_body:
                # Trim to ~100-120 words (roughly 700 chars) at sentence boundary
                if len(body) > 800:
                    cut = body[:800]
                    d = cut.rfind('. ')
                    body = cut[:d+1] if d > 400 else cut + '…'
                summary = body
                gs = ''
                rel = 7
            else:
                try:
                    system = ("UPSC editor. Return ONLY JSON: "
                              '{"summary":"...","gs_paper":"GS2","relevance":7}. '
                              "Write 90-110 words in 2 short paragraphs: P1 event, "
                              "P2 UPSC angle. NEVER invent facts.")
                    user = f"SECTION: {section.name}\nHEADLINE: {art['title']}\nSNIPPET: {body[:400]}\nWrite."
                    content = _lazy_call_any_ai(system, user, max_tokens=500)
                    content = content.strip().strip('`').replace('```json','').replace('```','').strip()
                    if content.startswith('json'): content = content[4:].strip()
                    data = _lazy_json.loads(content)
                    summary = data.get('summary','').strip() or body
                    gs = data.get('gs_paper','')
                    rel = data.get('relevance',7)
                except Exception:
                    summary = body
                    gs = ''
                    rel = 6

            db.session.add(PaperArticle(
                section_id=section.id, title=art['title'][:300], summary=summary,
                source=art['source'], url=art['link'],
                gs_paper=gs, relevance=rel))
            saved += 1
            _ias_time18.sleep(2.0)
        except Exception as e:
            print(f'[gen18] {section.name}: {str(e)[:100]}')
            try: db.session.rollback()
            except Exception: pass

    try:
        cnt = PaperArticle.query.filter_by(section_id=section.id).count()
    except Exception:
        cnt = saved
    section.status = 'ready' if cnt > 0 else 'pending'
    db.session.commit()
    return saved

print('[patch18] short-real-news engine active (4 per section, no-AI when jina works)')

# ============ PATCH 19A: Book stream route + offline status ============
from flask import Response as _R19, request as _rq19, jsonify as _json19
from werkzeug.http import parse_range_header as _pr19

@app.route('/book/<int:book_id>/stream')
def book_stream(book_id):
    """Stream PDF from B2 with proper headers so Service Worker can cache it.
    Supports Range requests so PDF viewer can seek without full download."""
    book = Book.query.get_or_404(book_id)
    if not book.filename:
        return 'No file', 404

    # Resolve bytes
    data = None
    if book.filename.startswith('b2://'):
        try:
            remote = _b2_remote_from_url(book.filename)
            data = _b2_download_bytes(remote)
        except Exception as e:
            return f'B2 error: {str(e)[:120]}', 502
    else:
        import os as _os19
        path = _os19.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), book.filename)
        if not _os19.path.exists(path):
            return 'File missing', 404
        with open(path, 'rb') as f:
            data = f.read()

    total = len(data)
    rng = _rq19.headers.get('Range')
    accept = _rq19.headers.get('Accept', '')
    inline = 'application/pdf' in accept or 'inline' in accept

    headers = {
        'Content-Type': 'application/pdf',
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=86400',
    }
    if not inline:
        safe = (book.title or f'book-{book_id}').replace('"', '')[:60]
        headers['Content-Disposition'] = f'attachment; filename="{safe}.pdf"'

    if rng:
        pr = _pr19(rng)
        if pr and pr.ranges:
            start, end = pr.ranges[0]
            end = min(end if end is not None else total - 1, total - 1)
            if start >= total:
                return Response(b'', 416, headers=dict(headers, **{'Content-Range': f'bytes */{total}'}))
            chunk = data[start:end+1]
            headers['Content-Range'] = f'bytes {start}-{end}/{total}'
            headers['Content-Length'] = str(len(chunk))
            return Response(chunk, 206, headers=headers)

    headers['Content-Length'] = str(total)
    return Response(data, 200, headers=headers)


@app.route('/offline/status')
def offline_status():
    """Diagnostic — shows what the SW/IndexedDB thinks it has."""
    try:
        total_books = Book.query.count()
    except Exception:
        total_books = -1
    return _json19({
        'ok': True,
        'total_books_in_db': total_books,
        'note': 'Client-side cache status is in /offline page (uses IndexedDB)',
    })


print('[patch19a] /book/<id>/stream and /offline/status registered')

# ============ PATCH 19C: Real _b2_download_bytes + safe stream ============
def _b2_download_bytes(remote):
    """Download bytes from a b2sdk remote object or (bucket, filename) tuple.
    Handles multiple b2sdk versions."""
    # Case A: remote is a File object (has download())
    if hasattr(remote, 'download'):
        try:
            downloaded = remote.download()
            # b2sdk v2 DownloadedFile has save_bytes()
            if hasattr(downloaded, 'save_bytes'):
                return downloaded.save_bytes()
            if hasattr(downloaded, 'save'):
                import io as _io19c
                buf = _io19c.BytesIO()
                downloaded.save(buf)
                return buf.getvalue()
        except Exception as e:
            print(f'[b2dl] remote.download failed: {str(e)[:120]}')

    # Case B: (bucket, filename) tuple
    if isinstance(remote, (tuple, list)) and len(remote) == 2:
        bucket, fname = remote
        try:
            dl = bucket.download_file_by_name(fname)
            if hasattr(dl, 'save_bytes'):
                return dl.save_bytes()
            import io as _io19c
            buf = _io19c.BytesIO()
            dl.save(buf)
            return buf.getvalue()
        except Exception as e:
            print(f'[b2dl] bucket download failed: {str(e)[:120]}')

    # Case C: raw bytes (shouldn't happen)
    if isinstance(remote, (bytes, bytearray)):
        return bytes(remote)

    raise RuntimeError(f'Cannot download from remote type: {type(remote).__name__}')


# Redefine the stream route with try/except around download
# # @app.route('/book/<int:book_id>/stream')
def _book_stream_v2(book_id):
    book = Book.query.get_or_404(book_id)
    if not book.filename:
        return 'No file', 404

    data = None
    try:
        if book.filename.startswith('b2://'):
            remote = _b2_remote_from_url(book.filename)
            data = _b2_download_bytes(remote)
        else:
            import os as _os19c
            path = _os19c.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), book.filename)
            if not _os19c.path.exists(path):
                return f'File missing on server: {book.filename}', 404
            with open(path, 'rb') as f:
                data = f.read()
    except Exception as e:
        import traceback as _tb
        print('[stream] error:', _tb.format_exc()[:800])
        return f'Download failed: {str(e)[:200]}', 502

    total = len(data)
    from flask import Response as _R, request as _rq, make_response
    from werkzeug.http import parse_range_header as _pr
    rng = _rq.headers.get('Range')
    accept = _rq.headers.get('Accept', '')
    inline = 'application/pdf' in accept

    headers = {
        'Content-Type': 'application/pdf',
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=86400',
    }
    safe = (book.title or f'book-{book_id}').replace('"', '')[:60].replace('\n',' ')
    headers['Content-Disposition'] = ('inline; ' if inline else 'attachment; ') + f'filename="{safe}.pdf"'

    if rng:
        pr = _pr(rng)
        if pr and pr.ranges:
            start, end = pr.ranges[0]
            end = min(end if end is not None else total - 1, total - 1)
            if start >= total:
                return _R(b'', 416, headers=dict(headers, **{'Content-Range': f'bytes */{total}'}))
            chunk = data[start:end+1]
            headers['Content-Range'] = f'bytes {start}-{end}/{total}'
            headers['Content-Length'] = str(len(chunk))
            return _R(chunk, 206, headers=headers)

    headers['Content-Length'] = str(total)
    return _R(data, 200, headers=headers)


# Also add a light /book/<id>/meta route so client can check size without downloading
@app.route('/book/<int:book_id>/meta')
def book_meta(book_id):
    book = Book.query.get_or_404(book_id)
    out = {'id': book_id, 'title': book.title,
           'filename': book.filename}
    # Size only if local
    if book.filename and not book.filename.startswith('b2://'):
        import os as _os_m
        p = _os_m.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), book.filename)
        if _os_m.path.exists(p):
            out['size'] = _os_m.path.getsize(p)
    return out


print('[patch19c] _b2_download_bytes + hardened stream route active')

# ============ PATCH 19D: Use new stream function + safe hooks ============
try:
    if '_book_stream_v2' in globals():
        app.view_functions['book_stream'] = globals()['_book_stream_v2']
        print('[patch19d] book_stream overridden with v2 (B2 download fixed)')
    else:
        print('[patch19d] WARNING: _book_stream_v2 not found')
except Exception as _e:
    import sys; print('[patch19d] override err:', _e, file=sys.stderr)

print('[patch19d] app loaded OK')

# ============ PATCH 19D: Use new stream function + safe hooks ============
try:
    if '_book_stream_v2' in globals():
        app.view_functions['book_stream'] = globals()['_book_stream_v2']
        print('[patch19d] book_stream overridden with v2 (B2 download fixed)')
    else:
        print('[patch19d] WARNING: _book_stream_v2 not found')
except Exception as _e:
    import sys; print('[patch19d] override err:', _e, file=sys.stderr)

print('[patch19d] app loaded OK')

# ============ PATCH 19E: Fix _b2_download_bytes for string URLs ============
def _b2_download_bytes(remote):
    """Handle b2sdk File objects, (bucket, fname) tuples, AND string URLs."""
    import re as _re19e

    # Case 1: string URL — parse and fetch
    if isinstance(remote, str):
        # b2://bucket/path/to/file.pdf
        m = _re19e.match(r'b2://([^/]+)/(.+)', remote)
        if m:
            bucket_name, fname = m.group(1), m.group(2)
            try:
                bkt, api = _b2_connect()
                if bkt:
                    dl = bkt.download_file_by_name(fname)
                    if hasattr(dl, 'save_bytes'):
                        return dl.save_bytes()
                    import io as _io19e
                    buf = _io19e.BytesIO()
                    dl.save(buf)
                    return buf.getvalue()
            except Exception as e:
                print(f'[b2dl] api download failed for {fname[:60]}: {str(e)[:150]}')

        # https://f000.backblazeb2.com/file/bucket/fname  (public bucket)
        if remote.startswith('http://') or remote.startswith('https://'):
            import requests as _rq19e
            try:
                r = _rq19e.get(remote, timeout=60, stream=True)
                if r.status_code == 200:
                    return r.content
                print(f'[b2dl] http fetch status {r.status_code} {remote[:80]}')
            except Exception as e:
                print(f'[b2dl] http err: {str(e)[:120]}')

        raise RuntimeError(f'Cannot resolve B2 URL: {remote[:120]}')

    # Case 2: File object with download()
    if hasattr(remote, 'download'):
        try:
            downloaded = remote.download()
            if hasattr(downloaded, 'save_bytes'):
                return downloaded.save_bytes()
            if hasattr(downloaded, 'save'):
                import io as _io19e
                buf = _io19e.BytesIO()
                downloaded.save(buf)
                return buf.getvalue()
        except Exception as e:
            print(f'[b2dl] object download failed: {str(e)[:120]}')

    # Case 3: (bucket, filename) tuple
    if isinstance(remote, (tuple, list)) and len(remote) == 2:
        bucket, fname = remote
        try:
            dl = bucket.download_file_by_name(fname)
            if hasattr(dl, 'save_bytes'):
                return dl.save_bytes()
            import io as _io19e
            buf = _io19e.BytesIO()
            dl.save(buf)
            return buf.getvalue()
        except Exception as e:
            print(f'[b2dl] tuple download failed: {str(e)[:120]}')

    # Case 4: raw bytes
    if isinstance(remote, (bytes, bytearray)):
        return bytes(remote)

    raise RuntimeError(f'Cannot download from remote type: {type(remote).__name__}')

# Rebind in stream route
try:
    import sys as _sys19e
    _this = _sys19e.modules[__name__]
    if hasattr(_this, '_book_stream_v2'):
        # Rebuild route v3 using current function
        @app.route('/book/<int:book_id>/stream2')
        def book_stream_v3(book_id):
            from flask import Response as _R, request as _rq, make_response
            from werkzeug.http import parse_range_header as _pr
            book = Book.query.get_or_404(book_id)
            if not book.filename:
                return 'No file', 404
            try:
                if book.filename.startswith('b2://'):
                    remote = _b2_remote_from_url(book.filename)
                    data = _b2_download_bytes(remote)
                else:
                    import os as _os19e
                    path = _os19e.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), book.filename)
                    if not _os19e.path.exists(path):
                        return f'File missing: {book.filename}', 404
                    with open(path, 'rb') as f:
                        data = f.read()
            except Exception as e:
                import traceback as _tb
                print('[stream] error:', _tb.format_exc()[:600])
                return f'Download failed: {str(e)[:200]}', 502
            total = len(data)
            headers = {
                'Content-Type': 'application/pdf',
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'public, max-age=86400',
            }
            safe = (book.title or f'book-{book_id}').replace('"', '')[:60].replace('\n', ' ')
            inline = 'application/pdf' in _rq.headers.get('Accept', '')
            headers['Content-Disposition'] = ('inline; ' if inline else 'attachment; ') + f'filename="{safe}.pdf"'
            rng = _rq.headers.get('Range')
            if rng:
                pr = _pr(rng)
                if pr and pr.ranges:
                    s, e = pr.ranges[0]
                    e = min(e if e is not None else total - 1, total - 1)
                    if s >= total:
                        return _R(b'', 416, headers=dict(headers, **{'Content-Range': f'bytes */{total}'}))
                    chunk = data[s:e+1]
                    headers['Content-Range'] = f'bytes {s}-{e}/{total}'
                    headers['Content-Length'] = str(len(chunk))
                    return _R(chunk, 206, headers=headers)
            headers['Content-Length'] = str(total)
            return _R(data, 200, headers=headers)

        # Override the ORIGINAL endpoint with v3 logic
        app.view_functions['book_stream'] = book_stream_v3
        print('[patch19e] book_stream upgraded to v3 (string URL support)')
except Exception as _e:
    import sys; print('[patch19e] override err:', _e, file=sys.stderr)

print('[patch19e] B2 string-URL handler active')

# ============ PATCH 19F: Bare filename = B2 key ============
def _b2_download_bytes(remote):
    """Handle: bare keys like 'books/x.pdf', b2:// URLs, https URLs,
    File objects, (bucket, fname) tuples, raw bytes."""
    import re as _re19f
    import sys as _sys19f

    # Case 1: string — bare key, b2://, or http(s)
    if isinstance(remote, str):
        # Strip b2://bucket/ prefix if present
        if remote.startswith('b2://'):
            m = _re19f.match(r'b2://([^/]+)/(.+)', remote)
            key = m.group(2) if m else remote
        elif remote.startswith('http://') or remote.startswith('https://'):
            # Direct HTTP fetch
            import requests as _rq
            try:
                r = _rq.get(remote, timeout=90)
                if r.status_code == 200:
                    return r.content
                raise RuntimeError(f'HTTP {r.status_code}')
            except Exception as e:
                print(f'[b2dl] http err: {str(e)[:150]}')
                raise
        else:
            # Bare key like 'books/Indian_politiy.pdf'
            key = remote

        # Download by name from B2
        try:
            bkt, api = _b2_connect()
            if bkt is None:
                raise RuntimeError('B2 connect returned None')
            dl = bkt.download_file_by_name(key)
            if hasattr(dl, 'save_bytes'):
                return dl.save_bytes()
            import io as _io
            buf = _io.BytesIO()
            dl.save(buf)
            return buf.getvalue()
        except Exception as e:
            print(f'[b2dl] key download failed for {key[:80]}: {str(e)[:180]}')
            # Try with 'books/' prefix variations
            for alt in [key, key.lstrip('/'), f'books/{key}' if not key.startswith('books/') else None]:
                if not alt or alt == key: continue
                try:
                    dl = bkt.download_file_by_name(alt)
                    if hasattr(dl, 'save_bytes'):
                        return dl.save_bytes()
                except Exception:
                    continue
            raise

    # Case 2: File object with download()
    if hasattr(remote, 'download'):
        downloaded = remote.download()
        if hasattr(downloaded, 'save_bytes'):
            return downloaded.save_bytes()
        if hasattr(downloaded, 'save'):
            import io as _io
            buf = _io.BytesIO()
            downloaded.save(buf)
            return buf.getvalue()

    # Case 3: (bucket, filename) tuple
    if isinstance(remote, (tuple, list)) and len(remote) == 2:
        bucket, fname = remote
        dl = bucket.download_file_by_name(fname)
        if hasattr(dl, 'save_bytes'):
            return dl.save_bytes()
        import io as _io
        buf = _io.BytesIO()
        dl.save(buf)
        return buf.getvalue()

    # Case 4: raw bytes
    if isinstance(remote, (bytes, bytearray)):
        return bytes(remote)

    raise RuntimeError(f'Unsupported remote type: {type(remote).__name__}')

# Simplify stream route: ALWAYS try B2 first if filename looks like a key
_ias_fb_stream = None
try:
    _ias_fb_stream = app.view_functions.get('book_stream')
except Exception:
    pass

@app.route('/book/<int:book_id>/stream3')
def book_stream_v4(book_id):
    from flask import Response as _R, request as _rq
    from werkzeug.http import parse_range_header as _pr
    import os as _os
    book = Book.query.get_or_404(book_id)
    if not book.filename:
        return 'No file', 404

    data = None
    errs = []
    fn = book.filename

    # Try local file first
    if not fn.startswith('b2://') and not fn.startswith('http'):
        local = _os.path.join(app.config.get('UPLOAD_FOLDER', 'uploads'), fn)
        if _os.path.exists(local):
            with open(local, 'rb') as f:
                data = f.read()

    # Fall back to B2 (treat as key)
    if data is None:
        try:
            data = _b2_download_bytes(fn)
        except Exception as e:
            errs.append(f'B2: {str(e)[:150]}')

    if data is None:
        return f'Download failed. {"; ".join(errs)}', 502

    total = len(data)
    headers = {
        'Content-Type': 'application/pdf',
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'public, max-age=86400',
    }
    safe = (book.title or f'book-{book_id}').replace('"', '')[:60].replace('\n', ' ')
    inline = 'application/pdf' in _rq.headers.get('Accept', '')
    headers['Content-Disposition'] = ('inline; ' if inline else 'attachment; ') + f'filename="{safe}.pdf"'

    rng = _rq.headers.get('Range')
    if rng:
        pr = _pr(rng)
        if pr and pr.ranges:
            s, e = pr.ranges[0]
            e = min(e if e is not None else total - 1, total - 1)
            if s >= total:
                return _R(b'', 416, headers=dict(headers, **{'Content-Range': f'bytes */{total}'}))
            chunk = data[s:e+1]
            headers['Content-Range'] = f'bytes {s}-{e}/{total}'
            headers['Content-Length'] = str(len(chunk))
            return _R(chunk, 206, headers=headers)

    headers['Content-Length'] = str(total)
    return _R(data, 200, headers=headers)

# Override the canonical endpoint
app.view_functions['book_stream'] = book_stream_v4
print('[patch19f] book_stream v4 active — bare key = B2 object')

# ============ CATEGORY SYSTEM PATCH ============
# Extend LIBRARY_COLLECTIONS with the 5 requested categories
try:
    _new_cats = {
        'NCERT':   {'label': '📗 NCERT',   'icon': '📗'},
        'UPSC':    {'label': '🎯 UPSC',    'icon': '🎯'},
        'BANKING': {'label': '🏦 Banking', 'icon': '🏦'},
        'SSC':     {'label': '📘 SSC',     'icon': '📘'},
        'OTHER':   {'label': '📁 Other',   'icon': '📁'},
    }
    for k, v in _new_cats.items():
        if k not in LIBRARY_COLLECTIONS:
            LIBRARY_COLLECTIONS[k] = v
    print('[cats] LIBRARY_COLLECTIONS now:', list(LIBRARY_COLLECTIONS.keys()))
except Exception as e:
    print('[cats] extend err:', e)


def _ias_classify_book(book):
    """Auto-assign collection based on title/author keywords."""
    t = ((book.title or '') + ' ' + (book.author or '')).lower()
    if 'ncert' in t:
        return 'NCERT'
    if any(k in t for k in ['ssc', 'cgl', 'chsl', 'mts', 'staff selection']):
        return 'SSC'
    if any(k in t for k in ['bank', 'ibps', 'sbi', 'rbi', 'po ', 'clerk', 'rrb']):
        return 'BANKING'
    if any(k in t for k in ['upsc', 'ias', 'civil service', 'prelims', 'mains',
                             'gs ', 'general studies', 'polity', 'modern history',
                             'geography', 'economy', 'ethics', 'optional']):
        return 'UPSC'
    return 'OTHER'


@app.route('/library/categorize', methods=['GET', 'POST'])
def library_categorize():
    from flask import jsonify
    changed = 0
    skipped = 0
    try:
        books = Book.query.all()
        for b in books:
            current = (b.collection or '').upper().strip()
            # Keep existing valid ones; only reclassify blanks / unknown
            if current and current in LIBRARY_COLLECTIONS:
                skipped += 1
                continue
            new_cat = _ias_classify_book(b)
            if b.collection != new_cat:
                b.collection = new_cat
                changed += 1
        db.session.commit()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500
    return jsonify({'ok': True, 'changed': changed, 'skipped': skipped,
                    'total': Book.query.count()})


@app.route('/library/recategorize-all', methods=['POST'])
def library_recategorize_all():
    """Force re-classify ALL books (ignores existing)."""
    from flask import jsonify
    changed = 0
    for b in Book.query.all():
        new_cat = _ias_classify_book(b)
        if b.collection != new_cat:
            b.collection = new_cat
            changed += 1
    db.session.commit()
    return jsonify({'ok': True, 'changed': changed, 'total': Book.query.count()})


print('[cats] /library/categorize + /library/recategorize-all routes added')

# ============ SUBCATEGORY TILE SYSTEM ============
import re as _ias_re_tile

def _ias_subcat(book):
    """Return a subcategory label for a book based on title/collection."""
    t = ((book.title or '') + ' ' + (book.author or '')).lower().strip()
    cat = (book.collection or 'OTHER').upper()

    if cat == 'NCERT':
        # Look for explicit class number
        m = _ias_re_tile.search(r'class[\s_-]*(\d{1,2})', t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 12:
                return f'Class {n}'
        # NCERT code like lehs201, legy101, leph102
        m = _ias_re_tile.search(r'\ble[a-z]{2}(\d)', t)
        if m:
            d = int(m.group(1))
            if d == 1: return 'Class 11'
            if d == 2: return 'Class 12'
        # Just a number at the start of a code like '201', '102'
        m = _ias_re_tile.search(r'(\d{1,2})', t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 12:
                return f'Class {n}'
        return 'Other'

    if cat == 'UPSC':
        rules = [
            (['polity','laxmikanth','constitution'], 'Polity'),
            (['modern history','spectrum','ancient','medieval','art and culture','culture'], 'History'),
            (['geography','gc leong','atlas','map'], 'Geography'),
            (['economy','ramesh singh','budget','economic survey'], 'Economy'),
            (['environment','ecology','climate','shankar ias'], 'Environment'),
            (['ethics','integrity','aptitude','lexicon'], 'Ethics'),
            (['essay'], 'Essay'),
            (['optional','psir','sociology','anthropology','pub adm','public admin'], 'Optional'),
            (['current affairs','current'], 'Current Affairs'),
            (['prelims','csat'], 'Prelims'),
            (['mains','answer writing'], 'Mains'),
            (['science and tech','science & tech'], 'Science & Tech'),
            (['international','ir '], 'International Relations'),
            (['governance','polity and governance'], 'Governance'),
            (['social','society'], 'Society'),
        ]
        for keys, label in rules:
            if any(k in t for k in keys):
                return label
        return 'General'

    if cat == 'SSC':
        for key, label in [('cgl','CGL'),('chsl','CHSL'),('mts','MTS'),
                            ('gd','GD'),('steno','Steno'),('si ','SI')]:
            if key in t: return label
        return 'General'

    if cat == 'BANKING':
        for key, label in [('ibps','IBPS'),('sbi','SBI'),('rbi','RBI'),
                            ('po ','PO'),('clerk','Clerk'),('nabard','NABARD')]:
            if key in t: return label
        return 'General'

    # OTHER
    for key, label in [('past paper','Past Papers'),('pyq','Past Papers'),
                        ('previous year','Past Papers'),
                        ('magazine','Magazine'),('yojana','Magazine'),('kurukshetra','Magazine'),
                        ('note','Notes'),('current affairs','Current Affairs'),
                        ('answer key','Answer Key'),('coaching','Coaching')]:
        if key in t: return label
    return 'Other'


def _ias_natural_sort(label):
    m = _ias_re_tile.search(r'(\d+)', label)
    return (m and int(m.group(1)) or 999, label)


@app.route('/library/c/<cat>')
def library_cat(cat):
    """Tile grid showing subcategories inside one category."""
    cat = cat.upper()
    if cat not in LIBRARY_COLLECTIONS:
        cat = 'OTHER'
    books = Book.query.filter_by(collection=cat).all()
    groups = {}
    for b in books:
        groups.setdefault(_ias_subcat(b), []).append(b.id)
    subs = sorted(groups.keys(), key=_ias_natural_sort)
    counts = {k: len(v) for k, v in groups.items()}
    return render_template('library_cat.html',
                           cat=cat, subcategories=subs,
                           counts=counts, total=len(books),
                           collections=LIBRARY_COLLECTIONS)


@app.route('/library/c/<cat>/<sub>')
def library_cat_sub(cat, sub):
    """Book list for one subcategory."""
    cat = cat.upper()
    if cat not in LIBRARY_COLLECTIONS:
        cat = 'OTHER'
    books = [b for b in Book.query.filter_by(collection=cat).all()
             if _ias_subcat(b) == sub]
    return render_template('index.html',
                           books=books,
                           collections=LIBRARY_COLLECTIONS,
                           collection_counts={cat: len(books)},
                           total_count=len(books),
                           years=[], subjects=[])


print('[tiles] /library/c/<cat> and /library/c/<cat>/<sub> registered')

# ============ PATCH: Home = features + tile, Library = separate ============
def _ias_home():
    from flask import render_template as _rt
    return _rt('home.html')

try:
    # Override /library's view to stay library_view
    # Override / to render new home.html
    app.view_functions['index'] = _ias_home
    print('[patch-home] / now renders home.html')
except Exception as _e:
    import sys; print('[patch-home] error:', _e, file=sys.stderr)

# ============ BOOK ZONE ============
BOOKZONE_CATS = {
    'UPSC':       {'label': 'UPSC',        'icon': '🎯', 'color': '#5b6bd4'},
    'SSC':        {'label': 'SSC',         'icon': '📘', 'color': '#e05555'},
    'BANKING':    {'label': 'Banking',     'icon': '🏦', 'color': '#e89b3a'},
    'RAILWAY':    {'label': 'Railway',     'icon': '🚂', 'color': '#3fa87a'},
    'TEACHING':   {'label': 'Teaching',    'icon': '📚', 'color': '#9b59b6'},
    'ADVOCATE':   {'label': 'Advocate',    'icon': '⚖️', 'color': '#3498db'},
    'ENGINEERING':{'label': 'Engineering', 'icon': '⚙️', 'color': '#e67e22'},
    'MEDICAL':    {'label': 'Medical',     'icon': '🩺', 'color': '#1abc9c'},
    'STATE_PSC':  {'label': 'State PSC',   'icon': '🏛️', 'color': '#e74c3c'},
    'DEFENCE':    {'label': 'Defence',     'icon': '🎖️', 'color': '#f39c12'},
    'RESEARCH':   {'label': 'Research',    'icon': '🔬', 'color': '#8e44ad'},
    'OTHER':      {'label': 'Other',       'icon': '📁', 'color': '#95a5a6'},
}

try:
    @app.route('/bookzone')
    def bookzone_home():
        from flask import render_template as _rt
        counts = {k: Book.query.filter_by(collection=k).count() for k in BOOKZONE_CATS}
        return _rt('bookzone.html', cats=BOOKZONE_CATS, counts=counts,
                   total=sum(counts.values()))

    @app.route('/bookzone/c/<cat>')
    def bookzone_cat(cat):
        from flask import render_template as _rt
        cat = cat.upper()
        if cat not in BOOKZONE_CATS: cat = 'OTHER'
        books = Book.query.filter_by(collection=cat).order_by(Book.uploaded_at.desc()).all()
        return _rt('bookzone_cat.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                   cats=BOOKZONE_CATS, books=books)

    @app.route('/bookzone/pick/<cat>')
    def bookzone_pick(cat):
        from flask import render_template as _rt
        cat = cat.upper()
        if cat not in BOOKZONE_CATS: cat = 'OTHER'
        books = Book.query.order_by(Book.uploaded_at.desc()).all()
        return _rt('bookzone_pick.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                   cats=BOOKZONE_CATS, books=books)

    @app.route('/bookzone/assign', methods=['POST'])
    def bookzone_assign():
        from flask import request as _rq, redirect as _rd, url_for as _uf
        cat = (_rq.form.get('cat') or 'OTHER').upper()
        if cat not in BOOKZONE_CATS: cat = 'OTHER'
        ids = _rq.form.getlist('book_ids')
        n = 0
        for bid in ids:
            try:
                b = Book.query.get(int(bid))
                if b and b.collection != cat:
                    b.collection = cat; n += 1
            except Exception: pass
        db.session.commit()
        return _rd(_uf('bookzone_cat', cat=cat))

    @app.route('/bookzone/unassign/<int:book_id>', methods=['POST'])
    def bookzone_unassign(book_id):
        from flask import redirect as _rd, url_for as _uf
        b = Book.query.get_or_404(book_id)
        b.collection = 'OTHER'
        db.session.commit()
        return _rd(_uf('bookzone_home'))

    print('[bookzone] 12 categories + 5 routes registered')
except Exception as _e:
    import sys; print('[bookzone] error:', _e, file=sys.stderr)

# ============ BOOKZONE v2: full library features inside Book Zone ============
from flask import render_template as _rt_v2, request as _rq_v2

def _bookzone_cat_v2(cat):
    """Render index.html (full library) with books filtered to one category.
    Reuses every existing feature: Read, Save, Info, Download, Move, Delete,
    Year filter, Subject filter, Upload form."""
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS:
        cat = 'OTHER'

    year_f = (_rq_v2.args.get('year') or '').strip()
    subj_f = (_rq_v2.args.get('subject') or '').strip()

    q = Book.query.filter(Book.collection == cat)
    if year_f:
        try: q = q.filter(Book.year == int(year_f))
        except ValueError: pass
    if subj_f:
        q = q.filter(Book.subject == subj_f)

    books = q.order_by(Book.uploaded_at.desc()).limit(500).all()

    years = sorted(
        [y[0] for y in db.session.query(Book.year)
         .filter(Book.collection == cat).distinct().all() if y[0]],
        reverse=True)
    subjects = sorted(
        [s[0] for s in db.session.query(Book.subject)
         .filter(Book.collection == cat).distinct().all() if s[0]])

    single = {cat: BOOKZONE_CATS[cat]}
    counts = {cat: len(books)}

    return _rt_v2('index.html',
                  books=books,
                  collections=single,
                  collection_counts=counts,
                  total_count=len(books),
                  years=years,
                  subjects=subjects)

# Override the original bookzone_cat with v2
try:
    app.view_functions['bookzone_cat'] = _bookzone_cat_v2
    print('[bookzone-v2] bookzone_cat upgraded to full library view')
except Exception as _e:
    import sys; print('[bookzone-v2] error:', _e, file=sys.stderr)


# Inject a "← Book Zone" back bar when inside /bookzone/c/*
try:
    @app.after_request
    def _bz_back_bar(resp):
        from flask import request as _rq_bz
        if not _rq_bz.path.startswith('/bookzone/c/'):
            return resp
        if resp.mimetype != 'text/html':
            return resp
        try:
            html = resp.get_data(as_text=True)
        except Exception:
            return resp
        if 'bz-back-bar' in html:
            return resp
        cat = _rq_bz.path.split('/')[-1]
        bar = (
            '<a id="bz-back-bar" href="/bookzone" style="display:block;'
            'margin:10px 14px 0;padding:10px 14px;background:#fff;'
            'color:#c0392b;text-decoration:none;border-radius:10px;'
            'font-family:Georgia,serif;font-size:14px;font-weight:600;'
            'box-shadow:0 2px 8px rgba(0,0,0,0.08);'
            'border-left:4px solid #c0392b;">'
            '← Book Zone &nbsp;<span style="color:#888;font-weight:400;">· ' + cat + '</span>'
            '</a>'
        )
        # Insert just after <body ...>
        import re as _re_bz
        m = _re_bz.search(r'<body[^>]*>', html)
        if m:
            html = html[:m.end()] + bar + html[m.end():]
            resp.set_data(html)
        return resp
    print('[bookzone-v2] back bar hook registered')
except Exception as _e:
    import sys; print('[bookzone-v2] back-bar error:', _e, file=sys.stderr)

print('[bookzone-v2] done')

# ============ BOOKZONE v3: Sub-tiles + Year/Paper drill-down ============
import re as _re_v3
from flask import render_template as _rt_v3

def _bz_classify(b):
    """Return dict: subcat, year, paper."""
    t = ((b.title or '') + ' ' + (b.author or '')).lower()
    # Paper detection
    paper = 'Other'
    rules = [
        (['essay'], 'Essay'),
        (['gs4','gs 4','paper iv','paper 4','ethics','integrity'], 'GS4'),
        (['gs3','gs 3','paper iii','paper 3'], 'GS3'),
        (['gs2','gs 2','paper ii','paper 2'], 'GS2'),
        (['gs1','gs 1','paper i','paper 1'], 'GS1'),
        (['csat','aptitude'], 'CSAT'),
        (['prelims','preliminary'], 'Prelims'),
        (['optional'], 'Optional'),
        (['compulsory'], 'Compulsory'),
    ]
    for keys, label in rules:
        if any(k in t for k in keys):
            paper = label
            break

    # Year — from field first, else title
    year = b.year
    if not year:
        m = _re_v3.search(r'\b(19[89]\d|20[0-4]\d)\b', b.title or '')
        if m:
            try: year = int(m.group(0))
            except ValueError: pass

    # Subcat
    if 'ncert' in t or (b.title or '').lower().startswith('le'):
        return {'subcat': 'ncert', 'year': year, 'paper': paper}
    if year:
        return {'subcat': 'pyq', 'year': year, 'paper': paper}
    return {'subcat': 'standard', 'year': None, 'paper': paper}


def _bz_library_view(cat, books):
    """Reuse index.html with these books."""
    years = sorted({b.year for b in books if b.year}, reverse=True)
    subjects = sorted({b.subject for b in books if b.subject})
    return _rt_v3('index.html',
                  books=books,
                  collections={cat: BOOKZONE_CATS.get(cat, {'label': cat, 'icon': '📁', 'color': '#888'})},
                  collection_counts={cat: len(books)},
                  total_count=len(books),
                  years=years,
                  subjects=subjects)


# -------- Override /bookzone/c/<cat> → subcategory tiles --------
def _bz_cat_tiles(cat):
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'
    books = Book.query.filter_by(collection=cat).all()
    buckets = {'standard': [], 'ncert': [], 'pyq': []}
    for b in books:
        cls = _bz_classify(b)
        buckets[cls['subcat']].append(b)

    tiles = [
        {'key': 'all',      'label': 'All Books',      'icon': '📚', 'color': '#5b6bd4', 'count': len(books)},
        {'key': 'standard', 'label': 'Standard Books', 'icon': '📕', 'color': '#c0392b', 'count': len(buckets['standard'])},
        {'key': 'ncert',    'label': 'NCERT',          'icon': '📗', 'color': '#27ae60', 'count': len(buckets['ncert'])},
        {'key': 'pyq',      'label': 'PYQ (Year-wise)','icon': '📄', 'color': '#e67e22', 'count': len(buckets['pyq'])},
    ]
    return _rt_v3('bookzone_sub.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                  tiles=tiles, total=len(books))


# -------- Subcategory entry --------
def _bz_sub(cat, sub):
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'
    books = Book.query.filter_by(collection=cat).all()

    if sub == 'all':
        return _bz_library_view(cat, books)

    if sub == 'standard':
        want = [b for b in books if _bz_classify(b)['subcat'] == 'standard']
        return _bz_library_view(cat, want)

    if sub == 'ncert':
        want = [b for b in books if _bz_classify(b)['subcat'] == 'ncert']
        return _bz_library_view(cat, want)

    if sub == 'pyq':
        # Group PYQ books by year
        years = {}
        for b in books:
            c = _bz_classify(b)
            if c['subcat'] != 'pyq' or not c['year']: continue
            years.setdefault(c['year'], 0)
            years[c['year']] += 1
        sorted_years = sorted(years.keys(), reverse=True)
        tiles = [{'key': str(y), 'label': f'{y}', 'icon': '📅',
                  'color': '#e67e22', 'count': years[y]} for y in sorted_years]
        return _rt_v3('bookzone_sub.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                      tiles=tiles, total=sum(years.values()),
                      header=f'{cat} · PYQ Year-wise', back_url=f'/bookzone/c/{cat}')

    return _bz_library_view(cat, books)


# -------- Year → papers --------
def _bz_year(cat, year):
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'
    try: yr = int(year)
    except ValueError: yr = 0

    books = Book.query.filter_by(collection=cat).all()
    papers = {}
    for b in books:
        c = _bz_classify(b)
        if c['subcat'] != 'pyq' or c['year'] != yr: continue
        p = c['paper'] or 'Other'
        papers.setdefault(p, 0)
        papers[p] += 1

    order = ['Prelims','CSAT','GS1','GS2','GS3','GS4','Essay','Optional','Compulsory','Other']
    sorted_papers = [p for p in order if p in papers] + [p for p in papers if p not in order]
    icons = {'Prelims':'📋','CSAT':'🧮','GS1':'📘','GS2':'📙','GS3':'📗','GS4':'📕',
             'Essay':'✍️','Optional':'🎯','Compulsory':'📎','Other':'📄'}
    tiles = [{'key': p.lower().replace(' ','_'), 'label': p,
              'icon': icons.get(p,'📄'), 'color': '#3498db',
              'count': papers[p]} for p in sorted_papers]

    return _rt_v3('bookzone_sub.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                  tiles=tiles, total=sum(papers.values()),
                  header=f'{cat} · {yr} Papers',
                  back_url=f'/bookzone/c/{cat}/pyq')


# -------- Paper → books --------
def _bz_paper(cat, year, paper):
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'
    try: yr = int(year)
    except ValueError: yr = 0

    want_paper = paper.lower().replace('_', ' ')
    books = Book.query.filter_by(collection=cat).all()
    out = []
    for b in books:
        c = _bz_classify(b)
        if c['subcat'] != 'pyq' or c['year'] != yr: continue
        if (c['paper'] or '').lower() == want_paper:
            out.append(b)
    return _bz_library_view(cat, out)


# -------- Register / override routes --------
try:
    app.view_functions['bookzone_cat'] = _bz_cat_tiles

    @app.route('/bookzone/c/<cat>/<sub>')
    def bookzone_sub(cat, sub):
        return _bz_sub(cat, sub)

    @app.route('/bookzone/c/<cat>/pyq/<year>')
    def bookzone_year(cat, year):
        return _bz_year(cat, year)

    @app.route('/bookzone/c/<cat>/pyq/<year>/<paper>')
    def bookzone_paper(cat, year, paper):
        return _bz_paper(cat, year, paper)

    print('[bookzone-v3] sub + year + paper routes registered')
except Exception as _e:
    import sys; print('[bookzone-v3] error:', _e, file=sys.stderr)

# ============ BOOKZONE v4: NCERT class tiles + route ============
import re as _re_v4
from flask import render_template as _rt_v4

def _bz_ncert_tiles(cat):
    """Show Class 1-12 tiles inside a Book Zone category."""
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'
    books = Book.query.filter_by(collection=cat).all()

    # Group NCERT books by class number
    by_class = {n: 0 for n in range(1, 13)}
    other = 0
    for b in books:
        c = _bz_classify(b)
        if c['subcat'] != 'ncert':
            continue
        t = (b.title or '').lower()
        m = _re_v4.search(r'class[\s_-]*(\d{1,2})', t)
        if not m:
            m = _re_v4.search(r'\ble[a-z]{2}(\d)', t)
            if m:
                d = int(m.group(1))
                cls = 11 if d == 1 else 12 if d == 2 else None
                if cls: by_class[cls] += 1
                else: other += 1
                continue
        if m:
            n = int(m.group(1))
            if 1 <= n <= 12: by_class[n] += 1
            else: other += 1
        else:
            other += 1

    colors = ['#5b6bd4','#e05555','#e89b3a','#3fa87a','#9b59b6','#3498db',
              '#e67e22','#1abc9c','#e74c3c','#f39c12','#8e44ad','#2ecc71']
    tiles = []
    for n in range(1, 13):
        tiles.append({'key': f'class_{n}', 'label': f'Class {n}',
                      'icon': str(n), 'color': colors[(n-1) % 12],
                      'count': by_class[n]})
    if other:
        tiles.append({'key': 'other_ncert', 'label': 'Other NCERT',
                      'icon': '📘', 'color': '#888', 'count': other})
    return _rt_v4('bookzone_sub.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                  tiles=tiles, total=sum(by_class.values()) + other,
                  header=f'{cat} · NCERT Class-wise',
                  back_url=f'/bookzone/c/{cat}')


def _bz_ncert_class(cat, cls):
    """Books for a given NCERT class inside a Book Zone category."""
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'
    books = Book.query.filter_by(collection=cat).all()
    out = []
    for b in books:
        c = _bz_classify(b)
        if c['subcat'] != 'ncert': continue
        t = (b.title or '').lower()
        if cls.startswith('class_'):
            want = int(cls.replace('class_',''))
            m = _re_v4.search(r'class[\s_-]*(\d{1,2})', t)
            if not m:
                m2 = _re_v4.search(r'\ble[a-z]{2}(\d)', t)
                if m2:
                    d = int(m2.group(1))
                    got = 11 if d==1 else 12 if d==2 else None
                    if got == want: out.append(b)
                continue
            if int(m.group(1)) == want: out.append(b)
        elif cls == 'other_ncert':
            m = _re_v4.search(r'class[\s_-]*(\d{1,2})', t)
            m2 = _re_v4.search(r'\ble[a-z]{2}(\d)', t)
            if not m and not m2: out.append(b)
    return _bz_library_view(cat, out)


# ---------- Override _bz_sub for 'ncert' → class tiles ----------
_orig_bz_sub = None
try:
    # We can't easily call the original; reimplement ncert branch cleanly
    def _bz_sub_v4(cat, sub):
        if sub == 'ncert':
            return _bz_ncert_tiles(cat)
        # For everything else, reuse the previous function by importing it via closure
        # Since we overrode it earlier, rebuild minimal logic:
        cat2 = (cat or 'OTHER').upper()
        if cat2 not in BOOKZONE_CATS: cat2 = 'OTHER'
        books = Book.query.filter_by(collection=cat2).all()
        if sub == 'all':
            return _bz_library_view(cat2, books)
        if sub == 'standard':
            want = [b for b in books if _bz_classify(b)['subcat'] == 'standard']
            return _bz_library_view(cat2, want)
        if sub == 'pyq':
            years = {}
            for b in books:
                c = _bz_classify(b)
                if c['subcat'] != 'pyq' or not c['year']: continue
                years.setdefault(c['year'], 0); years[c['year']] += 1
            sorted_years = sorted(years.keys(), reverse=True)
            tiles = [{'key': str(y), 'label': f'{y}', 'icon': '📅',
                      'color': '#e67e22', 'count': years[y]} for y in sorted_years]
            return _rt_v4('bookzone_sub.html', cat=cat2, cat_info=BOOKZONE_CATS[cat2],
                          tiles=tiles, total=sum(years.values()),
                          header=f'{cat2} · PYQ Year-wise',
                          back_url=f'/bookzone/c/{cat2}')
        return _bz_library_view(cat2, books)

    app.view_functions['bookzone_sub'] = _bz_sub_v4

    @app.route('/bookzone/c/<cat>/ncert/<cls>')
    def bookzone_ncert_class(cat, cls):
        return _bz_ncert_class(cat, cls)

    print('[bookzone-v4] NCERT class tiles registered')
except Exception as _e:
    import sys; print('[bookzone-v4] error:', _e, file=sys.stderr)


# ============ BOOKZONE v5: add NCERT + STANDARD + PYQ as top categories ============
try:
    BOOKZONE_CATS.update({
        'NCERT':    {'label': 'NCERT',     'icon': '📗', 'color': '#27ae60'},
        'STANDARD': {'label': 'Standard',  'icon': '📕', 'color': '#c0392b'},
        'PYQ':      {'label': 'PYQ',       'icon': '📄', 'color': '#e67e22'},
    })
    print('[bookzone-v5] NCERT + STANDARD + PYQ added to Book Zone')
except Exception as _e:
    import sys; print('[bookzone-v5] error:', _e, file=sys.stderr)

# ============ BOOKZONE v5b: NCERT category shows class tiles directly ============
_bz_cat_tiles_v3 = None
try:
    _bz_cat_tiles_v3 = app.view_functions.get('bookzone_cat')
except Exception:
    pass

def _bz_cat_tiles_v5(cat):
    """If cat is NCERT, show class tiles directly. Otherwise show 4 sub-tiles."""
    from flask import render_template as _rt_v5
    cat = (cat or 'OTHER').upper()
    if cat not in BOOKZONE_CATS: cat = 'OTHER'

    if cat == 'NCERT':
        # Direct class tiles
        import re as _re_v5
        books = Book.query.filter_by(collection='NCERT').all()
        by_class = {n: 0 for n in range(1, 13)}
        other = 0
        for b in books:
            t = (b.title or '').lower()
            m = _re_v5.search(r'class[\s_-]*(\d{1,2})', t)
            if not m:
                m = _re_v5.search(r'\ble[a-z]{2}(\d)', t)
                if m:
                    d = int(m.group(1))
                    cls = 11 if d == 1 else 12 if d == 2 else None
                    if cls: by_class[cls] += 1
                    else: other += 1
                    continue
            if m:
                n = int(m.group(1))
                if 1 <= n <= 12: by_class[n] += 1
                else: other += 1
            else:
                other += 1
        colors = ['#5b6bd4','#e05555','#e89b3a','#3fa87a','#9b59b6','#3498db',
                  '#e67e22','#1abc9c','#e74c3c','#f39c12','#8e44ad','#2ecc71']
        tiles = []
        for n in range(1, 13):
            tiles.append({'key': f'class_{n}', 'label': f'Class {n}',
                          'icon': str(n), 'color': colors[(n-1) % 12],
                          'count': by_class[n]})
        if other:
            tiles.append({'key': 'other_ncert', 'label': 'Other NCERT',
                          'icon': '📘', 'color': '#888', 'count': other})
        return _rt_v5('bookzone_sub.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                      tiles=tiles, total=len(books),
                      header=f'NCERT · Class-wise',
                      back_url='/bookzone')

    # For other categories, fall back to the sub-tile view
    if _bz_cat_tiles_v3:
        return _bz_cat_tiles_v3(cat)
    return _rt_v5('bookzone_sub.html', cat=cat, cat_info=BOOKZONE_CATS[cat],
                  tiles=[], total=0, header=BOOKZONE_CATS[cat]['label'],
                  back_url='/bookzone')

try:
    app.view_functions['bookzone_cat'] = _bz_cat_tiles_v5
    print('[bookzone-v5b] NCERT category → direct class tiles')
except Exception as _e:
    import sys; print('[bookzone-v5b] error:', _e, file=sys.stderr)

# ============ NCERT Class → Subject tiles ============
import re as _re_ns
from flask import render_template as _rt_ns

NCERT_SUBJECTS = {
    'maths':      {'label': 'Mathematics',        'icon': '📐', 'color': '#5b6bd4'},
    'physics':    {'label': 'Physics',            'icon': '⚛️', 'color': '#e05555'},
    'chemistry':  {'label': 'Chemistry',          'icon': '🧪', 'color': '#e89b3a'},
    'biology':    {'label': 'Biology',            'icon': '🧬', 'color': '#3fa87a'},
    'science':    {'label': 'Science',            'icon': '🔬', 'color': '#1abc9c'},
    'english':    {'label': 'English',            'icon': '🔤', 'color': '#9b59b6'},
    'hindi':      {'label': 'Hindi',              'icon': '🇮🇳', 'color': '#e67e22'},
    'sanskrit':   {'label': 'Sanskrit',           'icon': '📜', 'color': '#8e44ad'},
    'history':    {'label': 'History',            'icon': '🏛️', 'color': '#c0392b'},
    'geography':  {'label': 'Geography',          'icon': '🌍', 'color': '#3498db'},
    'polity':     {'label': 'Political Science',  'icon': '⚖️', 'color': '#2ecc71'},
    'economics':  {'label': 'Economics',          'icon': '💹', 'color': '#f39c12'},
    'sociology':  {'label': 'Sociology',          'icon': '👥', 'color': '#e74c3c'},
    'psychology': {'label': 'Psychology',         'icon': '🧠', 'color': '#16a085'},
    'accountancy':{'label': 'Accountancy',        'icon': '🧾', 'color': '#95a5a6'},
    'business':   {'label': 'Business Studies',   'icon': '💼', 'color': '#7f8c8d'},
    'social':     {'label': 'Social Science',     'icon': '👨‍👩‍👧', 'color': '#d35400'},
    'evs':        {'label': 'EVS',                'icon': '🌱', 'color': '#27ae60'},
    'other':      {'label': 'Other',              'icon': '📘', 'color': '#888'},
}

def _ncert_subject_of(book):
    t = ((book.title or '') + ' ' + (book.subject or '')).lower()
    rules = [
        (['social science','sst'], 'social'),
        (['mathematic','maths','ganit'], 'maths'),
        (['physics','bhautik'], 'physics'),
        (['chemistry','rasayan'], 'chemistry'),
        (['biology','jiv'], 'biology'),
        (['science'], 'science'),
        (['english'], 'english'),
        (['hindi'], 'hindi'),
        (['sanskrit'], 'sanskrit'),
        (['history','itihas'], 'history'),
        (['geography','bhugol'], 'geography'),
        (['political','polity','civics','nagrik'], 'polity'),
        (['economic','arth'], 'economics'),
        (['sociology','samaj'], 'sociology'),
        (['psychology','mano'], 'psychology'),
        (['accountancy','account'], 'accountancy'),
        (['business'], 'business'),
        (['evs','environment'], 'evs'),
    ]
    for keys, key in rules:
        if any(k in t for k in keys): return key
    return 'other'

def _ncert_class_of(book):
    t = (book.title or '').lower()
    m = _re_ns.search(r'class[\s_-]*(\d{1,2})', t)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 12: return n
    m = _re_ns.search(r'\ble[a-z]{2}(\d)', t)
    if m:
        d = int(m.group(1))
        return 11 if d == 1 else 12 if d == 2 else None
    return None


def _bookzone_ncert_class_subj(cat, cls):
    """Show subject tiles for one NCERT class."""
    cat = (cat or 'NCERT').upper()
    try:
        want = int(cls.replace('class_',''))
    except ValueError:
        want = 0

    books = Book.query.filter_by(collection='NCERT').all()
    in_class = [b for b in books if _ncert_class_of(b) == want]

    # Count by subject
    counts = {}
    for b in in_class:
        s = _ncert_subject_of(b)
        counts[s] = counts.get(s, 0) + 1

    tiles = []
    for key, info in NCERT_SUBJECTS.items():
        n = counts.get(key, 0)
        if n == 0: continue
        tiles.append({'key': key, 'label': info['label'], 'icon': info['icon'],
                      'color': info['color'], 'count': n})
    tiles.sort(key=lambda t: -t['count'])

    return _rt_ns('bookzone_sub.html', cat=cat,
                  cat_info=BOOKZONE_CATS.get(cat, {'label': cat, 'icon': '📗', 'color': '#27ae60'}),
                  tiles=tiles, total=len(in_class),
                  header=f'NCERT · Class {want} · Subjects',
                  back_url='/bookzone/c/NCERT')


def _bookzone_ncert_class_subject(cat, cls, subject):
    """Show books for NCERT class + subject."""
    try:
        want = int(cls.replace('class_',''))
    except ValueError:
        want = 0
    books = Book.query.filter_by(collection='NCERT').all()
    out = [b for b in books
           if _ncert_class_of(b) == want and _ncert_subject_of(b) == subject]
    return _bz_library_view('NCERT', out)


try:
    app.view_functions['bookzone_ncert_class'] = _bookzone_ncert_class_subj

    @app.route('/bookzone/c/<cat>/ncert/<cls>/<subject>')
    def bookzone_ncert_subj(cat, cls, subject):
        return _bookzone_ncert_class_subject(cat, cls, subject)

    print('[ncert-subj] class → subject tiles registered')
except Exception as _e:
    import sys; print('[ncert-subj] error:', _e, file=sys.stderr)

# ============ NCERT subject-tile ROUTING FIX ============
# Override bookzone_sub so /bookzone/c/NCERT/class_12 → subject tiles
_prev_bz_sub_v6 = app.view_functions.get('bookzone_sub')

def _bookzone_ncert_class_subj_v6(cat, cls):
    """Subject tiles for one NCERT class. Keys include full path so
    template's /bookzone/c/{{cat}}/{{t.key}} builds the right URL."""
    cat_up = (cat or 'NCERT').upper()
    try:
        want = int(cls.replace('class_', ''))
    except ValueError:
        want = 0
    books = Book.query.filter_by(collection='NCERT').all()
    in_class = [b for b in books if _ncert_class_of(b) == want]

    counts = {}
    for b in in_class:
        s = _ncert_subject_of(b)
        counts[s] = counts.get(s, 0) + 1

    tiles = []
    for key, info in NCERT_SUBJECTS.items():
        n = counts.get(key, 0)
        tiles.append({'key': f'ncert/{cls}/{key}',
                      'label': info['label'], 'icon': info['icon'],
                      'color': info['color'], 'count': n})
    # Sort: subjects with books first, then alphabetical
    tiles.sort(key=lambda t: (-t['count'], t['label']))

    return _rt_ns('bookzone_sub.html', cat=cat_up,
                  cat_info=BOOKZONE_CATS.get('NCERT', {'label': 'NCERT', 'icon': '📗', 'color': '#27ae60'}),
                  tiles=tiles, total=len(in_class),
                  header=f'NCERT · Class {want} · Subjects',
                  back_url='/bookzone/c/NCERT')


def _bz_sub_v6(cat, sub):
    cat_up = (cat or 'OTHER').upper()

    # NCERT class tile → subject tiles
    if cat_up == 'NCERT' and sub.startswith('class_'):
        return _bookzone_ncert_class_subj_v6(cat_up, sub)

    # Other NCERT → books with no class detected
    if cat_up == 'NCERT' and sub == 'other_ncert':
        books = Book.query.filter_by(collection='NCERT').all()
        out = [b for b in books if _ncert_class_of(b) is None]
        return _bz_library_view('NCERT', out)

    # Everything else falls through to previous handler
    if _prev_bz_sub_v6:
        return _prev_bz_sub_v6(cat, sub)
    return _bz_library_view(cat_up, Book.query.filter_by(collection=cat_up).all())

try:
    app.view_functions['bookzone_sub'] = _bz_sub_v6
    print('[ncert-fix] class_* → subject tiles wired')
except Exception as _e:
    import sys; print('[ncert-fix] error:', _e, file=sys.stderr)


# Fix the "bookzone_ncert_class" endpoint too — it needs to render subject tiles
try:
    app.view_functions['bookzone_ncert_class'] = _bookzone_ncert_class_subj_v6
    print('[ncert-fix] bookzone_ncert_class → subject tiles wired')
except Exception as _e:
    import sys; print('[ncert-fix] class endpoint error:', _e, file=sys.stderr)

# ============ PYQ Paper-wise tiles ============
def _bz_paper_tiles(cat):
    """Paper-type tiles for a Book Zone category."""
    cat_up = (cat or 'OTHER').upper()
    if cat_up not in BOOKZONE_CATS: cat_up = 'OTHER'
    books = Book.query.filter_by(collection=cat_up).all()

    counts = {}
    for b in books:
        c = _bz_classify(b)
        p = c.get('paper') or 'Other'
        counts[p] = counts.get(p, 0) + 1

    order = ['Prelims','CSAT','GS1','GS2','GS3','GS4','Essay','Optional','Compulsory','Other']
    icons = {'Prelims':'📋','CSAT':'🧮','GS1':'📘','GS2':'📙','GS3':'📗','GS4':'📕',
             'Essay':'✍️','Optional':'🎯','Compulsory':'📎','Other':'📄'}
    colors = {'Prelims':'#3498db','CSAT':'#1abc9c','GS1':'#e74c3c','GS2':'#e67e22',
              'GS3':'#27ae60','GS4':'#9b59b6','Essay':'#f39c12','Optional':'#8e44ad',
              'Compulsory':'#95a5a6','Other':'#888'}

    tiles = []
    for p in order:
        tiles.append({
            'key': f'paperwise/{p.lower()}',
            'label': p,
            'icon': icons.get(p, '📄'),
            'color': colors.get(p, '#888'),
            'count': counts.get(p, 0),
        })

    return _rt_v4('bookzone_sub.html', cat=cat_up, cat_info=BOOKZONE_CATS[cat_up],
                  tiles=tiles, total=len(books),
                  header=f'{cat_up} · Paper-wise',
                  back_url=f'/bookzone/c/{cat_up}')


def _bz_paper_books(cat, paper):
    """Books of one paper type across all years."""
    cat_up = (cat or 'OTHER').upper()
    if cat_up not in BOOKZONE_CATS: cat_up = 'OTHER'
    want = paper.lower().replace('_', ' ')
    books = Book.query.filter_by(collection=cat_up).all()
    out = []
    known = ['prelims','csat','gs1','gs2','gs3','gs4','essay','optional','compulsory']
    for b in books:
        c = _bz_classify(b)
        p = (c.get('paper') or 'Other').lower()
        if want == 'other':
            if p not in known: out.append(b)
        else:
            if p == want: out.append(b)
    return _bz_library_view(cat_up, out)


# --- New tile view: add Paper-wise tile to each category ---
def _bz_cat_tiles_v7(cat):
    from flask import render_template as _rt_v7
    import re as _re_v7
    cat_up = (cat or 'OTHER').upper()
    if cat_up not in BOOKZONE_CATS: cat_up = 'OTHER'

    # NCERT: direct class tiles
    if cat_up == 'NCERT':
        books = Book.query.filter_by(collection='NCERT').all()
        by_class = {n: 0 for n in range(1, 13)}
        other = 0
        for b in books:
            t = (b.title or '').lower()
            m = _re_v7.search(r'class[\s_-]*(\d{1,2})', t)
            if not m:
                m = _re_v7.search(r'\ble[a-z]{2}(\d)', t)
                if m:
                    d = int(m.group(1))
                    cls = 11 if d == 1 else 12 if d == 2 else None
                    if cls: by_class[cls] += 1
                    else: other += 1
                    continue
            if m:
                n = int(m.group(1))
                if 1 <= n <= 12: by_class[n] += 1
                else: other += 1
            else:
                other += 1
        colors = ['#5b6bd4','#e05555','#e89b3a','#3fa87a','#9b59b6','#3498db',
                  '#e67e22','#1abc9c','#e74c3c','#f39c12','#8e44ad','#2ecc71']
        tiles = [{'key': f'class_{n}', 'label': f'Class {n}', 'icon': str(n),
                  'color': colors[(n-1) % 12], 'count': by_class[n]} for n in range(1, 13)]
        if other:
            tiles.append({'key': 'other_ncert', 'label': 'Other NCERT',
                          'icon': '📘', 'color': '#888', 'count': other})
        return _rt_v7('bookzone_sub.html', cat=cat_up, cat_info=BOOKZONE_CATS[cat_up],
                      tiles=tiles, total=len(books),
                      header='NCERT · Class-wise', back_url='/bookzone')

    # Other categories: All / Standard / NCERT / PYQ / Paper-wise
    books = Book.query.filter_by(collection=cat_up).all()
    buckets = {'standard': [], 'ncert': [], 'pyq': []}
    for b in books:
        c = _bz_classify(b)
        buckets[c['subcat']].append(b)

    paper_count = 0
    for b in books:
        c = _bz_classify(b)
        if c.get('paper') and c['paper'] != 'Other':
            paper_count += 1

    tiles = [
        {'key': 'all',       'label': 'All Books',      'icon': '📚', 'color': '#5b6bd4', 'count': len(books)},
        {'key': 'standard',  'label': 'Standard Books', 'icon': '📕', 'color': '#c0392b', 'count': len(buckets['standard'])},
        {'key': 'ncert',     'label': 'NCERT',          'icon': '📗', 'color': '#27ae60', 'count': len(buckets['ncert'])},
        {'key': 'pyq',       'label': 'PYQ (Year-wise)','icon': '📄', 'color': '#e67e22', 'count': len(buckets['pyq'])},
        {'key': 'paperwise', 'label': 'Paper-wise',     'icon': '📑', 'color': '#8e44ad', 'count': paper_count},
    ]
    return _rt_v7('bookzone_sub.html', cat=cat_up, cat_info=BOOKZONE_CATS[cat_up],
                  tiles=tiles, total=len(books),
                  header=f'{cat_up} · Sub-sections', back_url='/bookzone')


# --- Sub-router: handles /bookzone/c/<cat>/<sub> for 'paperwise' etc ---
_prev_bz_sub_pw = app.view_functions.get('bookzone_sub')

def _bz_sub_v7(cat, sub):
    cat_up = (cat or 'OTHER').upper()
    if cat_up not in BOOKZONE_CATS: cat_up = 'OTHER'

    if sub == 'paperwise':
        return _bz_paper_tiles(cat_up)

    if _prev_bz_sub_pw:
        return _prev_bz_sub_pw(cat, sub)
    return _bz_library_view(cat_up, Book.query.filter_by(collection=cat_up).all())


try:
    app.view_functions['bookzone_cat'] = _bz_cat_tiles_v7
    app.view_functions['bookzone_sub'] = _bz_sub_v7

    @app.route('/bookzone/c/<cat>/paperwise/<paper>')
    def bookzone_paperwise_paper(cat, paper):
        return _bz_paper_books(cat, paper)

    print('[paperwise] tiles + route wired')
except Exception as _e:
    import sys; print('[paperwise] error:', _e, file=sys.stderr)

# ============ PythonAnywhere RENEWAL REMINDER ============
import json as _json_rn
import os as _os_rn
from datetime import datetime as _dt_rn, timedelta as _td_rn

RENEWAL_FILE = _os_rn.path.expanduser('~/ias_machine/.pa_renewal.json')
PA_WEBAPPS_URL = 'https://www.pythonanywhere.com/user/umadivy500/webapps/'
PA_DASHBOARD_URL = 'https://www.pythonanywhere.com/user/umadivy500/'

def _rn_load():
    try:
        with open(RENEWAL_FILE) as f:
            return _json_rn.load(f)
    except Exception:
        return {'last_renewed': None}

def _rn_save(d):
    try:
        with open(RENEWAL_FILE, 'w') as f:
            _json_rn.dump(d, f)
    except Exception: pass

def _rn_status():
    d = _rn_load()
    last = d.get('last_renewed')
    if not last:
        return {'days_left': None, 'last': None, 'warn': True, 'critical': True}
    try:
        last_dt = _dt_rn.strptime(last, '%Y-%m-%d')
    except Exception:
        return {'days_left': None, 'last': last, 'warn': True, 'critical': True}
    # PythonAnywhere free tier: 30 days from renewal
    next_due = last_dt + _td_rn(days=30)
    days_left = (next_due - _dt_rn.utcnow()).days
    return {
        'days_left': days_left,
        'last': last,
        'next_due': next_due.strftime('%Y-%m-%d'),
        'warn': days_left <= 7,
        'critical': days_left <= 2,
    }

@app.route('/renewal')
def renewal_page():
    from flask import render_template as _rt_rn
    return _rt_rn('renewal.html', status=_rn_status(),
                  pa_url=PA_WEBAPPS_URL, pa_dash=PA_DASHBOARD_URL)

@app.route('/renewal/mark', methods=['POST'])
def renewal_mark():
    from flask import redirect as _rd, url_for as _uf
    _rn_save({'last_renewed': _dt_rn.utcnow().strftime('%Y-%m-%d')})
    return _rd('/renewal')

@app.route('/renewal/status')
def renewal_status():
    from flask import jsonify as _jf_rn
    return _jf_rn(_rn_status())

# Inject a top banner on EVERY page when renewal is due soon
try:
    @app.after_request
    def _rn_banner(resp):
        from flask import request as _rq_rn
        if resp.mimetype != 'text/html': return resp
        try:
            html = resp.get_data(as_text=True)
        except Exception:
            return resp
        if 'rn-banner' in html: return resp
        st = _rn_status()
        dl = st.get('days_left')
        if dl is None or dl > 7: return resp
        color = '#c0392b' if st['critical'] else '#e67e22'
        label = f"⚠️ App will pause in {dl} days — tap to renew" if dl > 0 else "⚠️ Renewal overdue — tap now"
        banner = (
            f'<div id="rn-banner" style="position:fixed;top:0;left:0;right:0;z-index:99999;'
            f'background:{color};color:#fff;text-align:center;padding:10px 12px;'
            f'font-family:system-ui,sans-serif;font-size:13px;font-weight:600;'
            f'box-shadow:0 2px 8px rgba(0,0,0,0.25);">'
            f'<a href="/renewal" style="color:#fff;text-decoration:none;">{label} →</a>'
            f'</div>'
        )
        import re as _re_rn
        m = _re_rn.search(r'<body[^>]*>', html)
        if m:
            html = html[:m.end()] + banner + html[m.end():]
            resp.set_data(html)
        return resp
    print('[renewal] banner hook registered')
except Exception as _e:
    import sys; print('[renewal] banner error:', _e, file=sys.stderr)

print('[renewal] routes registered')

# ============ HOME RENEWAL TILE ============
_prev_ias_home = app.view_functions.get('index')

def _ias_home_v2():
    from flask import render_template as _rt_hr
    return _rt_hr('home.html', renewal=_rn_status())

try:
    app.view_functions['index'] = _ias_home_v2
    print('[home-renew] / now passes renewal status to home.html')
except Exception as _e:
    import sys; print('[home-renew] error:', _e, file=sys.stderr)

# ============ STUDY TOOLKIT ROUTE ============
try:
    @app.route('/toolkit')
    def study_toolkit():
        from flask import render_template as _rt_tk
        return _rt_tk('toolkit.html')
    print('[toolkit] /toolkit route registered')
except Exception as _e:
    import sys; print('[toolkit] error:', _e, file=sys.stderr)

# ============ STUDY TOOLKIT ROUTE ============
try:
    @app.route('/toolkit')
    def study_toolkit():
        from flask import render_template as _rt_tk
        return _rt_tk('toolkit.html')
    print('[toolkit] /toolkit route registered')
except Exception as _e:
    import sys; print('[toolkit] error:', _e, file=sys.stderr)

# ============ STUDY TOOLKIT ROUTE ============
try:
    @app.route('/toolkit')
    def study_toolkit():
        from flask import render_template as _rt_tk
        return _rt_tk('toolkit.html')
    print('[toolkit] /toolkit route registered')
except Exception as _e:
    import sys; print('[toolkit] error:', _e, file=sys.stderr)

# ============ STUDY TOOLKIT ROUTE ============
try:
    @app.route('/toolkit')
    def study_toolkit():
        from flask import render_template as _rt_tk
        return _rt_tk('toolkit.html')
    print('[toolkit] /toolkit route registered')
except Exception as _e:
    import sys; print('[toolkit] error:', _e, file=sys.stderr)

# ============ TOOLKIT REFERENCE DATA ============
TOOLKIT_DATA = {
  'constants': [
    {'cat':'Physics', 'name':'Speed of light (c)', 'val':'2.998 × 10⁸ m/s'},
    {'cat':'Physics', 'name':'Planck constant (h)', 'val':'6.626 × 10⁻³⁴ J·s'},
    {'cat':'Physics', 'name':'Gravitational constant (G)', 'val':'6.674 × 10⁻¹¹ N·m²/kg²'},
    {'cat':'Physics', 'name':'Boltzmann constant (k)', 'val':'1.381 × 10⁻²³ J/K'},
    {'cat':'Physics', 'name':'Avogadro number (Nₐ)', 'val':'6.022 × 10²³ /mol'},
    {'cat':'Physics', 'name':'Gas constant (R)', 'val':'8.314 J/(mol·K)'},
    {'cat':'Physics', 'name':'Elementary charge (e)', 'val':'1.602 × 10⁻¹⁹ C'},
    {'cat':'Physics', 'name':'Electron mass (mₑ)', 'val':'9.109 × 10⁻³¹ kg'},
    {'cat':'Physics', 'name':'Proton mass (mₚ)', 'val':'1.673 × 10⁻²⁷ kg'},
    {'cat':'Physics', 'name':'Acceleration due to gravity (g)', 'val':'9.81 m/s²'},
    {'cat':'Physics', 'name':'Standard atmospheric pressure', 'val':'1.013 × 10⁵ Pa'},
    {'cat':'Physics', 'name':'Absolute zero', 'val':'-273.15 °C = 0 K'},
    {'cat':'Physics', 'name':'Stefan-Boltzmann constant (σ)', 'val':'5.670 × 10⁻⁸ W/(m²·K⁴)'},
    {'cat':'Physics', 'name':'Rydberg constant (R∞)', 'val':'1.097 × 10⁷ /m'},
    {'cat':'Physics', 'name':'Bohr radius (a₀)', 'val':'5.291 × 10⁻¹¹ m'},
    {'cat':'Physics', 'name':'Faraday constant (F)', 'val':'96,485 C/mol'},
    {'cat':'Chemistry', 'name':'Atomic mass unit (u)', 'val':'1.660 × 10⁻²⁷ kg'},
    {'cat':'Chemistry', 'name':'Molar volume (STP)', 'val':'22.4 L/mol'},
    {'cat':'Chemistry', 'name':'Water density (4°C)', 'val':'1,000 kg/m³'},
    {'cat':'Chemistry', 'name':'pH of pure water (25°C)', 'val':'7.00'},
    {'cat':'Chemistry', 'name':'Kw of water (25°C)', 'val':'1.0 × 10⁻¹⁴'},
    {'cat':'Chemistry', 'name':'1 mole = molecules', 'val':'6.022 × 10²³'},
    {'cat':'Maths', 'name':'π (pi)', 'val':'3.14159265...'},
    {'cat':'Maths', 'name':'e (Euler)', 'val':'2.71828182...'},
    {'cat':'Maths', 'name':'Golden ratio (φ)', 'val':'1.61803398...'},
    {'cat':'Maths', 'name':'√2', 'val':'1.41421356...'},
    {'cat':'Maths', 'name':'√3', 'val':'1.73205080...'},
    {'cat':'Maths', 'name':'ln(2)', 'val':'0.693147...'},
    {'cat':'Economics', 'name':'Repo rate (RBI, 2024)', 'val':'6.50%'},
    {'cat':'Economics', 'name':'CRR (RBI)', 'val':'4.50%'},
    {'cat':'Economics', 'name':'SLR', 'val':'18.00%'},
    {'cat':'Economics', 'name':'Base year CPI', 'val':'2012'},
    {'cat':'Economics', 'name':'Base year GDP (new series)', 'val':'2011-12'},
    {'cat':'Environment', 'name':'CO₂ safe level (ppm)', 'val':'350 ppm'},
    {'cat':'Environment', 'name':'Current CO₂ (2024)', 'val':'~420 ppm'},
    {'cat':'Environment', 'name':'Pre-industrial CO₂', 'val':'280 ppm'},
    {'cat':'Environment', 'name':'India forest cover (2021)', 'val':'24.62%'},
  ],
  'formulas': [
    {'cat':'Physics', 'name':'Newton II', 'f':'F = m × a'},
    {'cat':'Physics', 'name':'Kinetic energy', 'f':'KE = ½ m v²'},
    {'cat':'Physics', 'name':'Potential energy', 'f':'PE = m g h'},
    {'cat':'Physics', 'name':'Einstein mass-energy', 'f':'E = m c²'},
    {'cat':'Physics', 'name':'Ohm\'s law', 'f':'V = I × R'},
    {'cat':'Physics', 'name':'Power', 'f':'P = V × I'},
    {'cat':'Physics', 'name':'Wave speed', 'f':'v = f × λ'},
    {'cat':'Physics', 'name':'Gravitation', 'f':'F = G m₁ m₂ / r²'},
    {'cat':'Physics', 'name':'Escape velocity', 'f':'vₑ = √(2 g R)'},
    {'cat':'Physics', 'name':'Centripetal force', 'f':'F = m v² / r'},
    {'cat':'Physics', 'name':'Snell\'s law', 'f':'n₁ sin θ₁ = n₂ sin θ₂'},
    {'cat':'Physics', 'name':'Lens formula', 'f':'1/v − 1/u = 1/f'},
    {'cat':'Physics', 'name':'Work', 'f':'W = F × d × cos θ'},
    {'cat':'Physics', 'name':'Momentum', 'f':'p = m v'},
    {'cat':'Physics', 'name':'Ideal gas law', 'f':'P V = n R T'},
    {'cat':'Chemistry', 'name':'Moles', 'f':'n = mass / molar mass'},
    {'cat':'Chemistry', 'name':'Dilution', 'f':'M₁ V₁ = M₂ V₂'},
    {'cat':'Chemistry', 'name':'Ideal gas (density)', 'f':'d = P M / R T'},
    {'cat':'Chemistry', 'name':'pH', 'f':'pH = −log[H⁺]'},
    {'cat':'Chemistry', 'name':'Boyle\'s law', 'f':'P₁ V₁ = P₂ V₂ (T const)'},
    {'cat':'Chemistry', 'name':'Charles law', 'f':'V₁/T₁ = V₂/T₂ (P const)'},
    {'cat':'Maths', 'name':'Quadratic roots', 'f':'x = (−b ± √(b²−4ac)) / 2a'},
    {'cat':'Maths', 'name':'Pythagoras', 'f':'a² + b² = c²'},
    {'cat':'Maths', 'name':'Circle area', 'f':'A = π r²'},
    {'cat':'Maths', 'name':'Sphere volume', 'f':'V = (4/3) π r³'},
    {'cat':'Maths', 'name':'Cylinder volume', 'f':'V = π r² h'},
    {'cat':'Maths', 'name':'Cone volume', 'f':'V = (1/3) π r² h'},
    {'cat':'Maths', 'name':'Simple interest', 'f':'SI = P R T / 100'},
    {'cat':'Maths', 'name':'Compound interest', 'f':'A = P (1 + R/100)ᵀ'},
    {'cat':'Maths', 'name':'Sin²θ + Cos²θ', 'f':'1'},
    {'cat':'Economics', 'name':'GDP', 'f':'C + I + G + (X − M)'},
    {'cat':'Economics', 'name':'Inflation rate', 'f':'((CPIₜ − CPIₜ₋₁)/CPIₜ₋₁) × 100'},
    {'cat':'Economics', 'name':'Money multiplier', 'f':'1 / CRR'},
    {'cat':'Economics', 'name':'Fisher equation', 'f':'MV = PT'},
    {'cat':'Economics', 'name':'Gini coefficient', 'f':'0 (equal) to 1 (unequal)'},
    {'cat':'Environment', 'name':'Carbon footprint', 'f':'= activity × emission factor'},
    {'cat':'Environment', 'name':'Population density', 'f':'Population / Area'},
    {'cat':'Environment', 'name':'Doubling time', 'f':'70 / growth rate %'},
  ],
  'scientists': [
    {'name':'Isaac Newton', 'field':'Physics · Maths', 'discover':'Laws of motion, universal gravitation, calculus'},
    {'name':'Albert Einstein', 'field':'Physics', 'discover':'Relativity, E = mc², photoelectric effect'},
    {'name':'Marie Curie', 'field':'Physics · Chemistry', 'discover':'Radioactivity, radium, polonium · 2 Nobel prizes'},
    {'name':'C.V. Raman', 'field':'Physics', 'discover':'Raman effect (1928) · Nobel 1930'},
    {'name':'Homi Bhabha', 'field':'Physics', 'discover':'Father of Indian nuclear programme'},
    {'name':'Vikram Sarabhai', 'field':'Physics', 'discover':'Father of Indian space programme, ISRO'},
    {'name':'A.P.J. Abdul Kalam', 'field':'Aerospace', 'discover':'Agni, Prithvi missiles · 11th President'},
    {'name':'Srinivasa Ramanujan', 'field':'Maths', 'discover':'Number theory, infinite series, partitions'},
    {'name':'Aryabhata', 'field':'Maths · Astronomy', 'discover':'Zero, π ≈ 3.1416, Earth rotation'},
    {'name':'Brahmagupta', 'field':'Maths · Astronomy', 'discover':'Rules for zero, negative numbers'},
    {'name':'Sushruta', 'field':'Medicine', 'discover':'Father of surgery, Sushruta Samhita'},
    {'name':'Charaka', 'field':'Medicine', 'discover':'Father of Indian medicine, Charaka Samhita'},
    {'name':'Dmitri Mendeleev', 'field':'Chemistry', 'discover':'Periodic table (1869)'},
    {'name':'Antoine Lavoisier', 'field':'Chemistry', 'discover':'Father of modern chemistry, conservation of mass'},
    {'name':'John Dalton', 'field':'Chemistry', 'discover':'Atomic theory'},
    {'name':'Michael Faraday', 'field':'Physics', 'discover':'Electromagnetic induction, electrolysis'},
    {'name':'James Clerk Maxwell', 'field':'Physics', 'discover':'Electromagnetic theory'},
    {'name':'Niels Bohr', 'field':'Physics', 'discover':'Atomic model, quantum theory'},
    {'name':'Werner Heisenberg', 'field':'Physics', 'discover':'Uncertainty principle'},
    {'name':'Erwin Schrödinger', 'field':'Physics', 'discover':'Wave equation, quantum mechanics'},
    {'name':'Charles Darwin', 'field':'Biology', 'discover':'Theory of evolution by natural selection'},
    {'name':'Gregor Mendel', 'field':'Biology', 'discover':'Father of genetics, laws of inheritance'},
    {'name':'Louis Pasteur', 'field':'Biology', 'discover':'Pasteurization, germ theory'},
    {'name':'Alexander Fleming', 'field':'Medicine', 'discover':'Penicillin (1928)'},
    {'name':'Ronald Ross', 'field':'Medicine', 'discover':'Malaria transmission by mosquitoes · Nobel 1902'},
    {'name':'Har Gobind Khorana', 'field':'Biology', 'discover':'Genetic code · Nobel 1968'},
    {'name':'Venkatraman Ramakrishnan', 'field':'Chemistry', 'discover':'Ribosome structure · Nobel 2009'},
    {'name':'Ada Lovelace', 'field':'Computing', 'discover':'First computer programmer'},
    {'name':'Alan Turing', 'field':'Computing · Maths', 'discover':'Turing machine, AI, WWII codebreaking'},
    {'name':'Tim Berners-Lee', 'field':'Computing', 'discover':'World Wide Web (1989)'},
    {'name':'Katherine Johnson', 'field':'Maths · Space', 'discover':'NASA orbital mechanics'},
    {'name':'Rosalind Franklin', 'field':'Biology', 'discover':'DNA double helix (X-ray)'},
    {'name':'Stephen Hawking', 'field':'Physics', 'discover':'Black hole radiation, cosmology'},
    {'name':'Jagadish Chandra Bose', 'field':'Physics · Biology', 'discover':'Radio waves, plant response'},
    {'name':'Meghnad Saha', 'field':'Physics', 'discover':'Saha ionization equation'},
    {'name':'Satyendra Nath Bose', 'field':'Physics', 'discover':'Bose-Einstein statistics'},
  ],
  'theories': [
    {'name':'Newton\'s 1st Law', 'field':'Physics', 'gist':'Body stays at rest/uniform motion unless external force acts.'},
    {'name':'Newton\'s 2nd Law', 'field':'Physics', 'gist':'F = ma — force equals rate of change of momentum.'},
    {'name':'Newton\'s 3rd Law', 'field':'Physics', 'gist':'Every action has equal and opposite reaction.'},
    {'name':'Theory of Relativity', 'field':'Physics', 'gist':'Space-time curves with mass; light speed is constant. Einstein 1905/1915.'},
    {'name':'Quantum Mechanics', 'field':'Physics', 'gist':'Energy is quantized; particles behave as waves. Planck, Bohr, Heisenberg.'},
    {'name':'Big Bang Theory', 'field':'Cosmology', 'gist':'Universe began ~13.8 billion years ago from singular dense state.'},
    {'name':'Heisenberg Uncertainty', 'field':'Physics', 'gist':'Cannot know both position and momentum precisely.'},
    {'name':'Ohm\'s Law', 'field':'Physics', 'gist':'V = IR for a conductor at constant temperature.'},
    {'name':'Archimedes\' Principle', 'field':'Physics', 'gist':'Buoyant force equals weight of displaced fluid.'},
    {'name':'Pascal\'s Law', 'field':'Physics', 'gist':'Pressure applied to fluid transmits equally in all directions.'},
    {'name':'Bernoulli\'s Principle', 'field':'Physics', 'gist':'Faster fluid flow → lower pressure.'},
    {'name':'Doppler Effect', 'field':'Physics', 'gist':'Frequency changes with relative motion of source/observer.'},
    {'name':'Atomic Theory', 'field':'Chemistry', 'gist':'Matter made of atoms. Dalton 1808.'},
    {'name':'Periodic Law', 'field':'Chemistry', 'gist':'Properties repeat periodically with atomic number. Mendeleev 1869.'},
    {'name':'Le Chatelier\'s Principle', 'field':'Chemistry', 'gist':'Equilibrium shifts to oppose change in conditions.'},
    {'name':'Arrhenius Theory', 'field':'Chemistry', 'gist':'Acids give H⁺, bases give OH⁻ in water.'},
    {'name':'Bronsted-Lowry', 'field':'Chemistry', 'gist':'Acid = proton donor; base = proton acceptor.'},
    {'name':'VSEPR Theory', 'field':'Chemistry', 'gist':'Molecular shape determined by electron-pair repulsion.'},
    {'name':'Molecular Orbital Theory', 'field':'Chemistry', 'gist':'Electrons in molecules occupy molecular orbitals.'},
    {'name':'Cell Theory', 'field':'Biology', 'gist':'All living things made of cells. Schleiden & Schwann 1839.'},
    {'name':'Theory of Evolution', 'field':'Biology', 'gist':'Natural selection drives species change. Darwin 1859.'},
    {'name':'Mendel\'s Laws', 'field':'Biology', 'gist':'Inheritance: dominance, segregation, independent assortment.'},
    {'name':'DNA Structure', 'field':'Biology', 'gist':'Double helix; Watson, Crick, Franklin 1953.'},
    {'name':'Germ Theory', 'field':'Biology', 'gist':'Microbes cause disease. Pasteur, Koch.'},
    {'name':'Photosynthesis', 'field':'Biology', 'gist':'Plants convert CO₂ + H₂O + light → glucose + O₂.'},
    {'name':'Demand & Supply', 'field':'Economics', 'gist':'Price set by intersection of demand and supply.'},
    {'name':'Say\'s Law', 'field':'Economics', 'gist':'Supply creates its own demand.'},
    {'name':'Keynesian Theory', 'field':'Economics', 'gist':'Government spending can boost demand in recession.'},
    {'name':'Quantity Theory of Money', 'field':'Economics', 'gist':'MV = PT — money supply drives prices.'},
    {'name':'Comparative Advantage', 'field':'Economics', 'gist':'Trade benefits when countries specialize. Ricardo.'},
    {'name':'Laffer Curve', 'field':'Economics', 'gist':'Tax revenue peaks at an optimal rate.'},
    {'name':'Phillips Curve', 'field':'Economics', 'gist':'Inverse relation between inflation and unemployment (short-run).'},
    {'name':'Tragedy of the Commons', 'field':'Environment', 'gist':'Shared resources get overused without regulation. Hardin 1968.'},
    {'name':'Gaia Hypothesis', 'field':'Environment', 'gist':'Earth acts as self-regulating system. Lovelock.'},
    {'name':'Ozone Depletion Theory', 'field':'Environment', 'gist':'CFCs break down ozone; Montreal Protocol 1987.'},
    {'name':'Greenhouse Effect', 'field':'Environment', 'gist':'GHGs trap heat, warming the planet.'},
  ],
  'events': [
    {'date':'01-26', 'year':1950, 'event':'Constitution of India came into force · Republic Day'},
    {'date':'01-30', 'year':1948, 'event':'Mahatma Gandhi assassinated'},
    {'date':'02-28', 'year':1928, 'event':'Simon Commission arrives in India'},
    {'date':'03-08', 'year':1911, 'event':'International Women\'s Day first observed'},
    {'date':'03-12', 'year':1930, 'event':'Dandi March begins (Salt Satyagraha)'},
    {'date':'04-13', 'year':1919, 'event':'Jallianwala Bagh massacre'},
    {'date':'04-14', 'year':1891, 'event':'B.R. Ambedkar born'},
    {'date':'05-11', 'year':1998, 'event':'Pokhran-II nuclear tests'},
    {'date':'05-18', 'year':1974, 'event':'Pokhran-I nuclear test (Smiling Buddha)'},
    {'date':'06-05', 'year':1972, 'event':'Stockholm Conference · World Environment Day'},
    {'date':'06-21', 'year':2015, 'event':'First International Yoga Day'},
    {'date':'07-18', 'year':1947, 'event':'Indian Independence Act passed by UK Parliament'},
    {'date':'08-15', 'year':1947, 'event':'India gains independence'},
    {'date':'08-29', 'year':1905, 'event':'Hockey wizard Dhyan Chand born'},
    {'date':'09-05', 'year':1888, 'event':'Sarvepalli Radhakrishnan born · Teachers\' Day'},
    {'date':'09-15', 'year':1948, 'event':'Sardar Patel led integration of Hyderabad'},
    {'date':'10-02', 'year':1869, 'event':'Mahatma Gandhi born · Gandhi Jayanti'},
    {'date':'10-31', 'year':1984, 'event':'Indira Gandhi assassinated'},
    {'date':'11-14', 'year':1889, 'event':'Jawaharlal Nehru born · Children\'s Day'},
    {'date':'11-26', 'year':1949, 'event':'Constitution adopted · Constitution Day'},
    {'date':'12-06', 'year':1956, 'event':'B.R. Ambedkar passed away · Mahaparinirvan Din'},
    {'date':'12-10', 'year':1948, 'event':'Human Rights Day'},
    {'date':'12-22', 'year':1887, 'event':'Srinivasa Ramanujan born · National Mathematics Day'},
    {'date':'12-24', 'year':1999, 'event':'Indian Airlines IC-814 hijack'},
    {'date':'05-26', 'year':1947, 'event':'Lord Mountbatten announces Partition plan'},
    {'date':'07-22', 'year':1947, 'event':'National Flag adopted by Constituent Assembly'},
    {'date':'08-29', 'year':1947, 'event':'Drafting Committee formed under Ambedkar'},
    {'date':'03-24', 'year':1887, 'event':'Rosalind Franklin born'},
    {'date':'04-12', 'year':1961, 'event':'Yuri Gagarin · first human in space'},
    {'date':'07-20', 'year':1969, 'event':'Apollo 11 · Man on Moon'},
    {'date':'02-11', 'year':2017, 'event':'ISRO PSLV-C37 · 104 satellites in one launch'},
    {'date':'09-24', 'year':2014, 'event':'Mangalyaan enters Mars orbit · India first to do so on 1st try'},
    {'date':'06-22', 'year':2016, 'event':'International Yoga Day · Paris Agreement'},
    {'date':'11-04', 'year':1984, 'event':'Bhopal Gas Tragedy'},
    {'date':'01-12', 'year':1863, 'event':'Swami Vivekananda born · National Youth Day'},
    {'date':'04-14', 'year':1891, 'event':'Ambedkar Jayanti'},
    {'date':'05-01', 'year':1960, 'event':'Maharashtra & Gujarat formed from Bombay State'},
    {'date':'06-05', 'year':1972, 'event':'UN Environment Programme founded'},
    {'date':'08-09', 'year':1942, 'event':'Quit India Movement launched'},
    {'date':'11-26', 'year':2008, 'event':'Mumbai 26/11 terror attacks'},
  ],
}


@app.route('/toolkit/reference')
def toolkit_reference():
    from flask import jsonify as _jf_tk
    return _jf_tk(TOOLKIT_DATA)


@app.route('/toolkit/reference/<section>')
def toolkit_reference_section(section):
    from flask import jsonify as _jf_tk
    data = TOOLKIT_DATA.get(section)
    if data is None:
        return _jf_tk({'error': 'Unknown section'}), 404
    return _jf_tk(data)


try:
    print('[toolkit-ref] data loaded:', {k: len(v) for k, v in TOOLKIT_DATA.items()})
except Exception:
    pass

# ============ FLOATING TOOLKIT BUTTON ON ALL PAGES ============
try:
    @app.after_request
    def _toolkit_float(resp):
        from flask import request as _rq_tf
        # Skip non-HTML, skip toolkit itself, skip API
        if resp.mimetype != 'text/html': return resp
        if _rq_tf.path.startswith('/toolkit'): return resp
        if _rq_tf.path.startswith('/static'): return resp
        if _rq_tf.path.startswith('/api'): return resp
        try:
            html = resp.get_data(as_text=True)
        except Exception:
            return resp
        if 'tk-float-btn' in html: return resp
        btn = '''
<style>
#tk-float-btn{position:fixed;bottom:18px;right:18px;width:56px;height:56px;
  border-radius:50%;background:linear-gradient(135deg,#d4a017,#b8860b);color:#0d1117;
  display:flex;align-items:center;justify-content:center;font-size:24px;
  text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,0.3);z-index:99998;
  border:2px solid #fff;transition:transform 0.15s;}
#tk-float-btn:active{transform:scale(0.92);}
</style>
<a id="tk-float-btn" href="/toolkit" title="Study Toolkit">🧰</a>
'''
        import re as _re_tf
        m = _re_tf.search(r'</body>', html)
        if m:
            html = html[:m.start()] + btn + html[m.start():]
            resp.set_data(html)
        return resp
    print('[toolkit-btn] floating button registered')
except Exception as _e:
    import sys; print('[toolkit-btn] error:', _e, file=sys.stderr)

# ============ TOOLKIT FIX: serve as raw HTML, skip Jinja ============
try:
    import os as _os_tkfix

    def _serve_toolkit_html():
        from flask import Response as _R_tk
        path = _os_tkfix.path.join(_os_tkfix.path.dirname(_os_tkfix.path.abspath(__file__)),
                                    'templates', 'toolkit.html')
        if not _os_tkfix.path.exists(path):
            return _R_tk('toolkit.html missing on server', status=500, mimetype='text/plain')
        with open(path, encoding='utf-8', errors='replace') as f:
            html = f.read()
        return _R_tk(html, mimetype='text/html')

    app.view_functions['study_toolkit'] = _serve_toolkit_html
    print('[toolkit-fix] /toolkit now serves raw HTML (no Jinja)')
except Exception as _e:
    import sys; print('[toolkit-fix] error:', _e, file=sys.stderr)

# ============ TOOLKIT FIX v2 ============
import os as _os_tk2

def _serve_toolkit_raw():
    from flask import Response as _R_tk2
    path = _os_tk2.path.join(_os_tk2.path.dirname(_os_tk2.path.abspath(__file__)),
                              'templates', 'toolkit.html')
    if not _os_tk2.path.exists(path):
        return _R_tk2('toolkit.html missing on server', status=500, mimetype='text/plain')
    with open(path, encoding='utf-8', errors='replace') as f:
        html = f.read()
    return _R_tk2(html, mimetype='text/html')

try:
    app.view_functions['study_toolkit'] = _serve_toolkit_raw
    print('[tk-fix2] study_toolkit endpoint overridden -> raw toolkit.html')
except Exception as _e:
    import sys; print('[tk-fix2] override error:', _e, file=sys.stderr)

# Also patch the broken template, in case anything else hits it
try:
    p = _os_tk2.path.join(_os_tk2.path.dirname(_os_tk2.path.abspath(__file__)),
                          'templates', 'toolkit_home.html')
    if _os_tk2.path.exists(p):
        with open(p, encoding='utf-8') as f:
            c = f.read()
        c = c.replace("url_for('toolkit_calc')", "/toolkit")
        c = c.replace('url_for("toolkit_calc")', '/toolkit')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(c)
        print('[tk-fix2] toolkit_home.html patched')
except Exception as _e:
    print('[tk-fix2] home patch error:', _e)

# ============ TOOLKIT FIX v3 ============
import os as _os_tk3

def _serve_toolkit_raw_v3():
    from flask import Response as _R_tk3
    path = _os_tk3.path.join(_os_tk3.path.dirname(_os_tk3.path.abspath(__file__)),
                              'templates', 'toolkit.html')
    if not _os_tk3.path.exists(path):
        return _R_tk3('toolkit.html missing', status=500)
    with open(path, encoding='utf-8', errors='replace') as f:
        html = f.read()
    return _R_tk3(html, mimetype='text/html')

try:
    # The REAL endpoint name is toolkit_home
    app.view_functions['toolkit_home'] = _serve_toolkit_raw_v3
    print('[tk-fix3] toolkit_home overridden -> raw toolkit.html')

    # Also handle study_toolkit if it exists
    if 'study_toolkit' in app.view_functions:
        app.view_functions['study_toolkit'] = _serve_toolkit_raw_v3
        print('[tk-fix3] study_toolkit also overridden')
except Exception as _e:
    import sys; print('[tk-fix3] error:', _e, file=sys.stderr)

# ============ FULL OFFLINE PWA ============
import os as _os_off

def _offline_sw():
    """Serve service worker from ROOT so scope is '/' (not /static/)."""
    from flask import Response as _R_off
    path = _os_off.path.join(_os_off.path.dirname(_os_off.path.abspath(__file__)),
                              'static', 'sw.js')
    if not _os_off.path.exists(path):
        return _R_off('// sw missing', status=500, mimetype='application/javascript')
    with open(path, encoding='utf-8') as f:
        js = f.read()
    return _R_off(js, mimetype='application/javascript',
                  headers={'Service-Worker-Allowed': '/',
                           'Cache-Control': 'no-cache'})

try:
    app.add_url_rule('/sw.js', 'service_worker_root', _offline_sw)
    print('[offline] /sw.js route registered (root scope)')
except Exception as _e:
    import sys; print('[offline] sw route error:', _e, file=sys.stderr)


@app.route('/offline/manifest-urls')
def offline_manifest_urls():
    """List of URLs to precache for offline use."""
    from flask import jsonify as _jf_off
    urls = [
        '/', '/toolkit', '/library', '/bookzone', '/epaper/lazy', '/news',
        '/static/style.css',
        '/static/manifest.json',
        '/static/offline.js',
        '/static/offline-fallback.html',
        '/static/icon-192.png',
        '/static/icon-512.png',
    ]
    return _jf_off({'urls': urls})


print('[offline] manifest-urls + fallback registered')

# ============ OFFLINE CACHE MANAGER ============
@app.route('/offline/cache')
def offline_cache_manager():
    from flask import render_template as _rt_cm
    books = Book.query.order_by(Book.uploaded_at.desc()).limit(500).all()
    book_index = [
        {'id': b.id, 'title': b.title or 'Untitled',
         'author': b.author or '', 'collection': b.collection or 'OTHER',
         'url': f'/book/{b.id}/stream'}
        for b in books
    ]
    pages_index = [
        {'url': '/', 'label': 'Home'},
        {'url': '/toolkit', 'label': 'Study Toolkit'},
        {'url': '/library', 'label': 'Library'},
        {'url': '/bookzone', 'label': 'Book Zone'},
        {'url': '/epaper/lazy', 'label': "Today's Newspaper"},
        {'url': '/news', 'label': 'News Feed'},
    ]
    return _rt_cm('offline_cache.html',
                  books=books,
                  book_index=book_index,
                  pages_index=pages_index)

@app.route('/offline/list-saved')
def offline_list_saved():
    from flask import jsonify as _jf_cm
    # Client-side caches are in IndexedDB; return an index of what CAN be saved
    books = Book.query.order_by(Book.uploaded_at.desc()).limit(500).all()
    return _jf_cm({
        'books': [{'id': b.id, 'title': b.title or 'Untitled',
                   'author': b.author or '', 'collection': b.collection or 'OTHER',
                   'url': f'/book/{b.id}/stream'} for b in books],
        'pages': [
            {'url': '/', 'label': 'Home'},
            {'url': '/toolkit', 'label': 'Study Toolkit'},
            {'url': '/library', 'label': 'Library'},
            {'url': '/bookzone', 'label': 'Book Zone'},
            {'url': '/epaper/lazy', 'label': "Today's Newspaper"},
            {'url': '/news', 'label': 'News Feed'},
            {'url': '/flashcards', 'label': 'Flashcards'},
            {'url': '/notes', 'label': 'Notes'},
        ]
    })

print('[cache-mgr] /offline/cache + /offline/list-saved registered')

# ============ IN-APP PDF READER (works from cache offline) ============
@app.route('/reader/<int:book_id>')
def book_reader(book_id):
    from flask import render_template as _rt_rd
    book = Book.query.get_or_404(book_id)
    return _rt_rd('reader.html', book=book)

# Force inline disposition for /book/<id>/stream (embed uses it)
try:
    @app.after_request
    def _force_inline_pdf(resp):
        from flask import request as _rq_rd
        if _rq_rd.path.startswith('/book/') and _rq_rd.path.endswith('/stream'):
            # Rewrite any attachment -> inline
            cd = resp.headers.get('Content-Disposition', '')
            if 'attachment' in cd:
                resp.headers['Content-Disposition'] = cd.replace('attachment', 'inline')
        return resp
    print('[reader] inline-disposition hook active')
except Exception as _e:
    import sys; print('[reader] hook error:', _e, file=sys.stderr)

print('[reader] /reader/<id> route registered')


# ============ FLOATING TOOLKIT BUTTON v2 (hideable + hidden on reader) ============
try:
    @app.after_request
    def _toolkit_float_v2(resp):
        from flask import request as _rq_tk2
        if resp.mimetype != 'text/html': return resp
        path = _rq_tk2.path
        # Skip toolkit page itself
        if path.startswith('/toolkit'): return resp
        if path.startswith('/static'): return resp
        if path.startswith('/reader'): return resp  # hide on PDF reader
        if path.startswith('/api'): return resp
        if path.startswith('/offline'): return resp  # hide on offline manager too
        try:
            html = resp.get_data(as_text=True)
        except Exception:
            return resp
        if 'tk-float-wrap' in html: return resp

        btn = """
<style>
#tk-float-wrap{position:fixed;bottom:18px;right:18px;z-index:99998;
  display:flex;align-items:center;gap:6px;font-family:system-ui,sans-serif;}
#tk-float-btn{width:56px;height:56px;border-radius:50%;
  background:linear-gradient(135deg,#d4a017,#b8860b);color:#0d1117;
  display:flex;align-items:center;justify-content:center;font-size:24px;
  text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,0.3);
  border:2px solid #fff;transition:transform 0.15s;}
#tk-float-btn:active{transform:scale(0.92);}
#tk-hide-btn{width:22px;height:22px;border-radius:50%;background:#da3633;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:12px;
  cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,0.4);border:1.5px solid #fff;
  font-weight:700;line-height:1;}
#tk-restore{position:fixed;bottom:22px;right:22px;width:36px;height:36px;
  border-radius:50%;background:rgba(212,160,23,0.85);color:#0d1117;
  display:none;align-items:center;justify-content:center;font-size:16px;
  cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,0.3);z-index:99998;
  border:1.5px solid #fff;opacity:0.55;}
</style>
<div id="tk-float-wrap">
  <div id="tk-hide-btn" onclick="tkHide()" title="Hide">×</div>
  <a id="tk-float-btn" href="/toolkit" title="Study Toolkit">🧰</a>
</div>
<div id="tk-restore" onclick="tkShow()" title="Show toolkit">🧰</div>
<script>
(function(){
  if (localStorage.getItem('tk_btn_hidden') === '1') {
    document.getElementById('tk-float-wrap').style.display = 'none';
    document.getElementById('tk-restore').style.display = 'flex';
  }
})();
function tkHide(){
  localStorage.setItem('tk_btn_hidden', '1');
  document.getElementById('tk-float-wrap').style.display = 'none';
  document.getElementById('tk-restore').style.display = 'flex';
}
function tkShow(){
  localStorage.removeItem('tk_btn_hidden');
  document.getElementById('tk-float-wrap').style.display = 'flex';
  document.getElementById('tk-restore').style.display = 'none';
}
</script>
"""
        import re as _re_tk2
        m = _re_tk2.search(r'</body>', html)
        if m:
            html = html[:m.start()] + btn + html[m.start():]
            resp.set_data(html)
        return resp
    print('[tk-float-v2] hideable + hidden on /reader')
except Exception as _e:
    import sys; print('[tk-float-v2] error:', _e, file=sys.stderr)


# === RAW SQL reader route (bypasses ORM stuck-session bug) ===
def _ias_reader_raw(book_id):
    from flask import render_template as _rt_r, abort as _abort
    from sqlalchemy import text as _t
    try:
        db.session.remove()
    except Exception:
        pass
    with db.engine.connect() as _conn:
        try:
            _conn.execute(_t('ROLLBACK'))
        except Exception:
            pass
        row = _conn.execute(
            _t('SELECT id, title, filename FROM book WHERE id = :i'),
            {'i': book_id}).fetchone()
    if not row:
        _abort(404)
    class _B:
        pass
    b = _B()
    b.id = row[0]
    b.title = row[1]
    b.filename = row[2]
    return _rt_r('reader.html', book=b)

try:
    app.view_functions['book_reader'] = _ias_reader_raw
    print('[fix-reader] book_reader -> raw SQL')
except Exception as _e:
    print('[fix-reader] error:', _e)


# ============ GOOGLE DRIVE BACKUP (laptop) ============
import os as _os_gd
import json as _json_gd
import io as _io_gd
import time as _time_gd
from datetime import datetime as _dt_gd

GDRIVE_FOLDER_ID = '1UaYQuQwznTc3A4mms0sjQ3L7B76tJAZQ'
GDRIVE_KEY = _os_gd.path.expanduser('~/ias_machine/config/gdrive_key.json')
if not _os_gd.path.exists(GDRIVE_KEY):
    GDRIVE_KEY = 'config/gdrive_key.json'
GDRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']

_gd_cache = {'svc': None, 'ts': 0}


def _gdrive_service():
    now = _time_gd.time()
    if _gd_cache['svc'] and (now - _gd_cache['ts']) < 600:
        return _gd_cache['svc']
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(GDRIVE_KEY, scopes=GDRIVE_SCOPES)
    svc = build('drive', 'v3', credentials=creds, cache_discovery=False)
    _gd_cache['svc'] = svc
    _gd_cache['ts'] = now
    return svc


BACKUP_TABLES = ['Book', 'Topper', 'TopperFullText', 'TopperParagraph', 'TopperDNA',
                 'InterviewQA', 'InterviewTranscript', 'NewsArticle',
                 'Question', 'Answer', 'CommonMistake', 'EthicsCase', 'EssayTopic',
                 'StudyNote', 'SyllabusNode', 'SelectionStat']


def _dump_tables(limit=5000):
    out = {}
    for tname in BACKUP_TABLES:
        cls = globals().get(tname)
        if cls is None:
            continue
        try:
            rows = cls.query.limit(limit).all()
            cols = [c.name for c in cls.__table__.columns]
            out[tname] = [{c: (str(getattr(r, c)) if getattr(r, c) is not None else None) for c in cols} for r in rows]
        except Exception as e:
            out[tname] = [{'__error': str(e)[:120]}]
    return out


@app.route('/backup/to-drive', methods=['GET', 'POST'])
def backup_to_drive():
    from flask import jsonify as _jf, request as _rq
    try:
        svc = _gdrive_service()
    except Exception as e:
        return _jf({'ok': False, 'error': 'auth: ' + str(e)[:250]}), 500
    try:
        data = _dump_tables()
    except Exception as e:
        return _jf({'ok': False, 'error': 'dump: ' + str(e)[:250]}), 500
    counts = {k: len(v) for k, v in data.items()}
    payload = {
        'generated_at': _dt_gd.utcnow().isoformat() + 'Z',
        'version': 'v1',
        'tables': counts,
        'data': data,
    }
    js = _json_gd.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    fname = 'ias_backup_' + _dt_gd.utcnow().strftime('%Y-%m-%d_%H%M') + '.json'
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(_io_gd.BytesIO(js), mimetype='application/json')
    try:
        created = svc.files().create(
            body={'name': fname, 'parents': [GDRIVE_FOLDER_ID]},
            media_body=media,
            fields='id,name,size,createdTime').execute()
    except Exception as e:
        return _jf({'ok': False, 'error': 'upload: ' + str(e)[:350]}), 500
    return _jf({'ok': True, 'file': created, 'size_bytes': len(js), 'tables': counts})


@app.route('/backup/list-drive')
def backup_list_drive():
    from flask import jsonify as _jf
    try:
        svc = _gdrive_service()
        q = "'" + GDRIVE_FOLDER_ID + "' in parents and trashed=false"
        res = svc.files().list(q=q, orderBy='createdTime desc', pageSize=100,
                               fields='files(id,name,size,createdTime)').execute()
        files = res.get('files', [])
        total = sum(int(f.get('size', 0) or 0) for f in files)
        return _jf({'ok': True, 'count': len(files), 'total_bytes': total, 'files': files[:30]})
    except Exception as e:
        return _jf({'ok': False, 'error': str(e)[:250], 'count': 0, 'total_bytes': 0, 'files': []})


@app.route('/backup/status')
def backup_status():
    from flask import jsonify as _jf
    return _jf({'folder_id': GDRIVE_FOLDER_ID, 'has_key': _os_gd.path.exists(GDRIVE_KEY)})


@app.route('/backup/drive')
def backup_drive_ui():
    from flask import render_template as _rt_gd
    return _rt_gd('backup_drive.html')


@app.route('/backup/delete/<file_id>', methods=['POST'])
def backup_delete(file_id):
    from flask import jsonify as _jf
    try:
        svc = _gdrive_service()
        svc.files().delete(fileId=file_id).execute()
        return _jf({'ok': True})
    except Exception as e:
        return _jf({'ok': False, 'error': str(e)[:250]}), 500


print('[gdrive-laptop] backup routes registered')


# === OAuth-based Drive service (replaces service account) ===
import os as _os_oauth
import json as _json_oauth

OAUTH_TOKEN  = _os_oauth.path.expanduser('~/ias_machine/config/oauth_token.json')
if not _os_oauth.path.exists(OAUTH_TOKEN):
    OAUTH_TOKEN = 'config/oauth_token.json'

def _gdrive_service_oauth():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import time as _t
    if not _os_oauth.path.exists(OAUTH_TOKEN):
        raise RuntimeError('OAuth token missing — run oauth_setup.py first')
    creds = Credentials.from_authorized_user_file(OAUTH_TOKEN, SCOPES)
    if not creds.valid or (creds.expired and creds.refresh_token):
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        with open(OAUTH_TOKEN, 'w') as f:
            f.write(creds.to_json())
    return build('drive', 'v3', credentials=creds, cache_discovery=False)

# Replace the service-account path
_gd_cache['svc'] = None
_gd_cache['ts'] = 0
_gdrive_service = _gdrive_service_oauth
print('[gdrive-oauth] Drive now uses OAuth user credentials')


# === Fix: define SCOPES for OAuth function ===
SCOPES = ['https://www.googleapis.com/auth/drive']
print('[fix-scopes] SCOPES defined')
