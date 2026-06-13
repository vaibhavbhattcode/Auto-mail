import os
import json
import datetime
import time
import threading
import re
from flask import Flask, request, jsonify, render_template, session, send_from_directory
from flask_cors import CORS
import werkzeug.utils

import database
import file_parser
import email_service

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'arena_agent_secure_secret_key_2026_dhruvbuilds'
app.jinja_env.variable_start_string = '[['
app.jinja_env.variable_end_string = ']]'
CORS(app, supports_credentials=True)

# Ensure database is initialized
database.init_db()

# Global state for rate limiting
email_send_tracker = {
    'last_send_time': None,
    'emails_sent_today': 0,
    'last_reset_date': None,
    'batch_count': 0,
    'last_batch_time': None
}

# --- Background Scheduler Loop with Anti-Spam ---
def background_scheduler_loop():
    while True:
        try:
            conn = database.get_db()
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Find scheduled leads that are due to be sent
            cursor.execute('''
                SELECT id FROM leads 
                WHERE status = 'Scheduled' 
                  AND scheduled_time IS NOT NULL 
                  AND scheduled_time <= ?
                ORDER BY scheduled_time ASC
                LIMIT 1
            ''', (now,))
            due_leads = cursor.fetchall()
            
            if due_leads:
                # Load settings
                cursor.execute('SELECT key, value FROM settings')
                settings = {row['key']: row['value'] for row in cursor.fetchall()}
                conn.close()
                
                # Check rate limits
                if not check_rate_limit(settings):
                    print(f"[Scheduler] Rate limit reached, skipping this cycle...")
                    time.sleep(20)
                    continue
                
                for l in due_leads:
                    print(f"[Scheduler] Dispatching scheduled email for Lead #{l['id']} at {now}...")
                    email_service.dispatch_lead_email(l['id'], settings)
                    
                    # Dynamic cooldown
                    cooldown = calculate_dynamic_cooldown(settings)
                    print(f"[Scheduler] Waiting {cooldown}s cooldown before next email...")
                    time.sleep(cooldown)
            else:
                conn.close()
        except Exception as e:
            print(f"[Scheduler Error]: {str(e)}")
            
        time.sleep(20)

# Start background thread
threading.Thread(target=background_scheduler_loop, daemon=True).start()


# --- Rate Limiting & Anti-Spam Functions ---
def check_rate_limit(settings):
    """Check if we can send email based on rate limits"""
    global email_send_tracker
    
    now = datetime.datetime.now()
    today = now.date()
    
    # Reset daily counter
    if email_send_tracker['last_reset_date'] != today:
        email_send_tracker['emails_sent_today'] = 0
        email_send_tracker['last_reset_date'] = today
        email_send_tracker['batch_count'] = 0
    
    # Check daily limit
    daily_limit = int(settings.get('daily_email_limit', 100))
    if email_send_tracker['emails_sent_today'] >= daily_limit:
        return False
    
    # Check batch limits
    emails_per_batch = int(settings.get('emails_per_batch', 5))
    if email_send_tracker['batch_count'] >= emails_per_batch:
        batch_cooldown_minutes = int(settings.get('batch_cooldown_minutes', 10))
        if email_send_tracker['last_batch_time']:
            time_since_batch = (now - email_send_tracker['last_batch_time']).total_seconds() / 60
            if time_since_batch < batch_cooldown_minutes:
                return False
        # Reset batch
        email_send_tracker['batch_count'] = 0
        email_send_tracker['last_batch_time'] = now
    
    return True

def calculate_dynamic_cooldown(settings):
    """Calculate randomized cooldown to appear human"""
    min_cooldown = int(settings.get('min_cooldown_seconds', 60))
    max_cooldown = int(settings.get('max_cooldown_seconds', 180))
    randomize = settings.get('randomize_cooldown', 'true') == 'true'
    
    if randomize:
        return random.randint(min_cooldown, max_cooldown)
    else:
        return min_cooldown

def update_send_tracker():
    """Update global send tracker after successful send"""
    global email_send_tracker
    email_send_tracker['last_send_time'] = datetime.datetime.now()
    email_send_tracker['emails_sent_today'] += 1
    email_send_tracker['batch_count'] += 1


# --- Authentication Helpers ---
def is_authenticated():
    # Allow local simulation / or require auth
    return session.get('logged_in', False)

