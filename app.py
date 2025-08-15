import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, g, session, send_from_directory
from flask_mysqldb import MySQL
from datetime import datetime, date
import MySQLdb.cursors

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'uploads'
# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'dhandha_db'
mysql = MySQL(app)
# Database Setup - This will automatically create tables on first run
def create_tables():
    cursor = mysql.connection.cursor()
    
    # Create Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(20) UNIQUE NOT NULL,
            password VARCHAR(60) NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            phone VARCHAR(20),
            firstname VARCHAR(20),
            lastname VARCHAR(20),
            is_agency BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) DEFAULT 'verified'
        )
    """)
    
    # Create Agencies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agencies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(20) UNIQUE NOT NULL,
            password VARCHAR(60) NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            phone VARCHAR(20),
            company_name VARCHAR(100) NOT NULL,
            trade_license VARCHAR(100) UNIQUE NOT NULL,
            is_agency BOOLEAN DEFAULT TRUE,
            is_admin BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) DEFAULT 'pending'
        )
    """)
    
    # Create Jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(100) NOT NULL,
            country VARCHAR(50) NOT NULL,
            deadline DATE NOT NULL,
            description TEXT NOT NULL,
            posted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            views INT DEFAULT 0,
            agency_id INT NOT NULL,
            FOREIGN KEY (agency_id) REFERENCES agencies(id) ON DELETE CASCADE
        )
    """)
    # Create Applications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(120) NOT NULL,
            contact VARCHAR(20) NOT NULL,
            cv_path VARCHAR(200) NOT NULL,
            status VARCHAR(20) DEFAULT 'Pending',
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id INT NOT NULL,
            job_id INT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
    """)
    # Create Job Bookmarks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_bookmarks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            job_id INT NOT NULL,
            bookmarked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
    """)
    # Create Notifications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            message TEXT NOT NULL,
            category VARCHAR(20) DEFAULT 'info',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_read BOOLEAN DEFAULT FALSE,
            user_id INT,
            agency_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (agency_id) REFERENCES agencies(id) ON DELETE CASCADE
        )
    """)
    # Create SuccessStories table and modify to allow agency stories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS success_stories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            content TEXT NOT NULL,
            rating INT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            author_id INT,
            agency_id INT,
            FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (agency_id) REFERENCES agencies(id) ON DELETE CASCADE
        )
    """)
    # Insert a default admin user if not exists
    cursor.execute("SELECT * FROM users WHERE is_admin = 1")
    admin_exists = cursor.fetchone()
    if not admin_exists:
        cursor.execute("""
            INSERT INTO users (username, password, email, firstname, lastname, is_admin)
            VALUES ('admin', 'adminpassword', 'admin@example.com', 'Admin', 'User', TRUE)
        """)
    mysql.connection.commit()
    cursor.close()
@app.before_request
def before_request():
    g.user = None
    if 'username' in session:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (session['username'],))
        user = cursor.fetchone()
        
        if user:
            g.user = {
                'id': user[0], 'username': user[1], 'password': user[2], 'email': user[3],
                'phone': user[4], 'firstname': user[5], 'lastname': user[6], 'is_agency': bool(user[7]),
                'is_admin': bool(user[8]), 'status': user[9]
            }
        else:
            cursor.execute("SELECT * FROM agencies WHERE username = %s", (session['username'],))
            agency = cursor.fetchone()
            if agency:
                g.user = {
                    'id': agency[0], 'username': agency[1], 'password': agency[2], 'email': agency[3],
                    'phone': agency[4], 'company_name': agency[5], 'trade_license': agency[6],
                    'is_agency': bool(agency[7]), 'is_admin': bool(agency[8]), 'status': agency[9]
                }
        cursor.close()
    
    # Check for expired jobs and remove them
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM jobs WHERE deadline < CURDATE()")
    mysql.connection.commit()
    cursor.close()
def is_authenticated():
    return g.user is not None
def send_notification(user_id, agency_id, message, category='info'):
    cursor = mysql.connection.cursor()
    cursor.execute("""
        INSERT INTO notifications (message, category, user_id, agency_id)
        VALUES (%s, %s, %s, %s)
    """, (message, category, user_id, agency_id))
    mysql.connection.commit()
    cursor.close()
# Route to serve uploaded files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/jobs')
def jobs():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Base query for all jobs, joining with agencies to get company name
    query = """
        SELECT j.*, a.company_name AS posted_by
        FROM jobs j
        JOIN agencies a ON j.agency_id = a.id
    """

    if g.user and not g.user['is_agency'] and not g.user['is_admin']:
        # If a regular user is logged in, get their application and bookmark statuses
        query = """
            SELECT
                j.id, j.title, j.country, j.deadline, j.description, j.posted_at, j.views,
                a.company_name AS posted_by,
                CASE WHEN app.job_id IS NOT NULL THEN 'applied' ELSE NULL END AS user_application_status,
                CASE WHEN bm.job_id IS NOT NULL THEN 'bookmarked' ELSE NULL END AS user_bookmark_status
            FROM jobs AS j
            JOIN agencies AS a ON j.agency_id = a.id
            LEFT JOIN applications AS app ON j.id = app.job_id AND app.user_id = %s
            LEFT JOIN job_bookmarks AS bm ON j.id = bm.job_id AND bm.user_id = %s
            ORDER BY j.posted_at DESC
        """
        cursor.execute(query, (g.user['id'], g.user['id']))
    else:
        # For agencies, admins, or logged-out users, just get the jobs
        cursor.execute(query + " ORDER BY j.posted_at DESC")
    
    all_jobs = cursor.fetchall()
    cursor.close()
    return render_template('jobs.html', jobs=all_jobs)


@app.route('/jobs/<int:job_id>')
def job_details(job_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Increment job view count
    cursor.execute("UPDATE jobs SET views = views + 1 WHERE id = %s", (job_id,))
    mysql.connection.commit()
    
    cursor.execute("SELECT j.*, a.company_name FROM jobs j JOIN agencies a ON j.agency_id = a.id WHERE j.id = %s", (job_id,))
    job_data = cursor.fetchone()
    cursor.close()
    
    if not job_data:
        flash('Job not found.', 'error')
        return redirect(url_for('jobs'))
    
    return render_template('job_details.html', job=job_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        is_agency = 'is_agency' in request.form
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        user_exists = cursor.fetchone()
        cursor.execute("SELECT * FROM agencies WHERE username = %s OR email = %s", (username, email))
        agency_exists = cursor.fetchone()
        
        if user_exists or agency_exists:
            flash('Username or email already exists. Please choose a different one.', 'error')
            cursor.close()
            return redirect(url_for('register'))
        if is_agency:
            required_fields = ['username', 'email', 'password', 'company_name', 'trade_license']
            for field in required_fields:
                if not request.form.get(field):
                    flash(f'Please provide {field}.', 'error')
                    cursor.close()
                    return redirect(url_for('register'))
            
            cursor.execute("""
                INSERT INTO agencies (username, password, email, phone, company_name, trade_license)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, password, email, request.form.get('phone'), request.form.get('company_name'), request.form.get('trade_license')))
            
            flash('Registration successful! Your agency account is pending admin approval.', 'success')
            
            cursor.execute("SELECT id FROM users WHERE is_admin = TRUE")
            admin_id = cursor.fetchone()
            if admin_id:
                send_notification(admin_id[0], None, f'New agency registration from {username} is awaiting your approval.', 'info')
        else:
            required_fields = ['username', 'email', 'password', 'firstname', 'lastname']
            for field in required_fields:
                if not request.form.get(field):
                    flash(f'Please provide {field}.', 'error')
                    cursor.close()
                    return redirect(url_for('register'))
            
            cursor.execute("""
                INSERT INTO users (username, password, email, phone, firstname, lastname)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, password, email, request.form.get('phone'), request.form.get('firstname'), request.form.get('lastname')))
            
            flash('Registration successful! Please log in.', 'success')
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('login'))
    
    return render_template('register.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user_data = cursor.fetchone()
        
        if user_data:
            session['username'] = username
            flash('Logged in successfully!', 'success')
            cursor.close()
            return redirect(url_for('index'))
        
        cursor.execute("SELECT * FROM agencies WHERE username = %s AND password = %s", (username, password))
        agency_data = cursor.fetchone()
        if agency_data:
            if agency_data[9] != 'verified':
                flash('Your account is pending admin approval. Please wait for verification.', 'error')
                cursor.close()
                return redirect(url_for('login'))
            session['username'] = username
            flash('Logged in successfully!', 'success')
            cursor.close()
            return redirect(url_for('index'))
        
        flash('Invalid username or password.', 'error')
        cursor.close()
    return render_template('login.html')
@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))
@app.route('/admin/dashboard')
def admin_dashboard():
    if not g.user or not g.user['is_admin']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM agencies WHERE status = 'pending'")
    pending_agencies = cursor.fetchall()
    cursor.execute("SELECT * FROM users WHERE is_admin = FALSE")
    registered_users = cursor.fetchall()
    cursor.execute("SELECT * FROM agencies WHERE status = 'verified'")
    registered_agencies = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM jobs")
    job_count = cursor.fetchone()[0]
    cursor.close()
    
    analytics = {
        'users': len(registered_users),
        'agencies': len(registered_agencies),
        'jobs': job_count
    }
    pending_agencies_list = [{'id': p[0], 'username': p[1]} for p in pending_agencies]
    registered_users_list = [{'username': u[1]} for u in registered_users]
    registered_agencies_list = [{'username': a[1]} for a in registered_agencies]
    return render_template('admin_dashboard.html', analytics=analytics, pending_agencies=pending_agencies_list, registered_users=registered_users_list, registered_agencies=registered_agencies_list)
@app.route('/admin/verify_agency/<int:agency_id>')
def verify_agency(agency_id):
    if not g.user or not g.user['is_admin']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT status, username FROM agencies WHERE id = %s", (agency_id,))
    agency_data = cursor.fetchone()
    
    if agency_data and agency_data[0] == 'pending':
        cursor.execute("UPDATE agencies SET status = 'verified' WHERE id = %s", (agency_id,))
        mysql.connection.commit()
        flash(f'Agency {agency_data[1]} has been approved.', 'success')
        
        cursor.execute("SELECT id FROM users WHERE is_admin = TRUE")
        admin_id = cursor.fetchone()[0]
        send_notification(None, agency_id, 'Congratulations! Your agency account has been approved by the admin.', 'success')
    else:
        flash('Agency not found or already verified.', 'error')
    
    cursor.close()
    return redirect(url_for('admin_dashboard'))
@app.route('/admin/reject_agency/<int:agency_id>')
def reject_agency(agency_id):
    if not g.user or not g.user['is_admin']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT status, username FROM agencies WHERE id = %s", (agency_id,))
    agency_data = cursor.fetchone()
    
    if agency_data and agency_data[0] == 'pending':
        cursor.execute("DELETE FROM agencies WHERE id = %s", (agency_id,))
        mysql.connection.commit()
        flash(f'Agency {agency_data[1]} has been rejected and removed.', 'success')
    else:
        flash('Agency not found or not in pending status.', 'error')
    
    cursor.close()
    return redirect(url_for('admin_dashboard'))
@app.route('/agency/dashboard')
def agency_dashboard():
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT j.*, COUNT(a.id) as applications_count
        FROM jobs j
        LEFT JOIN applications a ON j.id = a.job_id
        WHERE j.agency_id = %s
        GROUP BY j.id
    """, (g.user['id'],))
    jobs_data = cursor.fetchall()
    cursor.close()
    
    jobs = []
    for job in jobs_data:
        jobs.append({
            'id': job[0], 'title': job[1], 'country': job[2], 'deadline': job[3],
            'description': job[4], 'posted_at': job[5], 'views': job[6],
            'applications_count': job[8]
        })
    
    return render_template('agency_dashboard.html', jobs=jobs)
