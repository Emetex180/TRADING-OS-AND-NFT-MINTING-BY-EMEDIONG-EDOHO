from flask import Flask, render_template, request, redirect, flash, session, send_from_directory, jsonify, url_for, send_file
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, ImageDraw, ImageFont
import io
import plotly.graph_objects as go
import plotly.io as py
import csv
from flask_mail import Mail, Message
import uuid
from datetime import datetime
from collections import Counter
import json

app = Flask(__name__)

# Database config - using only SQLite3
app.secret_key = os.urandom(24)

# Upload config
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = "emediongedoho1@gmail.com"
app.config['MAIL_PASSWORD'] = "dxwajrsipzydmutp"
app.config['MAIL_DEFAULT_SENDER'] = ("Elite Trader Journal", "emediongedoho1@gmail.com")
mail = Mail(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        email TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        pair TEXT,
        result TEXT,
        entry FLOAT,
        exit FLOAT,
        notes TEXT,
        screenshot TEXT,
        date TEXT,
        emotions TEXT,
        rule_violations TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS playbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        setup_name TEXT,
        notes TEXT,
        screenshot TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Enhanced journals table for sharing feature
    cursor.execute('''CREATE TABLE IF NOT EXISTS journals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        journal_title TEXT,
        trade_data TEXT,
        share_token TEXT UNIQUE,
        is_shared INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Enhanced feedback table
    cursor.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_id INTEGER,
        mentor_id INTEGER,
        mentor_name TEXT,
        feedback_text TEXT,
        created_at TEXT,
        FOREIGN KEY(journal_id) REFERENCES journals(id)
    )''')

    # ✅ Automatically create default admin if not exists
    cursor.execute("SELECT * FROM users WHERE is_admin=1")
    admin_exists = cursor.fetchone()
    if not admin_exists:
        hashed_password = generate_password_hash("admin123")
        cursor.execute("INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
                       ("admin", "emediongedoho1@gmail.com", hashed_password, 1))
        conn.commit()
    conn.close()

@app.context_processor
def inject_user():
    return dict(session=session)

# =====================================================
#  Home
# =====================================================
@app.route('/')
def home():
    return render_template("index.html")

# =====================================================
#  Register
# =====================================================
@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect("database.db")
        try:
            conn.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                         (username, email, hashed_password))
            conn.commit()
            conn.close()

            # Save email to CSV
            file_exists = os.path.isfile("emails.csv")
            with open("emails.csv", mode="a", newline="") as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(["Username", "Email"])
                writer.writerow([username, email])

            # Send welcome email
            msg_user = Message(
                "Welcome to EliteTrader Journal!", 
                recipients=[email]
            )
            msg_user.html = f"""
            <h2>Welcome to EliteTrader Journal, {username}!</h2>
            <p>We're thrilled to have you join our trading community! 🎉</p>

            <p>At EliteTrader Journal, you'll gain access to:</p>
            <ul>
                <li>Exclusive trading insights and strategies</li>
                <li>Community discussions with experienced traders</li>
                <li>Tools to track and analyze your trades</li>
                <li>Educational resources to grow your skills</li>
            </ul>

            <p>We’re excited to support you on your trading journey. Let’s reach new heights together!</p>

            <p>Happy trading,<br>
            <strong>The EliteTrader Team</strong></p>
            """
            mail.send(msg_user)


            # Notify admin
            msg_admin = Message(f"New Registration: {username}", recipients=[app.config['MAIL_USERNAME']])
            msg_admin.body = f"New user registered to Elite Trader Journal: {username} ({email})"
            mail.send(msg_admin)

            flash("Registration successful! Check your email.", "success")
            return redirect("/login")

        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
            conn.close()

    return render_template("register.html")

# =====================================================
#  Login
# =====================================================
@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, password, is_admin FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session["user_id"] = user[0]
            session["username"] = user[1]
            flash("Login successful!", "success")
            return redirect("/dashboard")
        else:
            flash("Invalid credentials.", "danger")
    return render_template("login.html")

