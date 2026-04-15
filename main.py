import os
import json
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, abort
from werkzeug.utils import secure_filename
import csv
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, func, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
import openai
# Supabase PostgreSQL settings

# SQLAlchemy database URL (PostgreSQL via psycopg2)
DATABASE_URL = os.environ.get("DATABASE_URL")
GMAIL_USER = "odysseyauto.mobile393@gmail.com"
GMAIL_APP_PASSWORD = "upog lspx ecyr hrzg"  # Google App Password
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'csv'}

# Create uploads folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
# SQLAlchemy setup (synchronous for Flask)
# Database is already created in Supabase, no need to create it
# Tables will be created when engine is initialized

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "sslmode": "require",
        "connect_timeout": 10
    }
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserInfo(Base):
    __tablename__ = 'users_info'
    id = Column(Integer, primary_key=True)
    user_uuid = Column(String(64), unique=True, index=True)
    ip = Column(String(64))
    user_agent = Column(Text)
    device = Column(String(128))
    visits_count = Column(Integer, default=0)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)

class Referrer(Base):
    __tablename__ = 'referrers'
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    count = Column(Integer, default=0)

class BlogPost(Base):
    __tablename__ = 'blog_posts'
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    summary = Column(Text)
    details = Column(Text)
    img_urls = Column(Text)
    url = Column(String(1024))
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def ensure_blog_posts_schema():
    inspector = inspect(engine)
    if 'blog_posts' not in inspector.get_table_names():
        return

    existing_columns = {col['name'] for col in inspector.get_columns('blog_posts')}
    missing_columns = []

    if 'summary' not in existing_columns:
        missing_columns.append('summary TEXT')
    if 'details' not in existing_columns:
        missing_columns.append('details TEXT')
    if 'img_urls' not in existing_columns:
        missing_columns.append('img_urls TEXT')
    if 'url' not in existing_columns:
        missing_columns.append('url VARCHAR(1024)')
    if 'created_at' not in existing_columns:
        missing_columns.append('created_at TIMESTAMP')

    if not missing_columns:
        return

    with engine.begin() as conn:
        for column_def in missing_columns:
            conn.execute(text(f'ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS {column_def}'))
        if 'created_at' not in existing_columns:
            conn.execute(text('UPDATE blog_posts SET created_at = NOW() WHERE created_at IS NULL'))

ensure_blog_posts_schema()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def slugify(value: str) -> str:
    value = value or ''
    value = value.strip().lower().replace(' ', '_')
    return ''.join(ch for ch in value if ch.isalnum() or ch in ['_', '-'])

def source_color(name: str) -> str:
    name = (name or '').lower()
    if name == 'facebook':
        return '#3b82f6'
    if name == 'direct':
        return '#ef4444'
    if name == 'google':
        return '#dc2626'
    if name == 'instagram':
        return '#ec4899'
    if name == 'other':
        return '#f97316'
    return '#6b7280'

def seed_default_posts(db):
    if db.query(BlogPost).count() == 0:
        for default_post in DEFAULT_POSTS:
            blog = BlogPost(
                title=default_post['title'],
                slug=default_post['slug'],
                summary=default_post.get('summary', ''),
                details=default_post.get('details', ''),
                img_urls=json.dumps(default_post.get('img_urls', [])),
                url=default_post.get('url', f"/blog/{default_post['slug']}"),
                created_at=default_post.get('created_at', datetime.utcnow())
            )
            db.add(blog)
        db.commit()
        for blog in db.query(BlogPost).all():
            generate_blog_html(blog)


def generate_blog_html(post):
    image_list = json.loads(post.img_urls or '[]')
    main_image = image_list[0] if image_list else ''
    thumbs_html = ''
    for idx, img in enumerate(image_list):
        thumbs_html += f'<button type="button" class="w-20 h-20 rounded-xl overflow-hidden border border-gray-200" onclick="setMainImage({idx})">'
        thumbs_html += f'<img src="{img}" class="w-full h-full object-cover">'
        thumbs_html += '</button>'

    details_paragraphs = ''.join(
        f'<p class="text-gray-700 mb-6 leading-relaxed">{line.strip()}</p>'
        for line in (post.details or '').split('\n') if line.strip()
    )
    image_js_list = ', '.join(json.dumps(img) for img in image_list)
    filename = os.path.join('templates', 'blog', f'{post.slug}.html')
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    html_content = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{title} - Salvage Odyssey Auto</title>
    <link rel=\"icon\" type=\"image/jpg\" href=\"https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/logo-removebg.png\">
    <script src=\"https://cdn.tailwindcss.com\"></script>