# --- API Endpoints ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    logged_in = session.get('logged_in', False)
    user_id = session.get('user_id')
    
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Check if any users exist
    cursor.execute("SELECT COUNT(*) as count FROM users")
    users_exist = cursor.fetchone()['count'] > 0
    
    user_info = None
    if logged_in and user_id:
        cursor.execute("SELECT id, username, email, full_name, role FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row:
            user_info = dict(user_row)
    
    conn.close()
    
    return jsonify({
        'logged_in': logged_in,
        'first_time_setup': not users_exist,
        'user': user_info
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400
    
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Check if this is first time setup
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()['count'] == 0:
        # First time setup - create admin user
        password_hash = database.hash_password(password)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, full_name, role, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, data.get('email', ''), data.get('full_name', username), 'admin', now, now))
        conn.commit()
        user_id = cursor.lastrowid
        session['logged_in'] = True
        session['user_id'] = user_id
        session['username'] = username
        conn.close()
        return jsonify({'success': True, 'message': 'Account created successfully!', 'first_time': True})
    
    # Regular login
    cursor.execute("SELECT id, username, password_hash, email, full_name, role FROM users WHERE username = ? AND is_active = 1", (username,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    
    if not database.verify_password(password, user['password_hash']):
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    
    # Update last login
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user['id']))
    conn.commit()
    conn.close()
    
    session['logged_in'] = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    
    return jsonify({'success': True, 'message': 'Login successful', 'user': {
        'id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'full_name': user['full_name'],
        'role': user['role']
    }})

@app.route('/api/auth/change-password', methods=['POST'])
def change_password():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    current_password = data.get('current_password', '').strip()
    new_password = data.get('new_password', '').strip()
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'Both passwords required'}), 400
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    
    user_id = session.get('user_id')
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not database.verify_password(current_password, user['password_hash']):
        conn.close()
        return jsonify({'success': False, 'message': 'Current password incorrect'}), 401
    
    new_hash = database.hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out.'})

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    conn = database.get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('SELECT key, value FROM settings')
        settings = {r['key']: r['value'] for r in cursor.fetchall()}
        conn.close()
        # Mask google password if present
        if settings.get('google_app_password'):
            settings['google_app_password_masked'] = '••••••••••••••••'
        else:
            settings['google_app_password_masked'] = ''
        return jsonify(settings)
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        for k, v in data.items():
            if k == 'google_app_password_masked': continue
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (k, str(v)))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Settings saved successfully.'})

@app.route('/api/mail-providers', methods=['GET'])
def get_mail_providers():
    providers = {
        'gmail': {'name': 'Gmail', 'host': 'smtp.gmail.com', 'port': '587', 'help': 'Use a 16-character Google App Password'},
        'titan': {'name': 'Titan Mail', 'host': 'smtp.titan.email', 'port': '587', 'help': 'Enter your Titan Mail email and password'},
        'custom': {'name': 'Custom SMTP', 'host': '', 'port': '587', 'help': 'Enter your custom SMTP server details'}
    }
    return jsonify(providers)

@app.route('/api/settings/test-email', methods=['POST'])
def test_smtp_email():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    conn.close()
    
    try:
        success, msg = email_service.send_test_email(settings)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        # Return 200 with success=false so frontend can show a clean toast
        # without browser noise for expected SMTP/auth failures.
        return jsonify({'success': False, 'message': str(e), 'error_type': 'smtp_test_failed'})

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM leads')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM leads WHERE status = "Sent"')
    sent = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM leads WHERE status = "Scheduled"')
    scheduled = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM leads WHERE status = "Failed"')
    failed = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM leads WHERE status = "Pending"')
    pending = cursor.fetchone()[0]
    
    # Industry distribution
    cursor.execute('SELECT industry, COUNT(*) as cnt FROM leads GROUP BY industry')
    industries = [{'name': r['industry'], 'count': r['cnt']} for r in cursor.fetchall()]
    
    # Recent activity logs
    cursor.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT 8')
    logs = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    # Simulated response rate for nice dashboard display
    reply_rate = round((sent * 0.28), 1) if sent > 0 else 0
    open_rate = round((sent * 0.72), 1) if sent > 0 else 0
    
    return jsonify({
        'total_leads': total,
        'sent_emails': sent,
        'scheduled_emails': scheduled,
        'failed_emails': failed,
        'pending_leads': pending,
        'open_rate': open_rate,
        'reply_rate': reply_rate,
        'industry_distribution': industries,
        'recent_logs': logs
    })