# =====================================================
#  Dashboard
# =====================================================
@app.route('/dashboard', methods=["GET"])
def dashboard():
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    sort_by = request.args.get("sort_by", "date")
    sort_column = {
        "date": "date",
        "pair": "pair",
        "result": "result"
    }.get(sort_by, "date")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT pair, result, entry, exit, notes, screenshot, date, id, emotions, rule_violations FROM trades WHERE user_id = ? ORDER BY {sort_column} DESC", (session["user_id"],))
    trades = cursor.fetchall()

    win_loss = [1 if trade[1].lower() == 'win' else 0 for trade in trades]
    win_count = win_loss.count(1)
    loss_count = win_loss.count(0)

    # Stats
    total_trades = len(trades)
    win_rate = (win_count / total_trades * 100) if total_trades else 0
    pl_list = [(trade[3] - trade[2]) if trade[1].lower() == 'win' else (trade[3] - trade[2]) for trade in trades]
    total_pl = sum(pl_list)

    # Insights
    emotions = [trade[8] for trade in trades if trade[8]]
    violations = [trade[9] for trade in trades if trade[9]]
    pairs = [trade[0] for trade in trades]
    
    results_by_pair = {}
    for trade in trades:
        pair = trade[0]
        result = trade[1].lower()
        results_by_pair.setdefault(pair, []).append(result)
    
    best_pair = None
    worst_pair = None
    best_rate = -1
    worst_rate = 2
    for pair, results in results_by_pair.items():
        rate = results.count('win') / len(results)
        if rate > best_rate:
            best_rate = rate
            best_pair = pair
        if rate < worst_rate:
            worst_rate = rate
            worst_pair = pair
            
    insights = {
        'common_emotion': Counter(emotions).most_common(1)[0][0] if emotions else None,
        'common_violation': Counter(violations).most_common(1)[0][0] if violations else None,
        'most_traded_pair': Counter(pairs).most_common(1)[0][0] if pairs else None,
        'best_pair': best_pair,
        'worst_pair': worst_pair,
        'suggestion': None
    }
    
    if insights['common_emotion']:
        insights['suggestion'] = f"Watch out for trading when feeling {insights['common_emotion'].lower()}!"
    elif insights['common_violation']:
        insights['suggestion'] = f"Review trades with rule violation: {insights['common_violation']}"
    elif insights['best_pair']:
        insights['suggestion'] = f"Focus on your best pair: {insights['best_pair']}"

    # Chart
    fig = go.Figure(data=[
        go.Bar(name="Wins", x=["Wins"], y=[win_count], marker=dict(color="green")),
        go.Bar(name="Losses", x=["Losses"], y=[loss_count], marker=dict(color="red"))
    ])
    fig.update_layout(
        title="Your Performance (Win/Loss)",
        xaxis_title="Outcome",
        yaxis_title="Count",
        barmode='group'
    )

    graph = py.to_html(fig, full_html=False)
    
    # Gamification
    win_streak = 0
    max_streak = 0
    badges = []
    streak = 0
    for trade in trades:
        if trade[1].lower() == 'win':
            streak += 1
            if streak > max_streak:
                max_streak = streak
        else:
            streak = 0
    win_streak = streak
    if win_streak >= 5:
        badges.append("🔥 5+ Win Streak")
    if len(trades) >= 10:
        badges.append("🏅 10 Trades Logged")
    if insights['best_pair']:
        badges.append(f"⭐ Best Pair: {insights['best_pair']}")
        
    gamification = {
        'win_streak': win_streak,
        'badges': badges
    }
    conn.close()
    return render_template("dashboard.html", trades=trades, graph=graph, insights=insights, gamification=gamification)