</head>
<body>
    <div class=\"min-h-screen bg-white\">
        <nav class=\"bg-black text-white sticky top-0 z-50 shadow-lg\">
            <div class=\"max-w-7xl mx-auto px-4 sm:px-6 lg:px-8\">
                <div class=\"flex justify-between items-center h-20\">
                    <a href=\"/\" class=\"flex-shrink-0 flex items-center\">
                        <div class=\"w-16 h-16 rounded-lg flex items-center justify-center\">
                            <img src=\"https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/logo-removebg.png\" alt=\"Logo\" class=\"w-12 h-12\">
                        </div>
                        <span class=\"ml-3 text-xl font-bold hidden sm:block\">Salvage Odyssey Auto</span>
                    </a>
                    <a href=\"/\" class=\"text-red-600 hover:text-red-700 font-semibold\">← Back to Home</a>
                </div>
            </div>
        </nav>
        <section class=\"bg-gradient-to-r from-red-600 to-red-700 text-white py-16\">
            <div class=\"max-w-4xl mx-auto px-4 sm:px-6 lg:px-8\">
                <h1 class=\"text-4xl md:text-5xl font-bold mb-4\">{title}</h1>
                <p class=\"text-lg text-red-100\">Published {published}</p>
            </div>
        </section>
        <section class=\"py-16 bg-gray-50\">
            <div class=\"max-w-4xl mx-auto px-4 sm:px-6 lg:px-8\">
                <div class=\"bg-white rounded-xl shadow-lg p-8 md:p-12\">
                    <div class=\"mb-8\">
                        <img id=\"main-image\" src=\"{main_image}\" alt=\"{title}\" class=\"w-full h-96 object-cover rounded-lg mb-6\">
                        <div class=\"flex gap-3 overflow-x-auto\">{thumbs_html}</div>
                    </div>
                    <div class=\"prose prose-lg max-w-none\">
                        <p class=\"text-gray-700 mb-6 leading-relaxed\">{summary}</p>
                        {details_paragraphs}
                        <div class=\"bg-red-50 border-l-4 border-red-600 p-6 mt-8\">
                            <p class=\"text-gray-900 font-semibold mb-2\">Need more information?</p>
                            <p class=\"text-gray-700\">Contact us at <a href=\"tel:0204136 3660\" class=\"text-red-600 font-bold\">020 4136 3660</a> for a free assessment.</p>
                        </div>
                    </div>
                </div>
            </div>
        </section>
        <section class=\"py-16 bg-red-600 text-white\">
            <div class=\"max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center\">
                <h2 class=\"text-3xl font-bold mb-4\">Ready to talk about your car?</h2>
                <a href=\"tel:0204136 3660\" class=\"inline-block bg-white text-red-600 px-8 py-3 rounded-lg font-semibold hover:bg-gray-100 transition-colors duration-200\">Call Us Now</a>
            </div>
        </section>
        <footer class=\"bg-black text-white py-12\">
            <div class=\"max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center\">
                <p class=\"text-gray-400\">© 2026 Salvage Odyssey Auto. All rights reserved.</p>
            </div>
        </footer>
    </div>
    <script>
        function setMainImage(index) {
            const imgs = [{image_js_list}];
            document.getElementById('main-image').src = imgs[index];
        }
    </script>
