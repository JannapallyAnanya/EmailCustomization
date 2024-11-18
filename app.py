from flask import Flask, render_template, request, redirect, url_for, session, flash
import google.auth
from google_auth_oauthlib.flow import Flow  
import oauthlib
import google_auth_oauthlib.flow 
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from flask_mysqldb import MySQL
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
import MySQLdb.cursors
import re
import os
import csv
import smtplib
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = os.getenv('OAUTHLIB_INSECURE_TRANSPORT', '1')
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
#app.secret_key = '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'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True 
app.config['SESSION_PERMANENT'] = True  
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

mysql = MySQL(app)
  
@app.route('/')
@app.route('/login', methods =['GET', 'POST'])
def login():
    mesage = ''
    if request.method == 'POST' and 'email' in request.form and 'password' in request.form:
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM user WHERE email = % s AND password = % s', (email, password, ))
        user = cursor.fetchone()
        if user:
            session['loggedin'] = True
            session['userid'] = user['userid']
            session['name'] = user['name']
            session['email'] = user['email']
            mesage = 'Logged in successfully !'
            return render_template('user.html', mesage = mesage,name=session.get('name'))
        else:
            mesage = 'Please enter correct email / password !'
    return render_template('login.html', mesage = mesage, name=session.get('name'))
  
@app.route('/user')
def user():
    if 'loggedin' in session:
        return render_template('user.html', session.get('name'))
    else:
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('userid', None)
    session.pop('email', None)
    return redirect(url_for('login'))
  
@app.route('/register', methods =['GET', 'POST'])
def register():
    mesage = ''
    if request.method == 'POST' and 'name' in request.form and 'password' in request.form and 'email' in request.form :
        userName = request.form['name']
        password = request.form['password']
        email = request.form['email']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM user WHERE email = % s', (email, ))
        account = cursor.fetchone()
        if account:
            mesage = 'Account already exists !'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            mesage = 'Invalid email address !'
        elif not userName or not password or not email:
            mesage = 'Please fill out the form !'
        else:
            print("Registering user:", userName, email, password)
            cursor.execute('INSERT INTO user (name, email, password) VALUES (%s, %s, %s)', (userName, email, password))
            mysql.connection.commit()
            mesage = 'You have successfully registered !'
    elif request.method == 'POST':
        mesage = 'Please fill out the form !'
    return render_template('register.html', mesage = mesage)
    
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE') 
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly'
]

REDIRECT_URI = os.getenv('REDIRECT_URI')
UPLOAD_FOLDER = 'uploads'  
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
    CLIENT_SECRETS_FILE, scopes=SCOPES)
flow.redirect_uri = REDIRECT_URI

@app.route('/connect_google')
def connect_google():
    session.pop('credentials', None)
    flow = Flow.from_client_secrets_file(   
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(prompt='select_account')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )
    try:
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        session['credentials'] = credentials_to_dict(credentials)
        flash('Successfully connected to your Google account!', 'success')
        return redirect(url_for('get_sheets_list'))
    except oauthlib.oauth2.rfc6749.errors.AccessDeniedError:
        flash('You canceled the login process. Please try again if you want to connect.', 'warning')
        return render_template('user.html')
    except Exception as e:
        flash(f'An unexpected error occurred: {str(e)}', 'danger')
        return render_template('user.html')

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

@app.route('/get_sheets_list')
def get_sheets_list():
    if 'credentials' not in session:
        flash('You need to connect your Google account first.', 'warning')
        return redirect(url_for('connect_google'))
    credentials = Credentials(**session['credentials'])
    try:
        service = build('drive', 'v3', credentials=credentials)
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=10,
            fields="files(id, name)"
        ).execute()
        items = results.get('files', [])
        return render_template('sheets_list.html', sheets=items)
    except HttpError as err:
        flash(f'An error occurred while accessing Google Sheets: {err}', 'danger')
        return redirect(url_for('user'))

@app.route('/select_sheet/<sheet_id>')
def select_sheet(sheet_id):
    if 'credentials' not in session:
        flash('You need to connect your Google account first.', 'warning')
        return redirect(url_for('connect_google'))
    credentials = Credentials(**session['credentials'])
    try:
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='Sheet1'
        ).execute()
        data = sheet.get('values', [])
        return render_template('email_customization.html', data=data)
    except HttpError as err:
        flash(f'Error fetching sheet data: {err}', 'danger')
        return redirect(url_for('get_sheets_list'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_csv():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            emails = extract_emails_from_csv(filepath)
            session['uploaded_emails'] = emails
            with open(filepath, 'r') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
                headers = data[0] if data else []
            return render_template('email_customization.html', data=data[1:], headers=headers, emails=emails)
    return render_template('upload.html')

def send_email(subject, body, to_emails):
    from_email = session.get('email')  # Use the logged-in user's email
    from_password = session.get('password')  # Use the logged-in user's password
    if not from_email or not from_password:
        print('User is not logged in or email credentials are missing.')
        return "User is not logged in or email credentials are missing."
    status = 'Sent'
    delivery_status = 'Delivered'
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        for to_email in to_emails:
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        print("Email sent success ")
        return "Emails sent successfully!"
    except Exception as e:
        status = 'Failed'
        delivery_status = 'Bounced'
        print("failed")
        return f"Failed to send emails: {str(e)}"
    
def extract_emails_from_csv(filepath):
    emails = {}
    try:
        with open(filepath, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if 'Email' in row and 'Email Subject' in row and 'Body' in row:
                    emails[row['Email']] = {'subject': row['Email Subject'], 'body': row['Body']}
    except Exception as e:
        print(f"Error reading CSV: {e}")
    return emails
    
@app.route('/email_customization', methods=['GET', 'POST'])
def email_customization():
    if 'uploaded_emails' not in session:
        flash('No emails uploaded. Please upload a CSV file first.', 'warning')
        return redirect(url_for('upload_csv'))
    emails = session.get('uploaded_emails', {})
    if request.method == 'POST':
        if request.form['recipient'] == 'other':
            recipient_email = request.form['otherEmail']
        else:
            recipient_email = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        result = send_email(subject, body, [recipient_email])
        if "Emails sent successfully!" in result:
            print('success')
            flash(result, 'success')
            return redirect(url_for('dashboard'))  
        else:
            flash(result, 'danger')
    print('email custom')
    return render_template('email_customization.html', emails=emails)

@app.route('/dashboard')
def dashboard():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM email_statuses")
    email_statuses = cur.fetchall() 
    cur.close()
    return render_template('dashboard.html', email_statuses=email_statuses)

@app.route('/update_status', methods=['POST'])
def update_status():
    company_name = request.form['company_name']
    email_status = request.form['email_status']
    delivery_status = request.form['delivery_status']
    opened = request.form['opened']
    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE email_statuses 
        SET email_status=%s, delivery_status=%s, opened=%s
        WHERE company_name=%s
    """, (email_status, delivery_status, opened, company_name))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('dashboard'))

if __name__ == "__main__":
    app.run(debug=True) 