# =====================================================
#  Log Trade
# =====================================================
@app.route('/log_trade', methods=["GET", "POST"])
def log_trade():
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    if request.method == "POST":
        pair = request.form["pair"]
        result = request.form["result"]
        entry = float(request.form["entry"])
        exit_price = float(request.form["exit"])
        notes = request.form["notes"]
        screenshot_filename = None
        date = request.form["date"]
        emotions = request.form.get("emotions", "")
        rule_violations = request.form.get("rule_violations", "")

        if "screenshot" in request.files:
            file = request.files["screenshot"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                screenshot_filename = filename

        conn = sqlite3.connect("database.db")
        conn.execute("""INSERT INTO trades 
            (user_id, pair, result, entry, exit, notes, screenshot, date, emotions, rule_violations) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session["user_id"], pair, result, entry, exit_price, notes, screenshot_filename, date, emotions, rule_violations))
        conn.commit()
        conn.close()

        flash("Trade logged successfully!", "success")
        return redirect("/dashboard")

    return render_template("log_trade.html")

# =====================================================
#  Edit Trade
# =====================================================
@app.route('/edit_trade/<int:trade_index>', methods=["GET", "POST"])
def edit_trade(trade_index):
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM trades WHERE user_id = ? ORDER BY date DESC", (session["user_id"],))
    trade_ids = [row[0] for row in cursor.fetchall()]
    if trade_index >= len(trade_ids):
        conn.close()
        flash("Trade not found.", "danger")
        return redirect(url_for("dashboard"))
    trade_id = trade_ids[trade_index]

    if request.method == "POST":
        pair = request.form["pair"]
        result = request.form["result"]
        entry = float(request.form["entry"])
        exit_price = float(request.form["exit"])
        notes = request.form["notes"]
        screenshot_filename = None
        date = request.form["date"]
        emotions = request.form.get("emotions", "")
        rule_violations = request.form.get("rule_violations", "")
        
        if "screenshot" in request.files:
            file = request.files["screenshot"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                screenshot_filename = filename
                
        if screenshot_filename:
            cursor.execute("UPDATE trades SET pair=?, result=?, entry=?, exit=?, notes=?, screenshot=?, date=?, emotions=?, rule_violations=? WHERE id=?",
                           (pair, result, entry, exit_price, notes, screenshot_filename, date, emotions, rule_violations, trade_id))
        else:
            cursor.execute("UPDATE trades SET pair=?, result=?, entry=?, exit=?, notes=?, date=?, emotions=?, rule_violations=? WHERE id=?",
                           (pair, result, entry, exit_price, notes, date, emotions, rule_violations, trade_id))
        conn.commit()
        conn.close()
        flash("Trade updated successfully!", "success")
        return redirect(url_for("dashboard"))

    cursor.execute("SELECT pair, result, entry, exit, notes, screenshot, date, emotions, rule_violations FROM trades WHERE id=?", (trade_id,))
    trade = cursor.fetchone()
    conn.close()
    return render_template("edit_trade.html", trade=trade, trade_index=trade_index)

# =====================================================
#  Delete Trade
# =====================================================
@app.route('/delete_trade/<int:trade_index>', methods=["POST"])
def delete_trade(trade_index):
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM trades WHERE user_id = ? ORDER BY date DESC", (session["user_id"],))
    trade_ids = [row[0] for row in cursor.fetchall()]
    if trade_index >= len(trade_ids):
        conn.close()
        flash("Trade not found.", "danger")
        return redirect(url_for("dashboard"))
    trade_id = trade_ids[trade_index]
    cursor.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    conn.commit()
    conn.close()
    flash("Trade deleted successfully!", "success")
    return redirect(url_for("dashboard"))

# =====================================================
#  Playbooks
# =====================================================
@app.route('/playbooks', methods=["GET", "POST"])
def playbooks():
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    if request.method == "POST":
        setup_name = request.form["setup_name"]
        notes = request.form["notes"]
        screenshot_filename = None
        if "screenshot" in request.files:
            file = request.files["screenshot"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                screenshot_filename = filename
        cursor.execute(
            "INSERT INTO playbooks (user_id, setup_name, notes, screenshot) VALUES (?, ?, ?, ?)",
            (session["user_id"], setup_name, notes, screenshot_filename)
        )
        conn.commit()
        flash("Playbook saved!", "success")

    cursor.execute("SELECT id, setup_name, notes, screenshot FROM playbooks WHERE user_id = ?", (session["user_id"],))
    playbooks = cursor.fetchall()
    conn.close()
    return render_template("playbooks.html", playbooks=playbooks)

# =====================================================
#  Edit Playbook
# =====================================================
@app.route('/edit_playbook/<int:pb_id>', methods=["GET", "POST"])
def edit_playbook(pb_id):
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    if request.method == "POST":
        setup_name = request.form["setup_name"]
        notes = request.form["notes"]
        screenshot_filename = None
        if "screenshot" in request.files:
            file = request.files["screenshot"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                screenshot_filename = filename
        if screenshot_filename:
            cursor.execute("UPDATE playbooks SET setup_name=?, notes=?, screenshot=? WHERE id=? AND user_id=?",
                           (setup_name, notes, screenshot_filename, pb_id, session["user_id"]))
        else:
            cursor.execute("UPDATE playbooks SET setup_name=?, notes=? WHERE id=? AND user_id=?",
                           (setup_name, notes, pb_id, session["user_id"]))
        conn.commit()
        conn.close()
        flash("Playbook updated!", "success")
        return redirect("/playbooks")

    cursor.execute("SELECT id, setup_name, notes, screenshot FROM playbooks WHERE id=? AND user_id=?", (pb_id, session["user_id"]))
    playbook = cursor.fetchone()
    conn.close()
    if not playbook:
        flash("Playbook not found.", "danger")
        return redirect("/playbooks")
    return render_template("edit_playbook.html", playbook=playbook)

# =====================================================
#  Delete Playbook
# =====================================================
@app.route('/delete_playbook/<int:pb_id>', methods=["POST"])
def delete_playbook(pb_id):
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT screenshot FROM playbooks WHERE id=? AND user_id=?", (pb_id, session["user_id"]))
    row = cursor.fetchone()
    if row and row[0]:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], row[0])
        if os.path.exists(file_path):
            os.remove(file_path)
    cursor.execute("DELETE FROM playbooks WHERE id=? AND user_id=?", (pb_id, session["user_id"]))
    conn.commit()
    conn.close()

    flash("Playbook deleted!", "success")
    return redirect("/playbooks")

# =====================================================
#  Download Playbook
# =====================================================
@app.route('/download_playbook/<filename>')
def download_playbook(filename):
    # Find playbook info by filename
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT setup_name, notes FROM playbooks WHERE screenshot=?", (filename,))
    pb = cursor.fetchone()
    conn.close()
    if not pb:
        return "Playbook not found", 404
    setup_name, notes = pb

    # Load screenshot and logo
    screenshot_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    logo_path = os.path.join('static', 'image', 'elite logo.jpeg')
    try:
        screenshot = Image.open(screenshot_path).convert('RGBA')
    except Exception:
        return "Screenshot not found", 404
    try:
        logo = Image.open(logo_path).convert('RGBA')
    except Exception:
        logo = None

    # Card design parameters
    card_width = max(screenshot.width + 60, 500)
    card_height = screenshot.height + 220
    # Brand colors
    card_bg = (224, 242, 254, 255)  # #e0f2fe
    card_border = (14, 165, 233, 255)  # #0ea5e9
    title_color = '#0ea5e9'  # blue
    notes_color = '#334155'  # dark blue
    footer_color = '#0ea5e9'  # blue
    canvas = Image.new('RGBA', (card_width, card_height), card_bg)
    draw = ImageDraw.Draw(canvas)

    # Draw border
    border_thickness = 6
    draw.rounded_rectangle([(0,0),(card_width-1,card_height-1)], radius=28, outline=card_border, width=border_thickness)

    # Paste logo top left
    if logo:
        logo_size = 70
        logo = logo.resize((logo_size, logo_size))
        canvas.paste(logo, (30, 30), logo)

    # Setup name as title
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    try:
        font_title = ImageFont.truetype(font_path, 32)
        font_notes = ImageFont.truetype(font_path, 20)
    except Exception:
        font_title = font_notes = None
    draw.text((120, 38), setup_name, fill=title_color, font=font_title)

    # Notes/message below title
    draw.text((120, 80), notes, fill=notes_color, font=font_notes)

    # Paste screenshot centered below notes
    img_x = int((card_width - screenshot.width) / 2)
    img_y = 140
    canvas.paste(screenshot, (img_x, img_y))

    # Footer message
    footer_text = "EliteTrader Playbook • Share your best setups!"
    try:
        font_footer = ImageFont.truetype(font_path, 18)
    except Exception:
        font_footer = None
    draw.text((30, card_height-40), footer_text, fill=footer_color, font=font_footer)

    # Save to buffer and send as image
    buf = io.BytesIO()
    canvas.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png', as_attachment=True, download_name=f'ElitePlaybook_{setup_name}.png')

# =====================================================
#  Import Trades from CSV
# =====================================================
@app.route('/import_trades', methods=["GET", "POST"])
def import_trades():
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    if request.method == "POST":
        if "csv_file" not in request.files:
            flash("No file uploaded.", "danger")
            return redirect("/import_trades")
        file = request.files["csv_file"]
        if not file.filename.endswith('.csv'):
            flash("Please upload a CSV file.", "danger")
            return redirect("/import_trades")
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"))
            reader = csv.DictReader(stream)
            # Flexible column mapping
            def find_col(possibles, row):
                for key in row.keys():
                    for p in possibles:
                        if key.strip().lower() == p:
                            return key
                return None
            # Synonyms for each field
            col_map = {
                "pair": ["pair", "symbol", "ticker", "instrument"],
                "result": ["result", "outcome", "direction", "winloss", "pnl"],
                "entry": ["entry", "open", "o", "entry_price", "buy", "long", "in"],
                "exit": ["exit", "close", "c", "exit_price", "sell", "out"],
                "notes": ["notes", "comment", "annotation", "remarks", "memo"],
                "screenshot": ["screenshot", "image", "img", "picture", "snap"],
                "date": ["date", "datetime", "timestamp", "day"],
                "emotions": ["emotions", "emotion", "feeling", "feelings"],
                "rule_violations": ["rule_violations", "violation", "violations", "rules_broken"]
            }
            conn = sqlite3.connect("database.db")
            for row in reader:
                def get_val(field, default=None):
                    col = find_col([x.lower() for x in col_map[field]], row)
                    return row.get(col, default) if col else default
                pair = get_val("pair", "")
                result = get_val("result", "")
                entry = get_val("entry", 0)
                exit_price = get_val("exit", 0)
                notes = get_val("notes", "")
                screenshot = get_val("screenshot", None)
                date = get_val("date", "")
                emotions = get_val("emotions", "")
                rule_violations = get_val("rule_violations", "")
                try:
                    entry = float(entry)
                except Exception:
                    entry = 0
                try:
                    exit_price = float(exit_price)
                except Exception:
                    exit_price = 0
                conn.execute("""INSERT INTO trades (user_id, pair, result, entry, exit, notes, screenshot, date, emotions, rule_violations) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session["user_id"], pair, result, entry, exit_price, notes, screenshot, date, emotions, rule_violations))
            conn.commit()
            conn.close()
            flash("Trades imported successfully!", "success")
            return redirect("/dashboard")
        except Exception as e:
            flash(f"Import failed: {e}", "danger")
            return redirect("/import_trades")

    return render_template("import_trades.html")