</body>
</html>""".format(
        title=post.title,
        published=post.created_at.strftime('%B %d, %Y') if post.created_at else '',
        main_image=main_image,
        thumbs_html=thumbs_html,
        summary=post.summary,
        details_paragraphs=details_paragraphs,
        image_js_list=image_js_list
    )
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)

def detect_device(user_agent: str) -> str:
    ua = (user_agent or '').lower()
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        return 'mobile'
    if 'ipad' in ua or 'tablet' in ua:
        return 'tablet'
    return 'desktop'
def register_visit(flask_request):
    db = SessionLocal()
    try:
        # get or create user UUID in session
        user_uuid = session.get('user_uuid')
        ip_header = flask_request.headers.get('X-Forwarded-For', flask_request.remote_addr)
        ip = ip_header.split(',')[0].strip() if ip_header else ''
        ua = flask_request.headers.get('User-Agent', '')
        device = detect_device(ua)
        ref = session.get('ref_source') or flask_request.args.get('ref') or 'direct'

        if not user_uuid:
            user_uuid = str(uuid.uuid4())
            session['user_uuid'] = user_uuid

        user = db.query(UserInfo).filter_by(user_uuid=user_uuid).first()
        now = datetime.utcnow()
        if user is None:
            user = UserInfo(
                user_uuid=user_uuid,
                ip=ip,
                user_agent=ua,
                device=device,
                visits_count=1,
                first_seen=now,
                last_seen=now,
            )
            db.add(user)
        else:
            user.visits_count = (user.visits_count or 0) + 1
            user.ip = ip
            user.user_agent = ua
            user.device = device
            user.last_seen = now

        # update referrer counts (one increment per visit)
        ref_row = db.query(Referrer).filter_by(name=ref).first()
        if ref_row is None:
            ref_row = Referrer(name=ref, count=1)
            db.add(ref_row)
        else:
            ref_row.count = (ref_row.count or 0) + 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
def send_contact_email(name, phone, email_addr, message_text):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError('GMAIL_USER and GMAIL_APP_PASSWORD must be set as environment variables')

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Website Contact: {name}'
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    body = f"Name: {name}\nPhone: {phone}\nEmail: {email_addr}\n\nMessage:\n{message_text}"
    msg.attach(MIMEText(body, 'plain'))

    # Use SMTP SSL with app password
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, [GMAIL_USER], msg.as_string())
services = [
    'Full Body Spray Painting',
    'Dent & Damage Repairs',
    'Rust Repairs',
    'Body Parts Fitting',
    'Cut & Polish',
    'Insurance Claims',
    'Wheel Alignment',
    'Puncture Repair',
    'Oil Services',
    'WOF Repair & Service',
    'Engine Repair',
    'Suspension Repair',
    'Battery Charging & Support'
]
service_menu = [
    {
      "name": 'Tyres',
      "link": '/services/tyres',
      "description": 'Wheel alignment, puncture repair, and tyre support for safe driving.',
      "items": [
        {"name": 'Wheel Alignment', "link": '/services/tyres#wheel-alignment'},
        {"name": 'Puncture Repair', "link": '/services/tyres#puncture-repair'},
        {"name": 'New Tyres', "link": '/services/tyres/shop'},
        {"name": 'Used Tyres', "link": '/services/tyres/used-tyres'}
      ]
    },
    {
      "name": 'Mechanical',
      "link": '/services/mechanical',
      "description": 'Oil, WOF, engine, suspension, battery and full mechanical repairs.',
      "items": [
        {"name": 'Oil Services', "link": '/services/mechanical#oil-services'},
        {"name": 'WOF Repair & Service', "link": '/services/mechanical#wof-service'},
        {"name": 'Engine Repair', "link": '/services/mechanical#engine-repair'},
        {"name": 'Suspension Repair', "link": '/services/mechanical#suspension-repair'},
        {"name": 'Battery Charging & Support', "link": '/services/mechanical#battery-charging'}
      ]
    },
    {
      "name": 'Panel & Paint',
      "link": '/services/panel-beater',
      "description": 'Full spray paint, dent repair, rust work, body parts fitting and polish services.',
      "items": [
        {"name": 'Full Body Spray', "link": '/services/panel-beater#full-body-spray'},
        {"name": 'Touch Up & Paint Fade Repair', "link": '/services/panel-beater#touch-up'},
        {"name": 'Damage & Dent Repairs', "link": '/services/panel-beater#dent-repairs'},
        {"name": 'Rust Repairs & Bodywork', "link": '/services/panel-beater#rust-repairs'},
        {"name": 'Body Parts Fitted', "link": '/services/panel-beater/body-parts'},
        {"name": 'Cut & Polish', "link": '/services/panel-beater/cut-polish'},
        {"name": 'Winz Quotes', "link": '/services/panel-beater#winz-quotes'},
        {"name": 'Fibreglass Headlight Polish', "link": '/services/panel-beater#headlight-polish'}
      ]
    }
]
servicesd = [
    {
      "icon": 'Paintbrush',
      "url": '/services/panel-beater',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/car%20painting.jpg',
      "title": 'Full Body Spray Painting',
      "description": 'Give your vehicle a fresh look with our custom spray painting services for cars, boats, trucks, motorcycles, and caravans.'
    },
    {
      "icon": 'Wrench',
      "url": '/services/panel-beater',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/bump_repair.jpg',
      "title": 'Damage & Dent Repairs',
      "description": 'We expertly restore your vehicle with precision and care, repairing dents, scratches, and collision damage.'
    },
    {
      "icon": 'Shield',
      "url": '/services/panel-beater',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/body_fix.jpg',
      "title": 'Rust Repairs & Bodywork',
      "description": 'We remove corrosion, repair rusted panels, and restore structural bodywork to protect your vehicle long-term.'
    },
    {
      "icon": 'Puzzle',
      "url": '/services/panel-beater/body-parts',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/repair.jpg',
      "title": 'Body Parts Fitted',
      "description": 'Whether you need new panels or other body parts, we ensure seamless fitting and a factory-finish appearance.'
    },
    {
      "icon": 'Sparkles',
      "url": '/services/panel-beater/cut-polish',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/blog/body_fitting.jpeg',
      "title": 'Cut & Polish',
      "description": 'We bring back the original shine and smooth finish to your vehicle’s paintwork with our expert cut and polish services.'
    },
    {
      "icon": 'Tire',
      "url": '/services/tyres',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/inside_tyre.jpeg',
      "title": 'Wheel Alignment & Puncture Repair',
      "description": 'Precision wheel alignment and fast puncture repair to keep your tyres wearing evenly and your vehicle driving safely.'
    },
    {
      "icon": 'Droplet',
      "url": '/services/mechanical',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/engine_repair.jpg',
      "title": 'Oil, WOF & Engine Repair',
      "description": 'Comprehensive mechanical care including oil services, WOF checks, engine repairs and routine maintenance.'
    },
    {
      "icon": 'BatteryCharging',
      "url": '/services/mechanical',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/battery.jpg',
      "title": 'Suspension & Battery Support',
      "description": 'Suspension repairs, battery charging and electrical support to keep your vehicle dependable on every journey.'
    }
]

    # {
    #   "icon": 'FileText',
    #   "url": '/services/panel-beater/insurance-claims',
    #   "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/insurance.jpg',
    #   "title": 'Insurance Claims',
    #   "description": 'We work with all major insurance companies to ensure smooth, hassle-free repair processes for your vehicle.'
    # }
reasons = [
    {
      "icon": "Award",
      "title": 'Expert Craftsmanship',
      "description": 'We deliver meticulous repairs and painting for all types of vehicles.'
    },
    {
      "icon": "Package",
      "title": 'Quality Materials',
      "description": 'We use premium paints and parts to ensure durable, long-lasting results.'
    },
    {
      "icon": "Clock",
      "title": 'Fast Turnaround',
      "description": 'We work efficiently to get your vehicle back on the road as quickly as possible without compromising on quality.'
    },
    {
      "icon": "Users",
      "title": 'Customer-First Approach',
      "description": "We provide clear communication and personalized service at every stage of your vehicle's repair."
    }
]
stats = [
    { "icon": "Users", "value": '1.2K+', "label": 'Happy Clients' },
    { "icon": "Car", "value": '2K+', "label": 'Vehicles Fixed' },
    { "icon": "Star", "value": '5+', "label": 'Client Rating' },
    { "icon": "Award", "value": '5+', "label": 'Years of Experience' }
]
DEFAULT_POSTS = [
    {
      "img_urls": ['https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/blog/body_kits.jpeg'],
      "title": 'Transform Your Ride with Body Kits and Spoilers',
      "slug": 'transform_your_ride_with_body_kits_and_spoilers',
      "summary": 'Learn how our body kit and spoiler installs can refresh your vehicle’s appearance and performance.',
      "details": 'Our specialist team handles every stage of body kit installation, from part selection to paint matching. We ensure a seamless fit and a finish that elevates your vehicle’s look.\n\nEnjoy improved aerodynamics, a sportier stance, and professional installation tailored to your car.',
      "url": '/blog/transform_your_ride_with_body_kits_and_spoilers',
      "created_at": datetime(2024, 11, 29)
    },
    {
      "img_urls": ['https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/blog/body_fitting.jpeg'],
      "title": 'Expert Body Parts Fitting & Panel Beating Services in Hamilton',
      "slug": 'expert_body_parts_fitting_panel_beating_services_in_hamilton',
      "summary": 'We restore damaged panels with precision to bring your car back to factory-fit condition.',
      "details": 'When your vehicle needs bodywork, our experienced team provides complete panel beating and body parts fitting solutions.\n\nWe repair damaged doors, fenders, bumpers, and more using high-quality parts and expert alignment techniques.',
      "url": '/blog/expert_body_parts_fitting_panel_beating_services_in_hamilton',
      "created_at": datetime(2024, 11, 23)
    }
]

def initialize_openai_client():
    openai.api_key = ""
def generate_response(prompt):
    
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content if response.choices else None
chat_histories = {}

@app.route('/')
def index():
    # Register the visit
    try:
        register_visit(request)
    except Exception as e:
        # don't break the site for analytics errors
        print('register_visit error:', e)

    db = SessionLocal()
    try:
        seed_default_posts(db)
        raw_posts = db.query(BlogPost).order_by(BlogPost.created_at.desc()).all()
        posts = []
        for post in raw_posts:
            posts.append({
                'title': post.title,
                'slug': post.slug,
                'img_url': post.img_urls,
                'created_at': post.created_at,
                'url': f'/blog/{post.slug}',
                'summary': post.summary
            })
    except Exception as e:
        print('index blog load error:', e)
        posts = []
    finally:
        db.close()

    return render_template('index.html', services=services, stats=stats, reasons=reasons, servicesd=servicesd, posts=posts, services_menu=service_menu)

@app.route('/facebook')
def facebook():
    session['ref_source'] = 'facebook'
    return redirect(url_for('index'))

@app.route('/insta')
def insta():
    session['ref_source'] = 'instagram'
    return redirect(url_for('index'))

@app.route('/other')
def other():
    session['ref_source'] = 'other'
    return redirect(url_for('index'))

@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    phone = request.form.get('phone')
    email_addr = request.form.get('email')
    message_text = request.form.get('message')

    try:
        send_contact_email(name, phone, email_addr, message_text)
        flash('Thanks! Your message was sent.', 'success')
    except Exception as e:
        print('send email error:', e)
        flash('Could not send message. Check server email configuration.', 'error')

    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    db = SessionLocal()
    try:
        total_users = db.query(UserInfo).count()
        total_visits = db.query(UserInfo).with_entities(func.sum(UserInfo.visits_count)).scalar() or 0
        ref_rows = db.query(Referrer).all()
        referrers = {r.name: r.count for r in ref_rows}
        users = db.query(UserInfo).order_by(UserInfo.last_seen.desc()).limit(200).all()
        seed_default_posts(db)
        blog_posts = db.query(BlogPost).order_by(BlogPost.created_at.desc()).all()
    finally:
        db.close()

    ref_labels = list(referrers.keys())
    ref_values = [referrers[k] for k in ref_labels]
    ref_colors = [source_color(name) for name in ref_labels]
    ref_items = [{'name': r.name, 'count': r.count, 'color': source_color(r.name)} for r in ref_rows]

    blog_posts_count = len(blog_posts)
    recent_posts = blog_posts[:3]

    return render_template('admin.html',
                            total_users=total_users,
                            total_visits=total_visits,
                            ref_labels=json.dumps(ref_labels),
                            ref_values=json.dumps(ref_values),
                            ref_colors=json.dumps(ref_colors),
                            ref_items=ref_items,
                            users=users,
                            blog_posts=blog_posts,
                            blog_posts_count=blog_posts_count,
                            recent_posts=recent_posts)

@app.route('/admin/blogs/add', methods=['POST'])
def add_blog_post():
    title = request.form.get('title', '').strip()
    slug = request.form.get('slug', '').strip() or slugify(title)
    summary = request.form.get('summary', '').strip()
    details = request.form.get('details', '').strip()
    img_urls_raw = request.form.get('img_urls', '').strip()
    img_urls = [u.strip() for u in img_urls_raw.replace(',', '\n').split('\n') if u.strip()]

    if not title:
        flash('Blog post title is required.', 'error')
        return redirect(url_for('admin'))
    if not img_urls:
        flash('At least one image URL is required.', 'error')
        return redirect(url_for('admin'))

    slug = slugify(slug)
    if not slug:
        flash('Could not generate a valid slug from the title.', 'error')
        return redirect(url_for('admin'))

    db = SessionLocal()
    try:
        existing = db.query(BlogPost).filter(BlogPost.slug == slug).first()
        if existing:
            flash('A blog post with that slug already exists. Choose a different title or slug.', 'error')
            return redirect(url_for('admin'))

        post = BlogPost(
            title=title,
            slug=slug,
            summary=summary,
            details=details,
            img_urls=json.dumps(img_urls),
            url=f'/blog/{slug}',
            created_at=datetime.utcnow()
        )
        db.add(post)
        db.commit()
        generate_blog_html(post)
        flash('Blog post added successfully.', 'success')
    except Exception as e:
        db.rollback()
        print('add blog error:', e)
        flash('Could not save blog post. Please try again.', 'error')
    finally:
        db.close()

    return redirect(url_for('admin'))

@app.route('/admin/blogs/delete/<int:blog_id>', methods=['POST'])
def delete_blog_post(blog_id):
    db = SessionLocal()
    try:
        post = db.query(BlogPost).filter(BlogPost.id == blog_id).first()
        if post:
            filename = os.path.join('templates', 'blog', f'{post.slug}.html')
            if os.path.exists(filename):
                os.remove(filename)
            db.delete(post)
            db.commit()
            flash('Blog post deleted successfully.', 'success')
        else:
            flash('Blog post not found.', 'error')
    except Exception as e:
        db.rollback()
        print('delete blog error:', e)
        flash('Could not delete blog post. Please try again.', 'error')
    finally:
        db.close()

    return redirect(url_for('admin'))

@app.route('/admin/data')
def admin_data():
    db = SessionLocal()
    try:
        referrers = {r.name: r.count for r in db.query(Referrer).all()}
    finally:
        db.close()
    return jsonify(referrers)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_tires_from_csv():
    tires_file = os.path.join(app.config['UPLOAD_FOLDER'], 'tyres.csv')
    tires = []
    if os.path.exists(tires_file):
        try:
            with open(tires_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                tires = list(reader)
        except Exception as e:
            print(f"Error reading tires CSV: {e}")
    return tires

@app.route('/blog/body-kits-and-spoilers')
def blog_body_kits():
    return render_template('blog/body-kits-spoilers.html')

@app.route('/blog/body-parts-fitting')
def blog_body_parts():
    return render_template('blog/body-parts-fitting.html')

@app.route('/blog/<slug>')
def blog_post(slug):
    template_name = f'blog/{slug}.html'
    filename = os.path.join('templates', template_name)
    if not os.path.exists(filename):
        db = SessionLocal()
        try:
            post = db.query(BlogPost).filter(BlogPost.slug == slug).first()
            if post:
                generate_blog_html(post)
            else:
                abort(404)
        finally:
            db.close()

    try:
        return render_template(template_name)
    except Exception:
        abort(404)

@app.route('/services/panel-beater')
def panel_beater():
    return render_template('services/panel-beater.html')

@app.route('/services/panel-beater/body-parts')
def panel_beater_body_parts():
    return render_template('services/panel-beater-body-parts.html')

@app.route('/services/panel-beater/spoilers')
def panel_beater_spoilers():
    return render_template('services/panel-beater-spoilers.html')

@app.route('/services/panel-beater/cut-polish')
def panel_beater_cut_polish():
    return render_template('services/panel-beater-cut-polish.html')

@app.route('/services/panel-beater/cut-and-polish')
def panel_beater_cut_and_polish():
    return redirect(url_for('panel_beater_cut_polish'))

@app.route('/services/mechanical')
def mechanical_services():
    return render_template('services/mechanical.html')

@app.route('/services/tyres')
def tyres():
    return render_template('services/tyres.html')

@app.route('/services/tyres/shop')
def tyres_shop():
    return render_template('services/tyres-shop.html')

@app.route('/services/tyres/used-tyres')
def used_tyres():
    tires = load_tires_from_csv()
    sizes = sorted(list(set([t.get('size', '') for t in tires if t.get('size')])))
    return render_template('services/used-tyres.html', tires=tires, sizes=sizes)

@app.route('/services/tyres/used-tyres/filter', methods=['POST'])
def filter_tires():
    size = request.form.get('size', '')
    tires = load_tires_from_csv()

    if size:
        tires = [t for t in tires if t.get('size', '').lower() == size.lower()]

    return render_template('services/used-tyres-results.html', tires=tires, selected_size=size)

@app.route('/admin/tyres/upload', methods=['GET', 'POST'])
def upload_tyres():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename('tyres.csv')
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('Tyres CSV uploaded successfully!', 'success')
            return redirect(url_for('used_tyres'))
        else:
            flash('Only CSV files are allowed', 'error')
            return redirect(request.url)

    return render_template('admin/upload-tyres.html')

@app.route('/services/wrecked-cars')
def wrecked_cars():
    return render_template('services/wrecked-cars.html')

@app.route('/services/wrecked-cars/submit', methods=['POST'])
def submit_wrecked_car():
    name = request.form.get('name')
    phone = request.form.get('phone')
    email_addr = request.form.get('email')
    car_make = request.form.get('car_make')
    car_model = request.form.get('car_model')
    car_year = request.form.get('car_year')
    condition = request.form.get('condition')
    message = request.form.get('message')

    try:
        body = f"""
