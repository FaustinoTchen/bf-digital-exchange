import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename

template_dir = os.path.abspath('templates')
static_dir = os.path.abspath('static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SECRET_KEY'] = 'bf_digital_exchange_master_elite_2026'
app.config['UPLOAD_FOLDER'] = os.path.join(static_dir, 'uploads')
app.config['DATABASE'] = 'bf_exchange.db'

socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SENDER_EMAIL = 'bfdigital53@gmail.com'
SENDER_PASSWORD = 'fynjboihawuofvtl'

def send_email_with_pdf(to_email, subject, body, file_path, filename):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(SENDER_EMAIL, SENDER_PASSWORD)
        s.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"Erro E-mail com PDF: {e}")
        return False

def send_gmail_notification(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(SENDER_EMAIL, SENDER_PASSWORD)
        s.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"Erro E-mail: {e}")
        return False

def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                fullname TEXT, email TEXT, phone TEXT, password TEXT,
                iban_euro TEXT, iban_kz TEXT, 
                status TEXT DEFAULT 'Pendente', 
                rejection_count INTEGER DEFAULT 0, 
                id_document TEXT, half_body_photo TEXT,
                transfer_receipt TEXT, admin_receipt TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                username TEXT UNIQUE, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT, receiver TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    for col in [("transfer_receipt", "TEXT"), ("admin_receipt", "TEXT")]:
        try:
            c.execute(f"ALTER TABLE clients ADD COLUMN {col[0]} {col[1]}")
        except sqlite3.OperationalError:
            pass

    c.execute("INSERT OR IGNORE INTO admins (username, password, role) VALUES ('admin', 'adminpassword2026', 'Primário')")
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        iban_euro = request.form.get('iban_euro') or 'N/A'
        iban_kz = request.form.get('iban_kz') or 'N/A'
        
        id_f = request.files.get('id_document')
        photo_f = request.files.get('half_body_photo')
        
        id_filename = secure_filename(id_f.filename) if id_f and id_f.filename else None
        photo_filename = secure_filename(photo_f.filename) if photo_f and photo_f.filename else None

        if id_f and id_filename:
            id_f.save(os.path.join(app.config['UPLOAD_FOLDER'], id_filename))
        if photo_f and photo_filename:
            photo_f.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))

        conn = get_db()
        existing = conn.execute('SELECT * FROM clients WHERE email = ?', (email,)).fetchone()
        
        if existing:
            conn.execute('''
                UPDATE clients 
                SET fullname=?, phone=?, password=?, iban_euro=?, iban_kz=?, 
                    id_document=COALESCE(?, id_document), half_body_photo=COALESCE(?, half_body_photo), status='Pendente'
                WHERE email=?
            ''', (fullname, phone, password, iban_euro, iban_kz, id_filename, photo_filename, email))
            conn.commit()
        else:
            conn.execute('''
                INSERT INTO clients (fullname, email, phone, password, iban_euro, iban_kz, id_document, half_body_photo, status, rejection_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', 0)
            ''', (fullname, email, phone, password, iban_euro, iban_kz, id_filename, photo_filename))
            conn.commit()
        
        conn.close()
        send_gmail_notification(email, "Registo BF Digital", "O seu registo está em análise.")
        send_gmail_notification(SENDER_EMAIL, "Novo Registo", f"Cliente: {fullname} ({email})")
        session['client_email'] = email
        return redirect(url_for('client_dashboard'))
    return render_template('signup.html')

@app.route('/client-login', methods=['GET', 'POST'])
def client_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        conn = get_db()
        client = conn.execute('SELECT * FROM clients WHERE email=? AND password=?', (email, password)).fetchone()
        conn.close()
        if client:
            session['client_email'] = client['email']
            return redirect(url_for('client_dashboard'))
        flash('Email ou palavra-passe incorretos.')
    return render_template('client_login.html')

