from flask import Flask, render_template, request, redirect, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'dhandha'

mysql = MySQL(app)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session['loggedin'] = True
            session['id'] = user['id']
            session['role'] = user['role']
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
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)', (name, email, hashed_password, role))
        mysql.connection.commit()
        flash('Signup successful! Please login.', 'success')
        return redirect('/login')
    return render_template('signup.html')


if __name__ == '__main__':
    app.run(debug=True)