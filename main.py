import os
import json
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from werkzeug.utils import secure_filename
import csv
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, func
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
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
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
        ip = flask_request.headers.get('X-Forwarded-For', flask_request.remote_addr)
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
    'Insurance Claims'
]
servicesd = [
    {
      "icon": 'Paintbrush',
      "url": '/services/panel-beater/spoilers',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/car%20painting.jpg',
      "title": 'Full Body Spray Painting',
      "description": 'Give your vehicle a fresh look with our custom spray painting services. We use high-quality paints and offer a wide range of color options.'
    },
    {
      "icon": 'Wrench',
      "url": '/services/panel-beater/body-parts',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/bump_repair.jpg',
      "title": 'Dent & Damage Repairs',
      "description": 'We expertly restore your vehicle with precision and utmost care, from minor dents to extensive body damage.'
    },
    {
      "icon": 'Shield',
      "url": '/services/panel-beater/rust-repairs',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/body_fix.jpg',
      "title": 'Rust Repairs',
      "description": "Don't let rust compromise your vehicle's appearance or safety. We handle rust removal and prevention to extend your vehicle's lifespan."
    },
    {
      "icon": 'Puzzle',
      "url": '/services/panel-beater/body-parts',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/services/repair.jpg',
      "title": 'Body Parts Fitting',
      "description": 'Whether you need new panels or other body parts, we ensure seamless fitting and a factory-finish appearance.'
    },
    {
      "icon": 'Sparkles',
      "url": '/services/panel-beater/cut-and-polish',
      "img": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/blog/body_fitting.jpeg',
      "title": 'Cut & Polish',
      "description": "We bring back the original shine and smooth finish to your vehicle's paintwork with our professional cut and polish services."
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
posts = [
    {
      "img_url": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/blog/body_kits.jpeg',
      "title": 'Transform Your Ride with Body Kits and Spoilers',
      "date": 'November 29, 2024'
    },
    {
      "img_url": 'https://zwlhdzpybfsqpmzcslhc.supabase.co/storage/v1/object/public/images/blog/body_fitting.jpeg',
      "title": 'Expert Body Parts Fitting & Panel Beating Services in Hamilton',
      "date": 'November 23, 2024'
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

    return render_template('index.html', services=services, stats=stats, reasons=reasons, servicesd=servicesd, posts=posts)

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
        referrers = {r.name: r.count for r in db.query(Referrer).all()}
        users = db.query(UserInfo).order_by(UserInfo.last_seen.desc()).limit(200).all()
    finally:
        db.close()

    ref_labels = list(referrers.keys())
    ref_values = [referrers[k] for k in ref_labels]

    # Blog posts summary (from in-memory posts list)
    try:
        blog_posts_count = len(posts)
        recent_posts = posts[:3]
    except Exception:
        blog_posts_count = 0
        recent_posts = []

    # Tyres summary (from CSV upload)
    try:
        tyres = load_tires_from_csv()
        tyres_count = len(tyres)
        recent_tyres = tyres[:3]
    except Exception:
        tyres_count = 0
        recent_tyres = []

    return render_template('admin.html',
                            total_users=total_users,
                            total_visits=total_visits,
                            ref_labels=json.dumps(ref_labels),
                            ref_values=json.dumps(ref_values),
                            users=users,
                            blog_posts_count=blog_posts_count,
                            recent_posts=recent_posts,
                            tyres_count=tyres_count,
                            recent_tyres=recent_tyres)

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
<a href="https://www.facebook.com/salvageodysseyauto"
   target="_blank"
   class="fixed left-0 top-[50%] -translate-y-1/2 bg-blue-600 text-white p-3 rounded-r-lg shadow-lg hover:px-5 hover:bg-blue-700 transition-all duration-300 flex items-center gap-2 group">

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
   class="fixed left-0 top-[45%] -translate-y-1/2 
          bg-gradient-to-tr from-[#f56040] via-[#c13584] to-[#405de6]
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
   class="fixed left-0 top-[55%] -translate-y-1/2 
          bg-green-600 text-white p-3 rounded-r-lg shadow-lg
          hover:px-5 hover:bg-green-700
          transition-all duration-300
          flex items-center gap-2 group">

    <svg class="w-5 h-5 fill-current" viewBox="0 0 24 24">
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z"/>
    </svg>

    <span class="hidden group-hover:block text-sm font-semibold">
        Location
    </span>
</a>
<a href="tel:02041363660"
   class="fixed left-0 top-[60%] -translate-y-1/2
          bg-red-600 text-white p-3 rounded-r-lg shadow-lg
          hover:px-5 hover:bg-red-700
          transition-all duration-300
          flex items-center gap-2 group">

    <svg class="w-5 h-5 fill-current" viewBox="0 0 24 24">
        <path d="M6.62 10.79a15.05 15.05 0 006.59 6.59l2.2-2.2a1 1 0 011-.24c1.12.37 2.33.57 3.59.57a1 1 0 011 1V21a1 1 0 01-1 1C10.07 22 2 13.93 2 4a1 1 0 011-1h3.5a1 1 0 011 1c0 1.26.2 2.47.57 3.59a1 1 0 01-.25 1l-2.2 2.2z"/>
    </svg>

    <span class="hidden group-hover:block text-sm font-semibold">
        Call Us
    </span>
</a>
<a href="mailto:odyssey.auto.mobile393@gmail.com"
   class="fixed left-0 top-[65%] -translate-y-1/2
          bg-gray-700 text-white p-3 rounded-r-lg shadow-lg
          hover:px-5 hover:bg-gray-800
          transition-all duration-300
          flex items-center gap-2 group">

    <svg class="w-5 h-5 fill-current" viewBox="0 0 24 24">
        <path d="M20 4H4a2 2 0 00-2 2v.01l10 6.99 10-6.99V6a2 2 0 00-2-2zm0 4.24l-8.4 5.88a1 1 0 01-1.2 0L2 8.24V18a2 2 0 002 2h16a2 2 0 002-2V8.24z"/>
    </svg>

    <span class="hidden group-hover:block text-sm font-semibold">
        Email Us
    </span>
</a>
<!-- Chat Button -->
<button id="chat-open"
style="position:fixed;bottom:20px;right:20px;z-index:9999;
background:#dc2626;color:white;border:none;
padding:12px 14px;border-radius:999px;
box-shadow:0 10px 25px rgba(0,0,0,.2);cursor:pointer">
    <i data-lucide="bot"></i>
</button>

<!-- Chat Box -->
<div id="chat-box"
style="display:none;position:fixed;bottom:80px;right:20px;
z-index:9999;width:380px;height:520px;
background:#18181b;color:white;border-radius:16px;
overflow:hidden;box-shadow:0 20px 40px rgba(0,0,0,.3)">

    <div style="display:flex;justify-content:space-between;
    padding:12px;border-bottom:1px solid #3f3f46">
        <div style="display:flex;gap:8px;align-items:center">
            <i data-lucide="bot"></i>
            <span>AI Assistant</span>
        </div>
        <button id="chat-close" style="background:none;border:none;color:white;cursor:pointer">
            <i data-lucide="x"></i>
        </button>
    </div>

    <iframe
        src="https://www.salvageodysseyauto.co.nz/chatbot/project_web"
        style="width:100%;height:100%;border:none;background:white">
    </iframe>
</div>
<script src="https://unpkg.com/lucide@latest"></script>
<script>
    lucide.createIcons();
</script>
<script>
window.addEventListener("load", function(){
    const openBtn = document.getElementById("chat-open");
    const closeBtn = document.getElementById("chat-close");
    const chatBox = document.getElementById("chat-box");

    if(openBtn && closeBtn && chatBox){
        openBtn.onclick = () => {
            openBtn.style.display = "none";
            chatBox.style.display = "block";
        };

        closeBtn.onclick = () => {
            chatBox.style.display = "none";
            openBtn.style.display = "block";
        };
    }

    if (window.lucide) {
        lucide.createIcons();
    }
});
</script>

"""
        content = content.replace("</body>", widget + "</body>")
        response.set_data(content)

    return response