@app.route('/client-dashboard', methods=['GET', 'POST'])
def client_dashboard():
    email = session.get('client_email')
    if not email:
        return redirect(url_for('client_login'))
    
    conn = get_db()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if 'transfer_receipt' in request.files:
            try:
                receipt_f = request.files.get('transfer_receipt')
                if receipt_f and receipt_f.filename:
                    if receipt_f.filename.lower().endswith('.pdf'):
                        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                        receipt_filename = secure_filename(receipt_f.filename)
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], receipt_filename)
                        receipt_f.save(file_path)
                        
                        conn.execute('UPDATE clients SET transfer_receipt=?, status="Comprovativo Submetido - A Aguardar Validação" WHERE email=?', (receipt_filename, email))
                        conn.commit()
                        send_email_with_pdf(SENDER_EMAIL, f"Auditoria: Comprovativo de {email}", "Segue em anexo o PDF submetido pelo cliente.", file_path, receipt_filename)
                        flash('Comprovativo PDF enviado com sucesso e auditado por e-mail!')
                    else:
                        flash('Erro: Apenas são aceites ficheiros em formato PDF original!')
            except Exception as e:
                print(f"Erro upload: {e}")
                flash('Ocorreu um erro interno ao processar o ficheiro.')
        elif action == 'confirm_received':
            conn.execute('UPDATE clients SET status="Concluído - Fundos Liquidados" WHERE email=?', (email,))
            conn.commit()
            flash('Dinheiro confirmado na conta com sucesso! Transação concluída.')
                
    client = conn.execute('SELECT * FROM clients WHERE email=?', (email,)).fetchone()
    admins = conn.execute('SELECT username FROM admins').fetchall()
    conn.close()
    
    if not client:
        session.pop('client_email', None)
        return redirect(url_for('client_login'))
        
    return render_template('client_dashboard.html', client=client, admins=admins)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        admin = conn.execute('SELECT * FROM admins WHERE username=? AND password=?', 
                             (request.form['username'], request.form['password'])).fetchone()
        conn.close()
        if admin:
            session.update({'logged_in': True, 'username': admin['username'], 'role': admin['role']})
            return redirect(url_for('admin'))
        flash('Credenciais incorretas.')
    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    registos = conn.execute('SELECT * FROM clients ORDER BY id DESC').fetchall()
    admins = conn.execute('SELECT * FROM admins ORDER BY id ASC').fetchall()
    messages = conn.execute('SELECT * FROM messages ORDER BY id ASC').fetchall()
    conn.close()
    return render_template('admin.html', registos=registos, admins=admins, messages=messages, role=session.get('role'), username=session.get('username'))

@app.route('/admin/update_status/<int:id>', methods=['POST'])
def update_status(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    new_status = request.form.get('status')
    conn = get_db()
    c = conn.execute('SELECT * FROM clients WHERE id=?', (id,)).fetchone()
    conn.execute('UPDATE clients SET status=? WHERE id=?', (new_status, id))
    conn.commit()
    conn.close()
    
    if c and c['email']:
        socketio.emit('status_updated', {'status': new_status}, room=c['email'])
        if new_status in ['Aprovado', 'Concluído']:
            send_gmail_notification(c['email'], "Conta Aprovada", "A sua conta foi verificada! Aceda: http://127.0.0.1:5001/client-login")
            flash(f"APROVAR:{c['email']}:{c['fullname']}")
    return redirect(url_for('admin'))

@app.route('/admin/send_receipt/<int:id>', methods=['POST'])
def send_receipt(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    receipt_f = request.files.get('admin_receipt')
    if receipt_f and receipt_f.filename.lower().endswith('.pdf'):
        filename = secure_filename(receipt_f.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        receipt_f.save(file_path)
        conn = get_db()
        c = conn.execute('SELECT email FROM clients WHERE id=?', (id,)).fetchone()
        conn.execute('UPDATE clients SET admin_receipt=?, status="Comprovativo BF Enviado - Verificar Banco" WHERE id=?', (filename, id))
        conn.commit()
        conn.close()
        if c:
            send_email_with_pdf(c['email'], "BF Digital - Comprovativo Oficial", "Segue em anexo o comprovativo de transferência oficial emitido pela BF Digital Exchange.", file_path, filename)
            socketio.emit('receive_message', {'sender': 'Admin', 'content': 'O seu comprovativo de transferência oficial foi emitido e enviado por e-mail.'}, room=c['email'])
    return redirect(url_for('admin'))

@app.route('/admin/delete_client/<int:id>', methods=['POST'])
def delete_client(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM clients WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/add_admin', methods=['POST'])
def add_admin():
    if session.get('role') != 'Primário':
        return "Acesso Negado", 403
    conn = get_db()
    try:
        conn.execute('INSERT INTO admins (username, password, role) VALUES (?, ?, ?)', 
                     (request.form['username'], request.form['password'], request.form['role']))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_admin/<int:id>', methods=['POST'])
def delete_admin(id):
    if session.get('role') != 'Primário':
        return "Acesso Negado", 403
    conn = get_db()
    conn.execute('DELETE FROM admins WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@socketio.on('join')
def on_join(data):
    join_room(data['room'])

@socketio.on('send_message')
def handle_message(data):
    conn = get_db()
    conn.execute('INSERT INTO messages (sender, receiver, content) VALUES (?, ?, ?)', 
                 (data['sender'], data['receiver'], data['content']))
    conn.commit()
    conn.close()
    emit('receive_message', data, room=data['receiver'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)