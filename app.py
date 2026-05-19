"""
RetroLens — AI-Powered Retrospective & Feedback Analyzer
==========================================================
Paste sprint retro notes → AI categorizes themes, detects sentiment,
identifies action items, and tracks team health trends over time.

Tech Stack: Flask + SQLAlchemy + Anthropic Claude API + Chart.js
Author: Saanvi (Tech PM Portfolio)
"""

import os
import json
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'retro-lens-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///retro_analyzer.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ─── Models ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    retros = db.relationship('RetroSession', backref='team', lazy=True, cascade='all, delete-orphan')


class RetroSession(db.Model):
    __tablename__ = 'retro_sessions'
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    sprint_name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    raw_input = db.Column(db.Text, nullable=False)
    analysis_json = db.Column(db.Text)  # Full AI analysis stored as JSON
    overall_sentiment = db.Column(db.Float, default=0.0)  # -1 to 1
    morale_score = db.Column(db.Integer, default=3)  # 1-5
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('RetroItem', backref='session', lazy=True, cascade='all, delete-orphan')
    action_items = db.relationship('ActionItem', backref='session', lazy=True, cascade='all, delete-orphan')


class RetroItem(db.Model):
    __tablename__ = 'retro_items'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('retro_sessions.id'), nullable=False)
    original_text = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))  # went_well, to_improve, kudos, blocker, process, technical, communication
    theme = db.Column(db.String(100))  # AI-detected theme
    sentiment = db.Column(db.Float, default=0.0)  # -1 to 1
    priority = db.Column(db.String(20), default='medium')