# =====================================================
#  COMMUNITY FEATURES - ENHANCED
# =====================================================

# =====================================================
#  Create Journal (Share Trades)
# =====================================================
@app.route('/create_journal', methods=["GET", "POST"])
def create_journal():
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    if request.method == "POST":
        # Get selected trade IDs from form
        selected_trades = request.form.getlist("trade_ids")
        journal_title = request.form.get("journal_title", "My Trading Journal")
        
        if not selected_trades:
            flash("Please select at least one trade to share.", "warning")
            return redirect("/create_journal")
        
        # Get trade data
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        
        trade_data = []
        for trade_id in selected_trades:
            cursor.execute("SELECT pair, result, entry, exit, notes, date, emotions, rule_violations FROM trades WHERE id=? AND user_id=?", 
                          (trade_id, session["user_id"]))
            trade = cursor.fetchone()
            if trade:
                trade_data.append({
                    "pair": trade[0],
                    "result": trade[1],
                    "entry": trade[2],
                    "exit": trade[3],
                    "notes": trade[4],
                    "date": trade[5],
                    "emotions": trade[6],
                    "rule_violations": trade[7]
                })
        
        if not trade_data:
            flash("No valid trades selected.", "warning")
            conn.close()
            return redirect("/create_journal")
        
        # Create journal entry
        journal_data = json.dumps(trade_data)
        share_token = uuid.uuid4().hex
        
        cursor.execute(
            "INSERT INTO journals (user_id, journal_title, trade_data, share_token, is_shared, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session["user_id"], journal_title, journal_data, share_token, 1, datetime.now().isoformat())
        )
        conn.commit()
        journal_id = cursor.lastrowid
        conn.close()
        
        share_url = url_for("view_shared", token=share_token, _external=True)
        flash(f"Journal created and shared! Share this URL: {share_url}", "success")
        return redirect("/my_journals")

    # GET request - show user's trades for selection
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, pair, result, date FROM trades WHERE user_id=? ORDER BY date DESC", 
                  (session["user_id"],))
    trades = cursor.fetchall()
    conn.close()
    
    return render_template("create_journal.html", trades=trades)

