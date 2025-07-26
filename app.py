# ✅ Updated `app.py` with SQLite (instead of MySQL)
from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ✅ DB Setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'dhandha.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ✅ Ensure DB and Tables Exist
with get_db_connection() as conn:
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT CHECK(role IN ('user','agency','admin')) NOT NULL,
        verified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agency_id INTEGER,
        title TEXT,
        description TEXT,
        country TEXT,
        salary TEXT,
        deadline DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (agency_id) REFERENCES users(id)
    )''')
    conn.commit()

@app.route('/')
def home():
    conn = get_db_connection()
    jobs = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 6').fetchall()
    conn.close()
    return render_template('home.html', jobs=jobs)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['loggedin'] = True
            session['id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            flash('Login successful', 'success')
            return redirect('/')
        else:
            flash('Incorrect credentials', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        hashed_password = generate_password_hash(password)
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)',
                         (name, email, hashed_password, role))
            conn.commit()
            conn.close()
            flash('Signup successful! Please login.', 'success')
            return redirect('/login')
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'danger')
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