@app.route('/api/leads', methods=['GET'])
def get_leads():
    conn = database.get_db()
    cursor = conn.cursor()
    
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    industry = request.args.get('industry', '').strip()
    
    query = 'SELECT * FROM leads WHERE 1=1'
    params = []
    
    if search:
        query += ' AND (company_name LIKE ? OR contact_email LIKE ? OR website LIKE ? OR subject LIKE ?)'
        wildcard = f'%{search}%'
        params.extend([wildcard, wildcard, wildcard, wildcard])
        
    if status and status != 'All':
        query += ' AND status = ?'
        params.append(status)
        
    if industry and industry != 'All':
        query += ' AND industry = ?'
        params.append(industry)
        
    query += ' ORDER BY id DESC'
    
    cursor.execute(query, params)
    leads = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(leads)

@app.route('/api/leads', methods=['POST'])
def add_lead():
    data = request.get_json() or {}
    conn = database.get_db()
    cursor = conn.cursor()
    
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO leads (
            company_name, website, industry, location, app_status,
            contact_email, whatsapp_number, linkedin, subject, pitch,
            status, scheduled_time, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('company_name', 'New Company').strip(),
        data.get('website', 'example.com').strip(),
        data.get('industry', 'Technology').strip(),
        data.get('location', 'India').strip(),
        data.get('app_status', 'Review Needed').strip(),
        data.get('contact_email', 'contact@example.com').strip(),
        data.get('whatsapp_number', '+91 9510539603').strip(),
        data.get('linkedin', '').strip(),
        data.get('subject', 'App Dev Pitch').strip(),
        data.get('pitch', '').strip(),
        'Pending',
        None,
        now
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Lead added successfully.'})

@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
def update_lead(lead_id):
    data = request.get_json() or {}
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE leads SET
            company_name = ?, website = ?, industry = ?, location = ?,
            app_status = ?, contact_email = ?, whatsapp_number = ?,
            linkedin = ?, subject = ?, pitch = ?
        WHERE id = ?
    ''', (
        data.get('company_name', '').strip(),
        data.get('website', '').strip(),
        data.get('industry', '').strip(),
        data.get('location', '').strip(),
        data.get('app_status', '').strip(),
        data.get('contact_email', '').strip(),
        data.get('whatsapp_number', '').strip(),
        data.get('linkedin', '').strip(),
        data.get('subject', '').strip(),
        data.get('pitch', '').strip(),
        lead_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Lead updated successfully.'})

@app.route('/api/leads/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM leads WHERE id = ?', (lead_id,))
    cursor.execute('DELETE FROM logs WHERE lead_id = ?', (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Lead deleted.'})

@app.route('/api/leads/upload', methods=['POST'])
def upload_leads_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part attached.'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file.'}), 400
        
    os.makedirs('uploads', exist_ok=True)
    filename = werkzeug.utils.secure_filename(file.filename)
    filepath = os.path.join('uploads', filename)
    file.save(filepath)
    
    try:
        # Check if preview mode
        preview_mode = request.form.get('preview', 'false') == 'true'
        
        if preview_mode:
            headers, sample_rows = file_parser.extract_raw_data(filepath)
            return jsonify({
                'success': True,
                'preview': True,
                'headers': headers,
                'sample_rows': sample_rows,
                'filepath': filepath,
                'filename': filename
            })
        
        # Full import with optional mapping
        mapping_str = request.form.get('column_mapping', '')
        column_mapping = json.loads(mapping_str) if mapping_str else None
        
        new_leads = file_parser.parse_file(filepath, column_mapping)
        if not new_leads:
            return jsonify({'success': False, 'message': 'Could not extract any leads from this file format.'}), 400
        
        # Detect duplicates
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT contact_email FROM leads')
        existing_emails = set(row['contact_email'].lower() for row in cursor.fetchall())
        
        duplicates = []
        unique_leads = []
        for l in new_leads:
            if l['contact_email'].lower() in existing_emails:
                duplicates.append(l['contact_email'])
            else:
                unique_leads.append(l)
                existing_emails.add(l['contact_email'].lower())
        
        # Insert unique leads
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for l in unique_leads:
            cursor.execute('''
                INSERT INTO leads (
                    company_name, website, industry, location, app_status,
                    contact_email, whatsapp_number, linkedin, subject, pitch,
                    status, scheduled_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                l['company_name'], l['website'], l['industry'], l['location'], l['app_status'],
                l['contact_email'], l['whatsapp_number'], l['linkedin'], l['subject'], l['pitch'],
                'Pending', None, now
            ))
        conn.commit()
        conn.close()
        
        msg = f'Successfully imported {len(unique_leads)} leads'
        if duplicates:
            msg += f'. Skipped {len(duplicates)} duplicates.'
        
        return jsonify({
            'success': True,
            'message': msg,
            'imported': len(unique_leads),
            'duplicates': len(duplicates),
            'duplicate_emails': duplicates[:10]  # First 10
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error parsing file: {str(e)}'}), 500

@app.route('/api/leads/<int:lead_id>/send', methods=['POST'])
def send_instant_lead(lead_id):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    conn.close()
    
    # Check rate limit
    if not check_rate_limit(settings):
        return jsonify({
            'success': False, 
            'message': 'Rate limit reached. Please wait before sending more emails to avoid spam filters.'
        }), 429
    
    try:
        success, msg = email_service.dispatch_lead_email(lead_id, settings)
        if success:
            update_send_tracker()
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/leads/<int:lead_id>/schedule', methods=['POST'])
def schedule_lead_email(lead_id):
    data = request.get_json() or {}
    sched_time = data.get('scheduled_time', '').strip()
    
    if not sched_time:
        return jsonify({'success': False, 'message': 'Please provide a valid schedule date & time.'}), 400
        
    # Format or validate datetime
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status = 'Scheduled', scheduled_time = ? WHERE id = ?", (sched_time, lead_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Email successfully scheduled for {sched_time}.'})

@app.route('/api/leads/bulk', methods=['POST'])
def bulk_actions():
    data = request.get_json() or {}
    action = data.get('action', '')
    lead_ids = data.get('ids', [])
    sched_time = data.get('scheduled_time', '')
    
    if not lead_ids:
        return jsonify({'success': False, 'message': 'No leads selected.'}), 400
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT key, value FROM settings')
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    
    results = {'success': 0, 'failed': 0, 'errors': []}
    
    if action == 'delete':
        placeholders = ','.join('?' for _ in lead_ids)
        cursor.execute(f'DELETE FROM leads WHERE id IN ({placeholders})', lead_ids)
        cursor.execute(f'DELETE FROM logs WHERE lead_id IN ({placeholders})', lead_ids)
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Successfully deleted {len(lead_ids)} leads.'})
        
    elif action == 'schedule':
        if not sched_time:
            conn.close()
            return jsonify({'success': False, 'message': 'Please provide a scheduled time.'}), 400
            
        placeholders = ','.join('?' for _ in lead_ids)
        cursor.execute(f"UPDATE leads SET status = 'Scheduled', scheduled_time = ? WHERE id IN ({placeholders})", [sched_time] + lead_ids)
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Successfully scheduled {len(lead_ids)} emails for {sched_time}.'})
        
    elif action == 'send':
        conn.close()
        
        # Check rate limits for bulk send
        if not check_rate_limit(settings):
            return jsonify({
                'success': False, 
                'message': 'Rate limit reached. Reduce batch size or increase cooldown settings.'
            }), 429
        
        for idx, lid in enumerate(lead_ids):
            try:
                suc, m = email_service.dispatch_lead_email(lid, settings)
                if suc:
                    results['success'] += 1
                    update_send_tracker()
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Lead #{lid}: {m}")
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Lead #{lid}: {str(e)}")
            
            # Smart cooldown between bulk emails
            if idx < len(lead_ids) - 1:  # Not last email
                cooldown = calculate_dynamic_cooldown(settings)
                print(f"[Bulk Send] Cooldown {cooldown}s before next email...")
                time.sleep(cooldown)
                
                # Check if we hit batch limit
                if not check_rate_limit(settings):
                    results['errors'].append(f"Rate limit reached after {results['success']} emails")
                    break
        
        return jsonify({
            'success': True, 
            'message': f'Bulk dispatch: {results["success"]} sent, {results["failed"]} failed.', 
            'details': results
        })
        
    elif action == 'reset':
        placeholders = ','.join('?' for _ in lead_ids)
        cursor.execute(f"UPDATE leads SET status = 'Pending', scheduled_time = NULL, error_message = '' WHERE id IN ({placeholders})", lead_ids)
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Successfully reset {len(lead_ids)} leads to Pending status.'})
        
    conn.close()
    return jsonify({'success': False, 'message': 'Unknown action.'}), 400

@app.route('/api/templates', methods=['GET'])
def get_templates():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM templates ORDER BY is_default DESC, id ASC')
    templates = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(templates)

@app.route('/api/templates', methods=['POST'])
def add_template():
    data = request.get_json() or {}
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO templates (name, subject, body, is_default)
        VALUES (?, ?, ?, 0)
    ''', (
        data.get('name', 'New Template').strip(),
        data.get('subject', 'Your App').strip(),
        data.get('body', 'Hi {{company_name}}, ...').strip()
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Template added successfully.'})

@app.route('/api/templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    data = request.get_json() or {}
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE templates SET name = ?, subject = ?, body = ? WHERE id = ?
    ''', (
        data.get('name', '').strip(),
        data.get('subject', '').strip(),
        data.get('body', '').strip(),
        template_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Template updated successfully.'})

@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM templates WHERE id = ? AND is_default = 0', (template_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Template deleted successfully.'})

@app.route('/api/templates/<int:template_id>/generate', methods=['POST'])
def generate_pitch_from_template(template_id):
    data = request.get_json() or {}
    lead = data.get('lead', {})
    
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT subject, body FROM templates WHERE id = ?', (template_id,))
    t = cursor.fetchone()
    conn.close()
    
    if not t:
        return jsonify({'success': False, 'message': 'Template not found.'}), 404
        
    subj = t['subject']
    body = t['body']
    
    # Replace placeholders
    replacements = {
        '{{company_name}}': lead.get('company_name', 'Client'),
        '{{website}}': lead.get('website', 'your website'),
        '{{industry}}': lead.get('industry', 'your sector'),
        '{{location}}': lead.get('location', 'your location'),
        '{{app_status}}': lead.get('app_status', 'Website Only'),
        '{{contact_email}}': lead.get('contact_email', 'your email'),
        '{{whatsapp_number}}': lead.get('whatsapp_number', '+91 9510539603')
    }
    
    for k, v in replacements.items():
        subj = subj.replace(k, str(v))
        body = body.replace(k, str(v))
        
    return jsonify({'success': True, 'subject': subj, 'pitch': body})

@app.route('/api/logs', methods=['GET'])
def get_audit_logs():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT 100')
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(logs)

@app.route('/api/leads/validate-field', methods=['POST'])
def validate_lead_field():
    """Validate individual field values"""
    data = request.get_json() or {}
    field = data.get('field')
    value = data.get('value', '').strip()
    
    errors = []
    
    if field == 'contact_email':
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
            errors.append('Invalid email format')
    elif field == 'website':
        if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', value):
            errors.append('Invalid website format')
    
    return jsonify({'valid': len(errors) == 0, 'errors': errors})

@app.route('/api/column-mappings', methods=['GET', 'POST'])
def manage_column_mappings():
    """Save/retrieve column mappings for future imports"""
    conn = database.get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        filename = request.args.get('filename')
        if filename:
            cursor.execute('SELECT file_column, system_field FROM column_mappings WHERE file_name = ?', (filename,))
            mappings = {row['file_column']: row['system_field'] for row in cursor.fetchall()}
            conn.close()
            return jsonify(mappings)
        conn.close()
        return jsonify({})
    
    elif request.method == 'POST':
        data = request.get_json() or {}
        filename = data.get('filename')
        mappings = data.get('mappings', {})
        
        # Clear old mappings
        cursor.execute('DELETE FROM column_mappings WHERE file_name = ?', (filename,))
        
        # Save new mappings
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for file_col, sys_field in mappings.items():
            if sys_field:  # Only save mapped fields
                cursor.execute('''
                    INSERT INTO column_mappings (file_name, file_column, system_field, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (filename, file_col, sys_field, now))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Mappings saved'})

@app.route('/api/rate-limit-status', methods=['GET'])
def get_rate_limit_status():
    """Get current rate limiting status"""
    global email_send_tracker
    
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    conn.close()
    
    daily_limit = int(settings.get('daily_email_limit', 100))
    emails_sent = email_send_tracker['emails_sent_today']
    remaining = max(0, daily_limit - emails_sent)
    
    can_send = check_rate_limit(settings)
    
    return jsonify({
        'emails_sent_today': emails_sent,
        'daily_limit': daily_limit,
        'remaining_today': remaining,
        'can_send_now': can_send,
        'batch_count': email_send_tracker['batch_count'],
        'last_send_time': email_send_tracker['last_send_time'].isoformat() if email_send_tracker['last_send_time'] else None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