# =====================================================
#  Share Journal (Generate Share Link)
# =====================================================
@app.route("/share_journal/<int:journal_id>", methods=["POST"])
def share_journal(journal_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Verify the journal belongs to the user
    cursor.execute("SELECT id FROM journals WHERE id=? AND user_id=?", (journal_id, session["user_id"]))
    journal = cursor.fetchone()
    
    if not journal:
        conn.close()
        return jsonify({"error": "Journal not found"}), 404
    
    # Generate share token
    share_token = uuid.uuid4().hex
    cursor.execute("UPDATE journals SET share_token=?, is_shared=1 WHERE id=?", (share_token, journal_id))
    conn.commit()
    conn.close()
    
    share_url = url_for("view_shared", token=share_token, _external=True)
    return jsonify({"share_url": share_url, "message": "Journal shared successfully!"})

# =====================================================
#  My Journals
# =====================================================
@app.route('/my_journals')
def my_journals():
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, journal_title, trade_data, share_token, created_at FROM journals WHERE user_id=? ORDER BY created_at DESC", 
                  (session["user_id"],))
    journals = cursor.fetchall()
    conn.close()
    
    journal_list = []
    for journal in journals:
        try:
            trade_data = json.loads(journal[2])
            journal_list.append({
                'id': journal[0],
                'title': journal[1] or "Untitled Journal",
                'trade_count': len(trade_data),
                'share_token': journal[3],
                'created_at': journal[4][:10] if journal[4] else 'Unknown',
                'share_url': url_for('view_shared', token=journal[3], _external=True)
            })
        except:
            continue
    
    return render_template("my_journals.html", journals=journal_list)