New Wrecked Car Submission:

Name: {name}
Phone: {phone}
Email: {email_addr}

Vehicle Details:
Make: {car_make}
Model: {car_model}
Year: {car_year}
Condition: {condition}

Message: {message}
        """
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Wrecked Car Submission from {name}'
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [GMAIL_USER], msg.as_string())

        flash('Thanks! Your wrecked car submission was received. We\'ll contact you soon.', 'success')
    except Exception as e:
        print('send email error:', e)
        flash('Could not send submission. Please try again.', 'error')

    return redirect(url_for('wrecked_cars'))
@app.route('/contact_page')
def contacts():
    return render_template('contact.html')


@app.route('/team')
def team():
    return render_template('team.html')

@app.route('/panel-beaters-hamilton')
def seo_panel_beaters():
    return render_template('panel-beaters-hamilton.html')

@app.route('/car-painting-hamilton')
def seo_car_painting():
    return render_template('car-painting-hamilton.html')

@app.route('/sell-wrecked-car-hamilton')
def seo_sell_wrecked():
    return render_template('sell-wrecked-car-hamilton.html')

@app.route('/used-tyres-hamilton')
def seo_used_tyres():
    tires = load_tires_from_csv()
    sizes = sorted(list(set([t.get('size', '') for t in tires if t.get('size')])))
    return render_template('used-tyres-hamilton.html', tires=tires, sizes=sizes)

@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    base_urls = [
        url_for('index', _external=True),
        url_for('panel_beater', _external=True),
        url_for('tyres', _external=True),
        url_for('wrecked_cars', _external=True),
        url_for('contacts', _external=True),
        url_for('blog_body_kits', _external=True),
        url_for('blog_body_parts', _external=True),
        url_for('panel_beater_body_parts', _external=True),
        url_for('panel_beater_spoilers', _external=True),
        url_for('panel_beater_cut_polish', _external=True),
        url_for('mechanical_services', _external=True),
        url_for('tyres_shop', _external=True),
        url_for('used_tyres', _external=True),
        url_for('seo_panel_beaters', _external=True),
        url_for('seo_car_painting', _external=True),
        url_for('seo_sell_wrecked', _external=True),
        url_for('seo_used_tyres', _external=True),
    ]

    xml_items = ''
    for u in base_urls:
        xml_items += f"<url><loc>{u}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>\n"

    sitemap_xml = f'<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap_xml += xml_items
    sitemap_xml += '</urlset>'

    response = make_response(sitemap_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/ai/chatbot', methods=['POST'])
def ai_chatbot():
    user_message = request.json.get('message')
    response = generate_response(user_message)
    return jsonify({'response': response})
@app.route('/chatbot')
def chatbot(foldername):
    response = generate_response("hi")
    return render_template('chatbot.html', response=response)
@app.after_request
def add_watermark(response):
    if "text/html" in response.content_type:
        content = response.get_data(as_text=True)
        widget = """