@app.route('/agency/post_job', methods=['GET', 'POST'])
def post_job():
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = request.form['title']
        country = request.form['country']
        deadline = request.form['deadline']
        description = request.form['description']
        
        cursor = mysql.connection.cursor()
        cursor.execute("""
            INSERT INTO jobs (title, country, deadline, description, agency_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (title, country, deadline, description, g.user['id']))
        mysql.connection.commit()
        cursor.close()
        
        flash('Job posted successfully!', 'success')
        
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id FROM users WHERE is_agency = FALSE AND is_admin = FALSE")
        users = cursor.fetchall()
        for user_id in users:
            send_notification(user_id[0], None, f'New job posted: {title} in {country}!')
        cursor.close()
        
        return redirect(url_for('agency_dashboard'))
    
    return render_template('post_job.html')
@app.route('/agency/edit_job/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = %s AND agency_id = %s", (job_id, g.user['id']))
    job_data = cursor.fetchone()
    
    if not job_data:
        flash('Job not found or you do not have permission to edit it.', 'error')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        country = request.form['country']
        deadline = request.form['deadline']
        description = request.form['description']
        
        cursor.execute("""
            UPDATE jobs SET title = %s, country = %s, deadline = %s, description = %s
            WHERE id = %s
        """, (title, country, deadline, description, job_id))
        mysql.connection.commit()
        flash('Job updated successfully!', 'success')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    
    job = {
        'id': job_data[0], 'title': job_data[1], 'country': job_data[2],
        'deadline': job_data[3], 'description': job_data[4]
    }
    cursor.close()
    return render_template('edit_job.html', job=job)
@app.route('/agency/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT agency_id FROM jobs WHERE id = %s", (job_id,))
    job_agency_id = cursor.fetchone()
    
    if job_agency_id and job_agency_id[0] == g.user['id']:
        cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        mysql.connection.commit()
        flash('Job deleted successfully!', 'success')
    else:
        flash('Job not found or you do not have permission to delete it.', 'error')
    
    cursor.close()
    return redirect(url_for('agency_dashboard'))
@app.route('/agency/view_applications/<int:job_id>')
def view_applications(job_id):
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT title, agency_id FROM jobs WHERE id = %s", (job_id,))
    job = cursor.fetchone()
    
    if not job or job[1] != g.user['id']:
        flash('Job not found or you do not have permission to view its applications.', 'error')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    
    cursor.execute("""
        SELECT a.id, a.name, a.email, a.contact, a.cv_path, a.status, a.applied_at, u.username
        FROM applications a
        JOIN users u ON a.user_id = u.id
        WHERE a.job_id = %s
        ORDER BY a.applied_at DESC
    """, (job_id,))
    applications_data = cursor.fetchall()
    cursor.close()
    applications = []
    for app_data in applications_data:
        applications.append({
            'id': app_data[0],
            'name': app_data[1],
            'email': app_data[2],
            'contact': app_data[3],
            'cv_path': app_data[4],
            'status': app_data[5],
            'applied_at': app_data[6],
            'username': app_data[7]
        })
    return render_template('view_applications.html', job_title=job[0], applications=applications)
@app.route('/agency/approve_application/<int:application_id>')
def approve_application(application_id):
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT job_id, user_id FROM applications WHERE id = %s", (application_id,))
    application_data = cursor.fetchone()
    if not application_data:
        flash('Application not found.', 'error')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    
    job_id = application_data[0]
    user_id = application_data[1]
    cursor.execute("SELECT agency_id FROM jobs WHERE id = %s", (job_id,))
    job_agency_id = cursor.fetchone()[0]
    if job_agency_id != g.user['id']:
        flash('You do not have permission to approve this application.', 'error')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    cursor.execute("UPDATE applications SET status = 'Approved' WHERE id = %s", (application_id,))
    mysql.connection.commit()
    flash('Application has been approved!', 'success')
    
    send_notification(user_id, None, 'Congratulations! Your job application has been approved.')
    cursor.close()
    return redirect(url_for('view_applications', job_id=job_id))
@app.route('/agency/reject_application/<int:application_id>')
def reject_application(application_id):
    if not g.user or not g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT job_id, user_id FROM applications WHERE id = %s", (application_id,))
    application_data = cursor.fetchone()
    if not application_data:
        flash('Application not found.', 'error')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    job_id = application_data[0]
    user_id = application_data[1]
    cursor.execute("SELECT agency_id FROM jobs WHERE id = %s", (job_id,))
    job_agency_id = cursor.fetchone()[0]
    if job_agency_id != g.user['id']:
        flash('You do not have permission to reject this application.', 'error')
        cursor.close()
        return redirect(url_for('agency_dashboard'))
    cursor.execute("UPDATE applications SET status = 'Rejected' WHERE id = %s", (application_id,))
    mysql.connection.commit()
    flash('Application has been rejected.', 'success')
    
    send_notification(user_id, None, 'Your job application has been rejected.')
    cursor.close()
    return redirect(url_for('view_applications', job_id=job_id))

@app.route('/bookmark_job/<int:job_id>', methods=['POST'])
def bookmark_job(job_id):
    if not g.user or g.user['is_agency'] or g.user['is_admin']:
        flash('You must be a user to bookmark a job.', 'error')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM job_bookmarks WHERE user_id = %s AND job_id = %s", (g.user['id'], job_id))
    bookmark_exists = cursor.fetchone()

    if bookmark_exists:
        flash('Job is already bookmarked.', 'info')
    else:
        cursor.execute("INSERT INTO job_bookmarks (user_id, job_id) VALUES (%s, %s)", (g.user['id'], job_id))
        mysql.connection.commit()
        flash('Job bookmarked successfully!', 'success')
    
    cursor.close()
    return redirect(url_for('jobs'))

@app.route('/remove_bookmark/<int:job_id>', methods=['POST'])
def remove_bookmark(job_id):
    if not g.user or g.user['is_agency'] or g.user['is_admin']:
        flash('Access denied.', 'error')
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM job_bookmarks WHERE user_id = %s AND job_id = %s", (g.user['id'], job_id))
    mysql.connection.commit()
    flash('Bookmark removed.', 'info')
    cursor.close()
    return redirect(url_for('my_applications'))

@app.route('/apply_job/<int:job_id>', methods=['GET', 'POST'])
def apply_job(job_id):
    if not g.user or g.user['is_agency']:
        flash('You must be a user to apply for jobs.', 'error')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
    job_data = cursor.fetchone()
    
    if not job_data:
        flash('Job not found.', 'error')
        cursor.close()
        return redirect(url_for('jobs'))
    
    cursor.execute("SELECT * FROM applications WHERE user_id = %s AND job_id = %s", (g.user['id'], job_id))
    already_applied = cursor.fetchone()
    if already_applied:
        flash('You have already applied for this job.', 'info')
        cursor.close()
        return redirect(url_for('jobs'))

    if request.method == 'POST':
        if 'cv' not in request.files:
            flash('No CV file uploaded.', 'error')
            return redirect(url_for('job_details', job_id=job_id))
        file = request.files['cv']
        if file.filename == '':
            flash('No CV file selected.', 'error')
            return redirect(url_for('job_details', job_id=job_id))
        if file:
            filename = f"{g.user['username']}_{job_id}_{secrets.token_hex(4)}.pdf"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            cursor.execute("""
                INSERT INTO applications (name, email, contact, cv_path, user_id, job_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (request.form['name'], request.form['email'], request.form['contact'], filepath, g.user['id'], job_id))
            mysql.connection.commit()
            
            # Remove from bookmarks if it exists
            cursor.execute("DELETE FROM job_bookmarks WHERE user_id = %s AND job_id = %s", (g.user['id'], job_id))
            mysql.connection.commit()
            
            flash('Application submitted successfully!', 'success')
            
            # Send notification to the agency that owns the job
            send_notification(user_id=None, agency_id=job_data['agency_id'], message=f"A new application has been submitted for your job: '{job_data['title']}'.")

    cursor.close()
    return render_template('apply_job.html', job=job_data)


@app.route('/my_applications')
def my_applications():
    if not g.user or g.user['is_agency']:
        flash('You must be a user to view your applications.', 'error')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Fetch applications
    cursor.execute("""
        SELECT a.id, a.status, a.applied_at, j.title, ag.company_name, j.id AS job_id
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        JOIN agencies ag ON j.agency_id = ag.id
        WHERE a.user_id = %s
        ORDER BY a.applied_at DESC
    """, (g.user['id'],))
    applied_jobs = cursor.fetchall()
    
    # Fetch bookmarked jobs
    cursor.execute("""
        SELECT b.id, j.id AS job_id, 'bookmarked' AS status, b.bookmarked_at AS applied_at, j.title, ag.company_name
        FROM job_bookmarks b
        JOIN jobs j ON b.job_id = j.id
        JOIN agencies ag ON j.agency_id = ag.id
        WHERE b.user_id = %s
        ORDER BY b.bookmarked_at DESC
    """, (g.user['id'],))
    bookmarked_jobs = cursor.fetchall()
    
    applications = []
    # Combine the lists and standardize the key names
    for app in applied_jobs:
        applications.append({
            'id': app['id'], 
            'status': app['status'], 
            'applied_at': app['applied_at'], 
            'job_title': app['title'], 
            'agency': app['company_name'],
            'job_id': app['job_id']
        })
    for bookmark in bookmarked_jobs:
        applications.append({
            'id': bookmark['id'],
            'status': 'Bookmarked', 
            'applied_at': bookmark['applied_at'],
            'job_title': bookmark['title'], 
            'agency': bookmark['company_name'],
            'job_id': bookmark['job_id']
        })
    
    # Sort the combined list by date
    applications.sort(key=lambda x: x['applied_at'], reverse=True)
    
    cursor.close()
    
    return render_template('my_applications.html', applications=applications)


@app.route('/notifications')
def notifications():
    if not g.user:
        flash('You must be logged in to view your notifications.', 'error')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor()
    if g.user['is_agency']:
        cursor.execute("SELECT * FROM notifications WHERE agency_id = %s ORDER BY timestamp DESC", (g.user['id'],))
    else:
        cursor.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY timestamp DESC", (g.user['id'],))
    notifications_data = cursor.fetchall()
    cursor.close()
    
    notifications = []
    for notif in notifications_data:
        notifications.append({
            'id': notif[0], 'message': notif[1], 'category': notif[2],
            'timestamp': notif[3], 'is_read': notif[4]
        })
    
    return render_template('notification.html', notifications=notifications)
@app.route('/success_stories', methods=['GET', 'POST'])
def success_stories():
    if request.method == 'POST':
        # This part remains the same as our previous successful fix
        if not g.user:
            flash('You must be logged in to post a story.', 'error')
            return redirect(url_for('login'))
        story_content = request.form['story']
        rating = request.form['rating']
        
        cursor = mysql.connection.cursor()
        
        if g.user['is_agency']:
            cursor.execute("""
                INSERT INTO success_stories (content, rating, agency_id)
                VALUES (%s, %s, %s)
            """, (story_content, rating, g.user['id']))
        else:
            cursor.execute("""
                INSERT INTO success_stories (content, rating, author_id)
                VALUES (%s, %s, %s)
            """, (story_content, rating, g.user['id']))
        mysql.connection.commit()
        flash('Your story has been posted!', 'success')
        cursor.close()
        return redirect(url_for('success_stories'))
    # This is the correct GET request logic to fetch all stories
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT 
            s.id,
            s.content,
            s.rating,
            s.timestamp,
            COALESCE(u.username, a.company_name) AS author,
            s.author_id,
            s.agency_id
        FROM success_stories AS s
        LEFT JOIN users AS u ON s.author_id = u.id
        LEFT JOIN agencies AS a ON s.agency_id = a.id
        ORDER BY s.timestamp DESC
    """)
    stories = cursor.fetchall()
    cursor.close()
    return render_template('success_stories.html', stories=stories)
@app.route('/edit_story/<int:story_id>', methods=['GET', 'POST'])
def edit_story(story_id):
    if not g.user:
        flash('You must be logged in to edit a story.', 'error')
        return redirect(url_for('success_stories'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if the user is the author (user or agency) of the story
    if g.user['is_agency']:
        cursor.execute("SELECT * FROM success_stories WHERE id = %s AND agency_id = %s", (story_id, g.user['id']))
    else:
        cursor.execute("SELECT * FROM success_stories WHERE id = %s AND author_id = %s", (story_id, g.user['id']))
    
    story = cursor.fetchone()
    
    if not story:
        flash('Story not found or you do not have permission to edit it.', 'error')
        cursor.close()
        return redirect(url_for('success_stories'))
    if request.method == 'POST':
        new_content = request.form['story']
        new_rating = request.form['rating']
        
        cursor.execute("UPDATE success_stories SET content = %s, rating = %s WHERE id = %s", (new_content, new_rating, story_id))
        mysql.connection.commit()
        
        flash('Your story has been updated successfully!', 'success')
        cursor.close()
        return redirect(url_for('success_stories'))
    
    cursor.close()
    return render_template('edit_story.html', story=story)
@app.route('/delete_story/<int:story_id>', methods=['POST'])
def delete_story(story_id):
    if not g.user:
        flash('You must be logged in to delete a story.', 'error')
        return redirect(url_for('success_stories'))
    
    cursor = mysql.connection.cursor()
    
    # Check if the user is the author (user or agency) of the story
    if g.user['is_agency']:
        cursor.execute("SELECT id FROM success_stories WHERE id = %s AND agency_id = %s", (story_id, g.user['id']))
    else:
        cursor.execute("SELECT id FROM success_stories WHERE id = %s AND author_id = %s", (story_id, g.user['id']))
        
    story_exists = cursor.fetchone()
    
    if not story_exists:
        flash('Story not found or you do not have permission to delete it.', 'error')
        cursor.close()
        return redirect(url_for('success_stories'))
    cursor.execute("DELETE FROM success_stories WHERE id = %s", (story_id,))
    mysql.connection.commit()
    
    flash('Your story has been deleted.', 'success')
    cursor.close()
    return redirect(url_for('success_stories'))
@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():
    if not g.user or g.user['is_agency']:
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        firstname = request.form.get('firstname')
        lastname = request.form.get('lastname')
        phone = request.form.get('phone')
        email = request.form.get('email')
        
        cursor = mysql.connection.cursor()
        cursor.execute("""
            UPDATE users SET firstname = %s, lastname = %s, phone = %s, email = %s
            WHERE id = %s
        """, (firstname, lastname, phone, email, g.user['id']))
        mysql.connection.commit()
        flash('Profile updated successfully!', 'success')
        cursor.close()
        return redirect(url_for('user_profile'))
    
    return render_template('user_profile.html', user=g.user)
@app.route('/forget_password', methods=['GET', 'POST'])
def forget_password():
    if request.method == 'POST':
        flash('Password reset link has been sent to your email (This is a placeholder).', 'info')
        return redirect(url_for('login'))
    return render_template('forget_password.html')
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        flash('Your password has been reset successfully.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html')
if __name__ == '__main__':
    with app.app_context():
        create_tables()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