# =====================================================
#  Delete Journal
# =====================================================
@app.route('/delete_journal/<int:journal_id>', methods=["POST"])
def delete_journal(journal_id):
    if "user_id" not in session:
        flash("You must log in first.", "warning")
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Delete associated feedback first
    cursor.execute("DELETE FROM feedback WHERE journal_id=?", (journal_id,))
    # Delete the journal
    cursor.execute("DELETE FROM journals WHERE id=? AND user_id=?", (journal_id, session["user_id"]))
    conn.commit()
    conn.close()

    flash("Journal deleted successfully!", "success")
    return redirect("/my_journals")

# =====================================================
#  View Shared Journal (Fixed)
# =====================================================
@app.route("/shared/<token>")
def view_shared(token):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, journal_title, trade_data, created_at FROM journals WHERE share_token=? AND is_shared=1", (token,))
    journal_row = cursor.fetchone()
    
    if not journal_row:
        conn.close()
        return "Journal not found", 404
        
    # Get username
    cursor.execute("SELECT username FROM users WHERE id=?", (journal_row[1],))
    user_row = cursor.fetchone()
    username = user_row[0] if user_row else "Unknown User"
    
    cursor.execute("SELECT mentor_name, feedback_text, created_at FROM feedback WHERE journal_id=?", (journal_row[0],))
    feedbacks = cursor.fetchall()
    conn.close()
    
    # Parse trade data
    try:
        trade_data = json.loads(journal_row[3])
    except:
        trade_data = []
    
    journal_data = {
        'id': journal_row[0],
        'title': journal_row[2] or "Shared Trading Journal",
        'trade_data': trade_data,
        'created_at': journal_row[4][:10] if journal_row[4] else 'Unknown',
        'username': username
    }
    
    return render_template("shared_journal.html", journal=journal_data, feedbacks=feedbacks)

