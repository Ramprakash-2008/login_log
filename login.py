from flask import Flask, request, redirect, url_for, render_template_string, session, send_file
import sqlite3, os, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from openpyxl import Workbook
from openpyxl.styles import PatternFill
import os
from datetime import datetime, time
import pytz
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)
app.secret_key = "super_secret_key"
 
# === CONFIG ===
ADMIN_PASSWORD = os.getenv("ADMIN_PASS")
ADMIN_EMAIL = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASS")
          # <-- Replace this
DATABASE = "users.db"
LOG_FILE = "login_log.csv"
DEADLINE_TIME = "09:00"

# === HTML Templates ===
LOGIN_TEMPLATE = """
<h2>Admin Login</h2>
<form method="POST">
    Password: <input type="password" name="password">
    <button type="submit">Login</button>
</form>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Dashboard</title>
    <style>
        body { font-family: Arial; margin: 20px; }
        .topbar button { margin-right: 10px; }
        .hidden { display: none; }
        .status { color: green; font-weight: bold; }
        .late { color: red; }
        .ontime { color: green; }
    </style>
    <script>
        function toggle(id) {
            const el = document.getElementById(id);
            el.style.display = (el.style.display === "none") ? "block" : "none";
        }
    </script>
</head>
<body>
<h2>Admin Dashboard - Login Logs</h2>
<div class="topbar">
    <button onclick="toggle('addUserForm')">➕ Add User</button>
    <button onclick="toggle('updateUsersForm')">🛠 Update Users</button>
    <form method="GET" action="/users" style="display:inline;">
        <button>👤 Show All Registered Users</button>
    </form>
    <form method="GET" action="/download-log" style="display:inline;">
        <button>📥 Download Excel Log</button>
    </form>
</div>

{% if message %}<p class="status">✅ {{ message }}</p>{% endif %}

<div id="addUserForm" class="hidden">
    <form method="POST">
        <label>Add Single Username:</label>
        <input type="text" name="new_username" required>
        <button type="submit">Add</button>
    </form>
    <br><hr>
    <form method="POST" enctype="multipart/form-data">
        <label>Upload Usernames File (.txt/.csv):</label>
        <input type="file" name="file" accept=".txt,.csv" required>
        <button type="submit">Upload</button>
    </form>
</div>

<div id="updateUsersForm" class="hidden">
    <form method="POST">
        <table border="1">
            <tr><th>Username</th><th>Edit</th><th>Delete</th></tr>
            {% for user in users %}
            <tr>
                <td><input type="text" name="usernames" value="{{ user }}"></td>
                <td><input type="checkbox" name="edit_{{ loop.index0 }}"></td>
                <td><input type="checkbox" name="delete_{{ loop.index0 }}"></td>
                <input type="hidden" name="original_{{ loop.index0 }}" value="{{ user }}">
            </tr>
            {% endfor %}
        </table>
        <input type="hidden" name="count" value="{{ users|length }}">
        <button type="submit" name="save_changes">💾 Save Changes</button>
    </form>
</div>

<h3>Login Logs</h3>
<table border="1">
<tr><th>Username</th><th>Time</th><th>Status</th></tr>
{% for row in logs %}
<tr>
    <td>{{ row[0] }}</td>
    <td>{{ row[1] }}</td>
    <td class="{{ 'late' if row[2] == 'Late' else 'ontime' }}">{{ row[2] }}</td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""

USERS_TEMPLATE = """
<h2>All Registered Users</h2>
<ul>
{% for user in users %}
    <li>{{ user }}</li>
{% endfor %}
</ul>
<a href="/admin">⬅ Back to Admin</a>
"""

# === Helper Functions ===
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT UNIQUE)")
    conn.commit()
    conn.close()
init_db()
def get_users():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT username FROM users")
    users = [row[0] for row in cur.fetchall()]
    conn.close()
    return users

def save_log(username, time, status):
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write("Username,Time,Status\n")
    with open(LOG_FILE, 'a') as f:
        f.write(f"{username},{time},{status}\n")

def get_logs():
    if not os.path.exists(LOG_FILE): return []
    with open(LOG_FILE) as f:
        next(f)
        return [line.strip().split(',') for line in f]

def send_late_email(username, login_time):
    msg = MIMEText(f"User '{username}' logged in late at {login_time}.")
    msg['Subject'] = f"LATE LOGIN: {username}"
    msg['From'] = ADMIN_EMAIL
    msg['To'] = ADMIN_EMAIL
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(ADMIN_EMAIL, EMAIL_PASSWORD)
            server.sendmail(ADMIN_EMAIL, ADMIN_EMAIL, msg.as_string())
    except Exception as e:
        print("❌ Email failed:", e)

@app.route("/download-log")
def download_excel():
    if not os.path.exists(LOG_FILE):
        return "Log file not found."

    wb = Workbook()
    ws = wb.active
    ws.title = "Login Log"
    ws.append(["Username", "Time", "Status"])

    green = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    with open(LOG_FILE, "r") as f:
        next(f)
        for line in f:
            username, time, status = line.strip().split(",")
            row = [username, time, status]
            ws.append(row)
            fill = green if status == "On-time" else red
            for cell in ws[ws.max_row]:
                cell.fill = fill

    file_path = "login_log.xlsx"
    wb.save(file_path)
    return send_file(file_path, as_attachment=True)

@app.route("/")
def home():
    return """
    <h2>User Login</h2>
    <form method="POST" action="/login">
        Username: <input type="text" name="username">
        <button type="submit">Login</button>
    </form>
    """

@app.route("/login", methods=["POST"])
def login_user():
    try:
        username = request.form.get("username", "").strip()
        if not username:
            return "❌ Username required", 400

        # ✅ Check if user is registered
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE username=?", (username,))
        result = c.fetchone()
        conn.close()

        if not result:
            return "❌ You are not a registered user", 401

        # ✅ Get India time
        india = pytz.timezone("Asia/Kolkata")
        now = datetime.now(india)
        current_time = now.time()
        deadline = time(hour=9, minute=0)

        status = "Late" if current_time > deadline else "On-time"
        log_time = now.strftime("%H:%M")

        # ✅ Save to log
        save_log(username, log_time, status)

        # ✅ Send email if late
        if status == "Late":
            send_late_email(username, log_time)

        return f"✅ {username} logged in at {log_time} ({status})"

    except Exception as e:
        print("❌ ERROR in /login:", e)
        return "Internal Server Error", 500


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("logged_in"):
        return redirect("/admin/login")

    message = ""

    if request.method == "POST":
        if "new_username" in request.form:
            username = request.form["new_username"].strip()
            if username:
                conn = sqlite3.connect(DATABASE)
                cur = conn.cursor()
                cur.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
                conn.commit()
                conn.close()
                message = f"User '{username}' added."

        elif "file" in request.files:
            file = request.files["file"]
            if file:
                lines = file.read().decode("utf-8").splitlines()
                conn = sqlite3.connect(DATABASE)
                cur = conn.cursor()
                for name in lines:
                    cur.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (name.strip(),))
                conn.commit()
                conn.close()
                message = f"{len(lines)} users uploaded."

        elif "save_changes" in request.form:
            count = int(request.form["count"])
            conn = sqlite3.connect(DATABASE)
            cur = conn.cursor()
            for i in range(count):
                original = request.form[f"original_{i}"].strip()
                new_value = request.form.getlist("usernames")[i].strip()
                delete = request.form.get(f"delete_{i}")

                if delete:
                    cur.execute("DELETE FROM users WHERE username = ?", (original,))
                elif new_value != original:
                    cur.execute("UPDATE users SET username = ? WHERE username = ?", (new_value, original))
            conn.commit()
            conn.close()
            message = "Changes saved successfully."

    return render_template_string(ADMIN_TEMPLATE, logs=get_logs(), users=get_users(), message=message)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect("/admin")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/users")
def show_users():
    return render_template_string(USERS_TEMPLATE, users=get_users())

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/admin/login")

# === Main ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