<div class="fixed left-0 top-1/2 -translate-y-1/2 flex flex-col gap-2 z-50">
    <a href="https://www.facebook.com/salvageodysseyauto"
    target="_blank"
    class="bg-blue-600 text-white p-3 rounded-r-lg shadow-lg
              hover:px-5 hover:bg-blue-700 transition-all duration-300
              flex items-center gap-2 group">

        <!-- icon -->
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
        </svg>

        <!-- text (only shows on hover) -->
        <span class="hidden group-hover:block text-sm font-semibold">
            Facebook
        </span>

    </a>
    <a href="https://www.instagram.com/odysseyauto.mobile393/"
    target="_blank"
    class="bg-gradient-to-tr from-[#f56040] via-[#c13584] to-[#405de6]
              text-white p-3 rounded-r-lg shadow-lg
              hover:px-5 transition-all duration-300
              flex items-center gap-2 group">

        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M7.75 2h8.5A5.75 5.75 0 0 1 22 7.75v8.5A5.75 5.75 0 0 1 16.25 22h-8.5A5.75 5.75 0 0 1 2 16.25v-8.5A5.75 5.75 0 0 1 7.75 2zm4.25 5.5a4.75 4.75 0 1 0 0 9.5 4.75 4.75 0 0 0 0-9.5zm0 1.75a3 3 0 1 1 0 6 3 3 0 0 1 0-6zm4.75-.88a1.13 1.13 0 1 0 0-2.25 1.13 1.13 0 0 0 0 2.25z"/>
        </svg>

        <span class="hidden group-hover:block text-sm font-semibold">
            Instagram
        </span>
    </a>
    <a href="https://maps.google.com/?q=109+Colombo+Street+Frankton+Hamilton"
    target="_blank"
    class="bg-green-600 text-white p-3 rounded-r-lg shadow-lg
              hover:px-5 hover:bg-green-700 transition-all duration-300
              flex items-center gap-2 group">

        <svg class="w-5 h-5 fill-current" viewBox="0 0 24 24">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z"/>
        </svg>

        <span class="hidden group-hover:block text-sm font-semibold">
            Location
        </span>
    </a>
    <a href="tel:02041363660"
    class="bg-red-600 text-white p-3 rounded-r-lg shadow-lg
              hover:px-5 hover:bg-red-700 transition-all duration-300
              flex items-center gap-2 group">

        <svg class="w-5 h-5 fill-current" viewBox="0 0 24 24">
            <path d="M6.62 10.79a15.05 15.05 0 006.59 6.59l2.2-2.2a1 1 0 011-.24c1.12.37 2.33.57 3.59.57a1 1 0 011 1V21a1 1 0 01-1 1C10.07 22 2 13.93 2 4a1 1 0 011-1h3.5a1 1 0 011 1c0 1.26.2 2.47.57 3.59a1 1 0 01-.25 1l-2.2 2.2z"/>
        </svg>

        <span class="hidden group-hover:block text-sm font-semibold">
            Call Us
        </span>
    </a>
    <a href="mailto:odyssey.auto.mobile393@gmail.com"
    class="bg-gray-700 text-white p-3 rounded-r-lg shadow-lg
              hover:px-5 hover:bg-gray-800 transition-all duration-300
              flex items-center gap-2 group">

        <svg class="w-5 h-5 fill-current" viewBox="0 0 24 24">
            <path d="M20 4H4a2 2 0 00-2 2v.01l10 6.99 10-6.99V6a2 2 0 00-2-2zm0 4.24l-8.4 5.88a1 1 0 01-1.2 0L2 8.24V18a2 2 0 002 2h16a2 2 0 002-2V8.24z"/>
        </svg>

        <span class="hidden group-hover:block text-sm font-semibold">
            Email Us
        </span>
    </a>
</div>
"""
        content = content.replace("</body>", widget + "</body>")
        response.set_data(content)

    return response