# =====================================================
#  Add Feedback (Fixed)
# =====================================================
@app.route("/feedback/<int:journal_id>", methods=["GET", "POST"])
def add_feedback(journal_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, journal_title, share_token FROM journals WHERE id=?", (journal_id,))
    journal_row = cursor.fetchone()
    
    if not journal_row:
        conn.close()
        return "Journal not found", 404

    if request.method == "POST":
        feedback_text = request.form["feedback_text"]
        mentor_name = request.form.get("mentor_name", "Anonymous Mentor")
        
        cursor.execute("INSERT INTO feedback (journal_id, mentor_id, mentor_name, feedback_text, created_at) VALUES (?, ?, ?, ?, ?)",
                      (journal_id, 1, mentor_name, feedback_text, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Get the share token for redirect
        share_token = journal_row[2]
        return redirect(url_for("view_shared", token=share_token))
    
    conn.close()
    return render_template("mentor_feedback.html", journal={'id': journal_row[0], 'title': journal_row[1]})

# =====================================================
#  Leaderboard (Enhanced with Real Data)
# =====================================================
@app.route("/leaderboard")
def leaderboard():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Get real user stats
    cursor.execute('''
        SELECT u.username, 
               COUNT(t.id) as total_trades,
               SUM(CASE WHEN LOWER(t.result) = 'win' THEN 1 ELSE 0 END) as wins,
               AVG(CASE WHEN LOWER(t.result) = 'win' THEN (t.exit - t.entry) / t.entry * 100 ELSE 0 END) as avg_profit_percent
        FROM users u
        LEFT JOIN trades t ON u.id = t.user_id
        GROUP BY u.id, u.username
        HAVING total_trades >= 1
        ORDER BY wins DESC, total_trades DESC
        LIMIT 10
    ''')
    
    user_stats = cursor.fetchall()
    conn.close()
    
    leaderboard_data = []
    for rank, (username, total_trades, wins, avg_profit_percent) in enumerate(user_stats, 1):
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        profit_display = f"+{avg_profit_percent:.1f}%" if avg_profit_percent and avg_profit_percent > 0 else f"{avg_profit_percent:.1f}%" if avg_profit_percent else "0%"
        
        leaderboard_data.append({
            'rank': rank,
            'user': username,
            'win_rate': f"{win_rate:.1f}%",
            'profit': profit_display,
            'trades': total_trades
        })
    
    # If no real data, use dummy data
    if not leaderboard_data:
        leaderboard_data = [
            {"rank": 1, "user": "EmediongE", "win_rate": "70.0%", "profit": "+12.5%", "trades": 45},
            {"rank": 2, "user": "TraderX", "win_rate": "68.2%", "profit": "+9.3%", "trades": 32},
            {"rank": 3, "user": "SarahFX", "win_rate": "65.7%", "profit": "+7.8%", "trades": 28},
        ]
    
    return render_template("leaderboard.html", data=leaderboard_data)
# =====================================================
#  Browse Shared Journals
# =====================================================
@app.route('/shared_journals')
def shared_journals():
    """Page to browse all shared journals from the community"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Get all shared journals with usernames
    cursor.execute('''
        SELECT j.id, j.journal_title, j.trade_data, j.share_token, j.created_at, u.username 
        FROM journals j 
        JOIN users u ON j.user_id = u.id 
        WHERE j.is_shared = 1 
        ORDER BY j.created_at DESC
    ''')
    journals = cursor.fetchall()
    conn.close()
    
    journal_list = []
    for journal in journals:
        try:
            trade_data = json.loads(journal[2])
            journal_list.append({
                'id': journal[0],
                'title': journal[1] or "Untitled Journal",
                'trade_count': len(trade_data),
                'share_token': journal[3],
                'created_at': journal[4][:10] if journal[4] else 'Unknown',
                'username': journal[5],
                'share_url': url_for('view_shared', token=journal[3])
            })
        except:
            continue
    
    return render_template("shared_journals.html", journals=journal_list)

# =====================================================
#  Trade Metadata API
# =====================================================
@app.route('/api/trade_metadata/<pair>_<date>.json')
def trade_metadata(pair, date):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pair, result, entry, exit, notes, screenshot, date FROM trades WHERE pair = ? AND date = ?",
                   (pair, date))
    trade = cursor.fetchone()
    conn.close()

    if not trade:
        return jsonify({"error": "Trade not found"}), 404

    metadata = {
        "name": f"Trade: {trade[0]} ({trade[6]})",
        "description": f"Result: {trade[1]}, Entry: {trade[2]}, Exit: {trade[3]}, Notes: {trade[4]}",
        "image": f"/uploads/{trade[5]}" if trade[5] else "",
        "attributes": [
            {"trait_type": "Pair", "value": trade[0]},
            {"trait_type": "Result", "value": trade[1]},
            {"trait_type": "Entry", "value": trade[2]},
            {"trait_type": "Exit", "value": trade[3]},
            {"trait_type": "Date", "value": trade[6]}
        ]
    }
    return jsonify(metadata)

# =====================================================
#  Logout
# =====================================================
@app.route('/logout', methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/")

# =====================================================
#  Admin Login
# =====================================================
@app.route('/admin_login', methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, password, is_admin FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password) and user[4] == 1:
            session["admin_id"] = user[0]
            session["admin_username"] = user[1]
            flash("Admin login successful!", "success")
            return redirect("/bulk_email")
        else:
            flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")

# =====================================================
#  Bulk Email (Admin Only)
# =====================================================
@app.route('/bulk_email', methods=["GET", "POST"])
def bulk_email():
    if "admin_id" not in session:
        flash("You must log in as admin first.", "warning")
        return redirect("/admin_login")

    if request.method == "POST":
        subject = request.form["subject"]
        body = request.form["body"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users")
        users = cursor.fetchall()
        conn.close()

        recipients = [u[0] for u in users]

        if recipients:
            msg = Message(subject, recipients=recipients)
            msg.html = body
            mail.send(msg)
            flash("Bulk email sent successfully ✅", "success")
        else:
            flash("No users found to send email.", "warning")

        return redirect("/bulk_email")

    return render_template("bulk_email.html")

# =====================================================
#  Admin Dashboard
# =====================================================
@app.route('/admin_dashboard')
def admin_dashboard():
    if "admin_id" not in session:
        flash("You must log in as admin first.", "warning")
        return redirect("/admin_login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, is_admin FROM users")
    users = cursor.fetchall()
    cursor.execute("SELECT * FROM trades")
    trades = cursor.fetchall()
    conn.close()

    return render_template("admin_dashboard.html", users=users, trades=trades)

# =====================================================
#  Admin Logout
# =====================================================
@app.route('/admin_logout', methods=["POST"])
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    flash("Admin logged out.", "info")
    return redirect("/admin_login")

# =====================================================
#  Uploads
# =====================================================
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# =====================================================
#  Run App
# =====================================================
if __name__ == '__main__':
    init_db()
    app.run(debug=True)