class ActionItem(db.Model):
    __tablename__ = 'action_items'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('retro_sessions.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    owner = db.Column(db.String(100))
    status = db.Column(db.String(20), default='open')  # open, in_progress, done
    due_date = db.Column(db.Date)
    priority = db.Column(db.String(20), default='medium')


# ─── Auth ─────────────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username taken', 'error')
            return redirect(url_for('register'))
        u = User(username=request.form['username'], email=request.form['email'])
        u.set_password(request.form['password'])
        db.session.add(u)
        db.session.commit()
        login_user(u)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    teams = Team.query.filter_by(created_by=current_user.id).all()
    recent_sessions = RetroSession.query.order_by(RetroSession.created_at.desc()).limit(10).all()

    # Morale trend data
    morale_data = []
    for session in RetroSession.query.order_by(RetroSession.date).all():
        morale_data.append({
            'date': session.date.isoformat() if session.date else '',
            'sprint': session.sprint_name,
            'morale': session.morale_score,
            'sentiment': round(session.overall_sentiment, 2)
        })

    # Theme frequency across all sessions
    all_items = RetroItem.query.all()
    theme_freq = {}
    for item in all_items:
        if item.theme:
            theme_freq[item.theme] = theme_freq.get(item.theme, 0) + 1

    # Category distribution
    cat_dist = {}
    for item in all_items:
        if item.category:
            cat_dist[item.category] = cat_dist.get(item.category, 0) + 1

    # Open action items
    open_actions = ActionItem.query.filter(ActionItem.status != 'done').order_by(ActionItem.priority).all()

    return render_template('dashboard.html',
                           teams=teams,
                           recent_sessions=recent_sessions,
                           morale_data=morale_data,
                           theme_freq=theme_freq,
                           cat_dist=cat_dist,
                           open_actions=open_actions)


# ─── Team Management ─────────────────────────────────────────────────────────

@app.route('/team/new', methods=['GET', 'POST'])
@login_required
def new_team():
    if request.method == 'POST':
        team = Team(name=request.form['name'], created_by=current_user.id)
        db.session.add(team)
        db.session.commit()
        flash('Team created!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('new_team.html')


# ─── Retro Session ────────────────────────────────────────────────────────────

@app.route('/retro/new', methods=['GET', 'POST'])
@login_required
def new_retro():
    teams = Team.query.filter_by(created_by=current_user.id).all()
    if request.method == 'POST':
        session = RetroSession(
            team_id=int(request.form['team_id']),
            sprint_name=request.form['sprint_name'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date() if request.form.get('date') else datetime.utcnow().date(),
            raw_input=request.form['raw_input']
        )
        db.session.add(session)
        db.session.commit()

        # Analyze with AI
        analysis = analyze_retro_with_ai(session.raw_input)
        if analysis:
            session.analysis_json = json.dumps(analysis)
            session.overall_sentiment = analysis.get('overall_sentiment', 0)
            session.morale_score = analysis.get('morale_score', 3)

            # Create retro items
            for item_data in analysis.get('items', []):
                item = RetroItem(
                    session_id=session.id,
                    original_text=item_data.get('text', ''),
                    category=item_data.get('category', 'general'),
                    theme=item_data.get('theme', ''),
                    sentiment=item_data.get('sentiment', 0),
                    priority=item_data.get('priority', 'medium')
                )
                db.session.add(item)

            # Create action items
            for action in analysis.get('action_items', []):
                ai = ActionItem(
                    session_id=session.id,
                    text=action.get('text', ''),
                    owner=action.get('owner', ''),
                    priority=action.get('priority', 'medium')
                )
                db.session.add(ai)

            db.session.commit()
        else:
            # Fallback: simple parsing without AI
            fallback_analyze(session)

        return redirect(url_for('retro_detail', session_id=session.id))
    return render_template('new_retro.html', teams=teams)


@app.route('/retro/<int:session_id>')
@login_required
def retro_detail(session_id):
    session = RetroSession.query.get_or_404(session_id)
    items = RetroItem.query.filter_by(session_id=session_id).all()
    actions = ActionItem.query.filter_by(session_id=session_id).all()

    # Group items by category
    categories = {}
    for item in items:
        cat = item.category or 'uncategorized'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    # Theme distribution for this session
    themes = {}
    for item in items:
        if item.theme:
            themes[item.theme] = themes.get(item.theme, 0) + 1

    # Sentiment breakdown
    sentiments = {'positive': 0, 'neutral': 0, 'negative': 0}
    for item in items:
        if item.sentiment > 0.2:
            sentiments['positive'] += 1
        elif item.sentiment < -0.2:
            sentiments['negative'] += 1
        else:
            sentiments['neutral'] += 1

    analysis = json.loads(session.analysis_json) if session.analysis_json else {}

    return render_template('retro_detail.html',
                           session=session,
                           items=items,
                           actions=actions,
                           categories=categories,
                           themes=themes,
                           sentiments=sentiments,
                           analysis=analysis)


@app.route('/action/<int:action_id>/update', methods=['POST'])
@login_required
def update_action(action_id):
    action = ActionItem.query.get_or_404(action_id)
    action.status = request.form.get('status', action.status)
    db.session.commit()
    if request.is_json:
        return jsonify({'success': True})
    return redirect(request.referrer or url_for('dashboard'))


# ─── AI Analysis ──────────────────────────────────────────────────────────────

def analyze_retro_with_ai(raw_text):
    """Use Claude API to analyze retro feedback"""
    if not ANTHROPIC_API_KEY:
        return None

    try:
        import httpx
        response = httpx.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'content-type': 'application/json',
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 2000,
                'messages': [{'role': 'user', 'content': f"""Analyze this sprint retrospective feedback. Return ONLY valid JSON with no other text.

Feedback:
{raw_text}

Return this exact JSON structure:
{{
  "overall_sentiment": <float -1 to 1>,
  "morale_score": <int 1-5>,
  "summary": "<2-3 sentence executive summary>",
  "key_insights": ["<insight1>", "<insight2>", "<insight3>"],
  "items": [
    {{
      "text": "<original feedback text>",
      "category": "<went_well|to_improve|blocker|kudos|process|technical|communication>",
      "theme": "<detected theme like 'collaboration', 'estimation', 'testing', 'communication'>",
      "sentiment": <float -1 to 1>,
      "priority": "<high|medium|low>"
    }}
  ],
  "action_items": [
    {{
      "text": "<suggested action>",
      "owner": "<suggested owner or 'Team'>",
      "priority": "<high|medium|low>"
    }}
  ],
  "patterns": ["<recurring pattern1>", "<recurring pattern2>"],
  "risk_flags": ["<any concerning trends or risks>"]
}}"""}]
            },
            timeout=30
        )
        data = response.json()
        text = data['content'][0]['text']
        # Clean potential markdown fencing
        text = re.sub(r'^```json\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text.strip())
        return json.loads(text)
    except Exception as e:
        print(f"AI analysis error: {e}")
        return None


def fallback_analyze(session):
    """Simple rule-based analysis when AI is unavailable"""
    lines = [l.strip() for l in session.raw_input.split('\n') if l.strip()]

    positive_words = {'great', 'good', 'excellent', 'improved', 'love', 'awesome', 'well', 'kudos', 'thanks', 'smooth', 'efficient'}
    negative_words = {'bad', 'slow', 'issue', 'problem', 'blocked', 'frustrated', 'confusing', 'late', 'missed', 'unclear'}

    for line in lines:
        # Remove common prefixes
        clean = re.sub(r'^[-*•+]\s*', '', line).strip()
        if not clean:
            continue

        words = set(clean.lower().split())
        pos = len(words & positive_words)
        neg = len(words & negative_words)
        sentiment = (pos - neg) / max(len(words), 1)

        # Categorize
        if pos > neg:
            category = 'went_well'
        elif neg > pos:
            category = 'to_improve'
        else:
            category = 'general'

        # Simple theme detection
        theme = 'general'
        if any(w in clean.lower() for w in ['test', 'bug', 'quality']):
            theme = 'testing'
        elif any(w in clean.lower() for w in ['deploy', 'release', 'ci', 'cd']):
            theme = 'deployment'
        elif any(w in clean.lower() for w in ['communication', 'meeting', 'standup']):
            theme = 'communication'
        elif any(w in clean.lower() for w in ['estimate', 'planning', 'scope']):
            theme = 'estimation'
        elif any(w in clean.lower() for w in ['team', 'collaborat', 'help']):
            theme = 'collaboration'

        item = RetroItem(
            session_id=session.id,
            original_text=clean,
            category=category,
            theme=theme,
            sentiment=round(sentiment, 2),
            priority='medium'
        )
        db.session.add(item)

    session.overall_sentiment = 0.0
    session.morale_score = 3
    session.analysis_json = json.dumps({
        'summary': f'Analyzed {len(lines)} feedback items using rule-based parsing. Connect an Anthropic API key for AI-powered analysis.',
        'key_insights': ['Configure ANTHROPIC_API_KEY environment variable for full AI analysis'],
        'patterns': [],
        'risk_flags': []
    })
    db.session.commit()


# ─── Comparison API ───────────────────────────────────────────────────────────

@app.route('/api/trends/<int:team_id>')
@login_required
def api_team_trends(team_id):
    sessions = RetroSession.query.filter_by(team_id=team_id).order_by(RetroSession.date).all()
    return jsonify({
        'sprints': [s.sprint_name for s in sessions],
        'morale': [s.morale_score for s in sessions],
        'sentiment': [round(s.overall_sentiment, 2) for s in sessions],
        'dates': [s.date.isoformat() if s.date else '' for s in sessions]
    })


# ─── Template Filters ────────────────────────────────────────────────────────

@app.template_filter('timeago')
def timeago_filter(dt):
    if not dt:
        return ''
    diff = datetime.utcnow() - dt
    if diff.days > 30:
        return dt.strftime('%b %d, %Y')
    elif diff.days > 0:
        return f'{diff.days}d ago'
    elif diff.seconds > 3600:
        return f'{diff.seconds // 3600}h ago'
    return 'just now'

@app.template_filter('sentiment_label')
def sentiment_label_filter(val):
    if val > 0.3:
        return 'positive'
    elif val < -0.3:
        return 'negative'
    return 'neutral'

@app.template_filter('sentiment_color')
def sentiment_color_filter(val):
    if val > 0.3:
        return '#10b981'
    elif val < -0.3:
        return '#ef4444'
    return '#f59e0b'


# ─── Seed Data ────────────────────────────────────────────────────────────────

def seed_demo_data():
    if User.query.first():
        return

    u = User(username='saanvi', email='saanvi@example.com')
    u.set_password('password123')
    db.session.add(u)
    db.session.flush()

    team = Team(name='Manzanita Dev Team', created_by=u.id)
    db.session.add(team)
    db.session.flush()

    # Demo retro sessions
    demo_retros = [
        {
            'sprint': 'Sprint 1 — Foundation',
            'offset': -28,
            'morale': 4,
            'sentiment': 0.4,
            'raw': """- Great team collaboration on setting up the project architecture
- Login page was delivered ahead of schedule
- Need to improve our estimation — underestimated the database schema complexity
- Standups felt too long, need to timebox to 15 min
- Kudos to Alex for fixing the CI pipeline overnight
- Deployment process was confusing, need documentation
- Good pair programming sessions helped onboard new members""",
            'items': [
                ('Great team collaboration on setting up the project architecture', 'went_well', 'collaboration', 0.7, 'low'),
                ('Login page was delivered ahead of schedule', 'went_well', 'delivery', 0.6, 'low'),
                ('Need to improve our estimation — underestimated DB schema', 'to_improve', 'estimation', -0.3, 'high'),
                ('Standups felt too long, need to timebox to 15 min', 'to_improve', 'communication', -0.2, 'medium'),
                ('Kudos to Alex for fixing the CI pipeline overnight', 'kudos', 'devops', 0.8, 'low'),
                ('Deployment process was confusing, need docs', 'to_improve', 'deployment', -0.4, 'high'),
                ('Good pair programming sessions helped onboarding', 'went_well', 'collaboration', 0.5, 'low'),
            ],
            'actions': [
                ('Introduce planning poker for story point estimation', 'Saanvi', 'high'),
                ('Create deployment runbook documentation', 'Alex', 'high'),
                ('Timebox daily standups to 15 minutes', 'Team', 'medium'),
            ]
        },
        {
            'sprint': 'Sprint 2 — Core Features',
            'offset': -14,
            'morale': 3,
            'sentiment': 0.1,
            'raw': """- Chat feature was complex but team pulled through
- Too many bugs found in QA — need better unit test coverage
- Communication between frontend and backend teams improved
- Scope creep on the search feature added 2 days
- Code review turnaround was too slow, blocking PRs
- Good documentation of API endpoints this sprint
- Need clearer acceptance criteria before starting stories""",
            'items': [
                ('Chat feature was complex but team pulled through', 'went_well', 'delivery', 0.3, 'low'),
                ('Too many bugs in QA — need better test coverage', 'to_improve', 'testing', -0.5, 'high'),
                ('Frontend-backend communication improved', 'went_well', 'communication', 0.4, 'low'),
                ('Scope creep on search added 2 days', 'blocker', 'estimation', -0.6, 'high'),
                ('Code review turnaround too slow', 'to_improve', 'process', -0.4, 'high'),
                ('Good API documentation this sprint', 'went_well', 'documentation', 0.5, 'low'),
                ('Need clearer acceptance criteria', 'to_improve', 'process', -0.3, 'medium'),
            ],
            'actions': [
                ('Set minimum 80% unit test coverage target', 'Team', 'high'),
                ('24-hour SLA for code review turnaround', 'Team', 'high'),
                ('Add acceptance criteria template to story creation', 'Saanvi', 'medium'),
                ('PO to sign off on scope before sprint starts', 'Jordan', 'medium'),
            ]
        },
        {
            'sprint': 'Sprint 3 — Integration',
            'offset': -1,
            'morale': 5,
            'sentiment': 0.6,
            'raw': """- Estimation accuracy improved significantly after planning poker
- Deployment runbook saved us hours during the release
- Team velocity is trending up — 40 pts vs 35 last sprint
- Code review SLA working well, no more blocking PRs
- Live chat integration with WebSocket was smooth
- Need to set up monitoring/alerting for production
- Great sprint overall, feeling confident about launch""",
            'items': [
                ('Estimation improved after planning poker', 'went_well', 'estimation', 0.7, 'low'),
                ('Deployment runbook saved hours', 'went_well', 'deployment', 0.8, 'low'),
                ('Velocity trending up — 40 pts vs 35', 'went_well', 'delivery', 0.6, 'low'),
                ('Code review SLA working well', 'went_well', 'process', 0.5, 'low'),
                ('WebSocket integration was smooth', 'went_well', 'technical', 0.4, 'low'),
                ('Need monitoring/alerting for production', 'to_improve', 'devops', -0.2, 'high'),
                ('Great sprint, confident about launch', 'went_well', 'morale', 0.9, 'low'),
            ],
            'actions': [
                ('Set up Datadog monitoring before launch', 'Alex', 'high'),
                ('Create incident response playbook', 'Saanvi', 'medium'),
            ]
        }
    ]

    for retro in demo_retros:
        s = RetroSession(
            team_id=team.id,
            sprint_name=retro['sprint'],
            date=datetime.utcnow().date() + timedelta(days=retro['offset']),
            raw_input=retro['raw'],
            overall_sentiment=retro['sentiment'],
            morale_score=retro['morale'],
            analysis_json=json.dumps({
                'summary': f"Sprint retrospective for {retro['sprint']}",
                'key_insights': ['Demo data — run with ANTHROPIC_API_KEY for real AI analysis'],
                'patterns': [],
                'risk_flags': []
            })
        )
        db.session.add(s)
        db.session.flush()

        for text, cat, theme, sent, priority in retro['items']:
            item = RetroItem(session_id=s.id, original_text=text, category=cat, theme=theme, sentiment=sent, priority=priority)
            db.session.add(item)

        for text, owner, priority in retro['actions']:
            status = 'done' if retro['offset'] < -14 else ('in_progress' if retro['offset'] < -7 else 'open')
            action = ActionItem(session_id=s.id, text=text, owner=owner, priority=priority, status=status)
            db.session.add(action)

    db.session.commit()
    print("✅ RetroLens demo data seeded!")


with app.app_context():
    db.create_all()
    seed_demo_data()

if __name__ == '__main__':
    app.run(debug=True, port=5002)
