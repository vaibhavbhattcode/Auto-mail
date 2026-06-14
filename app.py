import os
import json
import datetime
import time
import threading
import re
import random
import urllib.parse
from flask import Flask, request, jsonify, render_template, session, make_response, send_file, render_template_string
from flask_cors import CORS
import werkzeug.utils

import database
import file_parser
import email_service
import export_service

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

# Helper to verify campaign completion status
def check_and_update_campaign_completion(campaign_id):
    conn = database.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM leads WHERE campaign_id = ? AND status IN ('Pending', 'Processing')", (campaign_id,))
        remaining = cursor.fetchone()['cnt']
        
        if remaining == 0:
            cursor.execute("SELECT status FROM campaigns WHERE id = ?", (campaign_id,))
            camp = cursor.fetchone()
            if camp and camp['status'] in ('running', 'scheduled'):
                # Check if there were any failures or if all sent successfully
                cursor.execute("SELECT COUNT(*) as failed_cnt FROM leads WHERE campaign_id = ? AND status = 'Failed'", (campaign_id,))
                failed_leads = cursor.fetchone()['failed_cnt']
                
                cursor.execute("SELECT COUNT(*) FROM leads WHERE campaign_id = ?", (campaign_id,))
                total_leads = cursor.fetchone()[0]
                
                new_status = 'completed'
                if failed_leads > 0:
                    new_status = 'failed' if failed_leads == total_leads else 'completed'
                    
                cursor.execute("UPDATE campaigns SET status = ?, updated_at = ? WHERE id = ?", 
                               (new_status, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), campaign_id))
                conn.commit()
    finally:
        conn.close()

# --- Background Scheduler Loop ---
def background_scheduler_loop():
    while True:
        conn = None
        try:
            conn = database.get_db()
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Find active campaigns
            cursor.execute("SELECT id FROM campaigns WHERE status IN ('running', 'scheduled')")
            active_campaign_ids = [row['id'] for row in cursor.fetchall()]
            
            if active_campaign_ids:
                # Find due leads in active campaigns
                placeholders = ','.join('?' for _ in active_campaign_ids)
                cursor.execute(f'''
                    SELECT id, campaign_id FROM leads 
                    WHERE status = 'Pending' 
                      AND scheduled_time IS NOT NULL 
                      AND scheduled_time <= ?
                      AND campaign_id IN ({placeholders})
                    ORDER BY scheduled_time ASC
                    LIMIT 1
                ''', [now] + active_campaign_ids)
                
                due_lead = cursor.fetchone()
                
                if due_lead:
                    lead_id = due_lead['id']
                    campaign_id = due_lead['campaign_id']
                    
                    # Load global settings
                    cursor.execute('SELECT key, value FROM settings')
                    settings = {row['key']: row['value'] for row in cursor.fetchall()}
                    
                    # Close scheduler db connection before launching the send task to keep it free
                    conn.close()
                    conn = None
                    
                    # Check global rate limits
                    if not check_rate_limit(settings):
                        print(f"[Scheduler] Rate limit reached, skipping this cycle...")
                        time.sleep(15)
                        continue
                    
                    print(f"[Scheduler] Dispatching scheduled lead #{lead_id} at {now}")
                    
                    # Update status to processing
                    conn_update = database.get_db()
                    try:
                        cursor_up = conn_update.cursor()
                        cursor_up.execute("UPDATE leads SET status = 'Processing' WHERE id = ?", (lead_id,))
                        conn_update.commit()
                    finally:
                        conn_update.close()
                    
                    success, msg = email_service.dispatch_lead_email(lead_id, settings)
                    
                    if success:
                        update_send_tracker()
                        
                    # Cooldown interval
                    cooldown = calculate_dynamic_cooldown(settings)
                    print(f"[Scheduler] Waiting {cooldown}s cooldown...")
                    time.sleep(cooldown)
                    
                    # Check campaign completion
                    check_and_update_campaign_completion(campaign_id)
                else:
                    conn.close()
                    conn = None
            else:
                conn.close()
                conn = None
        except Exception as e:
            print(f"[Scheduler Error]: {str(e)}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
            
        time.sleep(10)

# Start background thread
threading.Thread(target=background_scheduler_loop, daemon=True).start()

# --- Rate Limiting & Anti-Spam Functions ---
def check_rate_limit(settings):
    global email_send_tracker
    now = datetime.datetime.now()
    today = now.date()
    
    if email_send_tracker['last_reset_date'] != today:
        email_send_tracker['emails_sent_today'] = 0
        email_send_tracker['last_reset_date'] = today
        email_send_tracker['batch_count'] = 0
        
    daily_limit = int(settings.get('daily_email_limit', 500))
    if email_send_tracker['emails_sent_today'] >= daily_limit:
        return False
        
    emails_per_batch = int(settings.get('emails_per_batch', 5))
    if email_send_tracker['batch_count'] >= emails_per_batch:
        batch_cooldown = int(settings.get('batch_cooldown_minutes', 5))
        if email_send_tracker['last_batch_time']:
            elapsed = (now - email_send_tracker['last_batch_time']).total_seconds() / 60
            if elapsed < batch_cooldown:
                return False
        email_send_tracker['batch_count'] = 0
        email_send_tracker['last_batch_time'] = now
        
    return True

def calculate_dynamic_cooldown(settings):
    min_cooldown = int(settings.get('min_cooldown_seconds', 10))
    max_cooldown = int(settings.get('max_cooldown_seconds', 30))
    randomize = settings.get('randomize_cooldown', 'true') == 'true'
    
    if randomize:
        return random.randint(min_cooldown, max_cooldown)
    else:
        return min_cooldown

def update_send_tracker():
    global email_send_tracker
    email_send_tracker['last_send_time'] = datetime.datetime.now()
    email_send_tracker['emails_sent_today'] += 1
    email_send_tracker['batch_count'] += 1

# --- Authentication Middleware Helper ---
def get_logged_in_user():
    if not session.get('logged_in'):
        return None
    return session.get('user_id')

# --- API Endpoints ---

@app.route('/')
def index():
    # Auto-update tracking domain based on current access URL
    conn = None
    try:
        current_origin = request.url_root.rstrip('/')
        is_current_public = 'localhost' not in current_origin and '127.0.0.1' not in current_origin
        
        # Force HTTPS for public environments to prevent mixed content blocking in email clients
        if is_current_public and current_origin.startswith('http://'):
            current_origin = current_origin.replace('http://', 'https://', 1)
            
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'tracking_domain'")
        row = cursor.fetchone()
        saved_domain = row['value'] if row else None
        
        is_saved_public = saved_domain and 'localhost' not in saved_domain and '127.0.0.1' not in saved_domain
        
        # Ensure saved domain is also HTTPS if public
        if is_saved_public and saved_domain.startswith('http://'):
            saved_domain = saved_domain.replace('http://', 'https://', 1)
            
        # Update conditions:
        # 1. Current origin is public (always update to public domain for live tracking)
        # 2. Or, the saved domain is not public and current origin is different
        should_update = False
        if is_current_public and saved_domain != current_origin:
            should_update = True
        elif not is_saved_public and saved_domain != current_origin:
            should_update = True
            
        if should_update and current_origin:
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('tracking_domain', ?)", (current_origin,))
            conn.commit()
            print(f"[Auto-Settings] Automatically updated tracking_domain to {current_origin}")
    except Exception as e:
        print(f"[Auto-Settings Error] Failed to update tracking domain: {str(e)}")
    finally:
        if conn:
            conn.close()

    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    logged_in = session.get('logged_in', False)
    user_id = session.get('user_id')
    
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users")
    users_exist = cursor.fetchone()['count'] > 0
    
    user_info = None
    if logged_in and user_id:
        cursor.execute("SELECT id, email, full_name FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            user_info = dict(row)
            
    conn.close()
    return jsonify({
        'logged_in': logged_in,
        'first_time_setup': not users_exist,
        'user': user_info
    })

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    full_name = data.get('full_name', '').strip() or email.split('@')[0]
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password required.'}), 400
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Check duplicate
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Email already registered.'}), 400
        
    pass_hash = database.hash_password(password)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (email, email, pass_hash, full_name, now))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        session['logged_in'] = True
        session['user_id'] = user_id
        session['email'] = email
        
        return jsonify({'success': True, 'message': 'Account registered successfully.'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password required.'}), 400
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if not user or not database.verify_password(password, user['password_hash']):
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401
        
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user['id']))
    conn.commit()
    conn.close()
    
    session['logged_in'] = True
    session['user_id'] = user['id']
    session['email'] = user['email']
    
    return jsonify({
        'success': True, 
        'message': 'Logged in successfully.',
        'user': {'id': user['id'], 'email': user['email'], 'full_name': user['full_name']}
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out.'})

# --- Settings ---
@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('SELECT key, value FROM settings')
        settings = {r['key']: r['value'] for r in cursor.fetchall()}
        conn.close()
        return jsonify(settings)
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        for k, v in data.items():
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (k, str(v)))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Settings saved successfully.'})

# --- SMTP Accounts CRUD ---
@app.route('/api/smtp-accounts', methods=['GET', 'POST'])
def manage_smtp_accounts():
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute('SELECT id, email_address, sender_name, smtp_host, smtp_port, ssl_tls FROM smtp_accounts WHERE user_id = ?', (user_id,))
        accounts = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(accounts)
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        email_address = data.get('email_address', '').strip()
        smtp_host = data.get('smtp_host', '').strip()
        smtp_port = int(data.get('smtp_port', 587))
        ssl_tls = data.get('ssl_tls', 'tls').strip()
        password = data.get('password', '').strip()
        sender_name = data.get('sender_name', '').strip()
        
        if not email_address or not smtp_host or not password:
            conn.close()
            return jsonify({'success': False, 'message': 'Email, SMTP Host, and Password are required.'}), 400
            
        pass_encrypted = database.encrypt_password(password)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
            INSERT INTO smtp_accounts (user_id, email_address, sender_name, smtp_host, smtp_port, ssl_tls, password_encrypted, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, email_address, sender_name, smtp_host, smtp_port, ssl_tls, pass_encrypted, now))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'SMTP Account added successfully.'})

@app.route('/api/smtp-accounts/<int:account_id>', methods=['PUT', 'DELETE'])
def update_delete_smtp_account(account_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Ownership check
    cursor.execute("SELECT id FROM smtp_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Account not found.'}), 404
        
    if request.method == 'PUT':
        data = request.get_json() or {}
        email_address = data.get('email_address', '').strip()
        smtp_host = data.get('smtp_host', '').strip()
        smtp_port = int(data.get('smtp_port', 587))
        ssl_tls = data.get('ssl_tls', 'tls').strip()
        sender_name = data.get('sender_name', '').strip()
        
        cursor.execute('''
            UPDATE smtp_accounts 
            SET email_address = ?, sender_name = ?, smtp_host = ?, smtp_port = ?, ssl_tls = ?
            WHERE id = ?
        ''', (email_address, sender_name, smtp_host, smtp_port, ssl_tls, account_id))
        
        # If updating password
        password = data.get('password', '').strip()
        if password and password != '••••••••••••••••':
            pass_encrypted = database.encrypt_password(password)
            cursor.execute("UPDATE smtp_accounts SET password_encrypted = ? WHERE id = ?", (pass_encrypted, account_id))
            
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'SMTP Account updated successfully.'})
        
    elif request.method == 'DELETE':
        cursor.execute("DELETE FROM smtp_accounts WHERE id = ?", (account_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'SMTP Account deleted successfully.'})

@app.route('/api/smtp-accounts/<int:account_id>/test', methods=['POST'])
def test_smtp_account(account_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM smtp_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
    account = cursor.fetchone()
    conn.close()
    
    if not account:
        return jsonify({'success': False, 'message': 'SMTP account not found.'}), 404
        
    account = dict(account)
    account['password'] = database.decrypt_password(account['password_encrypted'])
    
    try:
        success, msg = email_service.send_test_email(account)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# --- Campaigns CRUD ---
@app.route('/api/campaigns', methods=['GET', 'POST'])
def manage_campaigns():
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        search = request.args.get('search', '').strip()
        status = request.args.get('status', 'All').strip()
        
        query = "SELECT c.*, s.email_address as smtp_email FROM campaigns c LEFT JOIN smtp_accounts s ON c.smtp_account_id = s.id WHERE c.created_by = ?"
        params = [user_id]
        
        if search:
            query += " AND (c.name LIKE ? OR c.description LIKE ?)"
            wild = f"%{search}%"
            params.extend([wild, wild])
            
        if status != 'All':
            query += " AND c.status = ?"
            params.append(status.lower())
            
        query += " ORDER BY c.id DESC"
        
        cursor.execute(query, params)
        campaigns = []
        for row in cursor.fetchall():
            c = dict(row)
            # Count leads status
            cursor.execute("SELECT status, COUNT(*) as cnt FROM leads WHERE campaign_id = ? GROUP BY status", (c['id'],))
            counts = {r['status']: r['cnt'] for r in cursor.fetchall()}
            
            c['total_leads'] = sum(counts.values())
            c['sent_count'] = counts.get('Sent', 0)
            c['failed_count'] = counts.get('Failed', 0)
            c['pending_count'] = counts.get('Pending', 0) + counts.get('Processing', 0)
            c['scheduled_count'] = counts.get('Scheduled', 0)
            
            # Engagement rates
            cursor.execute("SELECT COUNT(*) FROM leads WHERE campaign_id = ? AND open_count > 0", (c['id'],))
            c['opened_count'] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM leads WHERE campaign_id = ? AND click_count > 0", (c['id'],))
            c['clicked_count'] = cursor.fetchone()[0]
            
            campaigns.append(c)
            
        conn.close()
        return jsonify(campaigns)
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        smtp_account_id = data.get('smtp_account_id')
        
        if not name:
            conn.close()
            return jsonify({'success': False, 'message': 'Campaign name is required.'}), 400
            
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO campaigns (name, description, status, smtp_account_id, created_by, created_at, updated_at)
            VALUES (?, ?, 'draft', ?, ?, ?, ?)
        ''', (name, description, smtp_account_id, user_id, now, now))
        conn.commit()
        campaign_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'success': True, 'message': 'Campaign created successfully.', 'campaign_id': campaign_id})

@app.route('/api/campaigns/<int:campaign_id>', methods=['PUT', 'DELETE'])
def update_delete_campaign(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Ownership
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    if request.method == 'PUT':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        smtp_account_id = data.get('smtp_account_id')
        
        if not name:
            conn.close()
            return jsonify({'success': False, 'message': 'Campaign name is required.'}), 400
            
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            UPDATE campaigns 
            SET name = ?, description = ?, smtp_account_id = ?, updated_at = ?
            WHERE id = ?
        ''', (name, description, smtp_account_id, now, campaign_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Campaign updated successfully.'})
        
    elif request.method == 'DELETE':
        # Delete campaign and leads
        cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        cursor.execute("DELETE FROM leads WHERE campaign_id = ?", (campaign_id,))
        cursor.execute("DELETE FROM tracking_logs WHERE campaign_id = ?", (campaign_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Campaign and associated leads deleted successfully.'})

@app.route('/api/campaigns/<int:campaign_id>/duplicate', methods=['POST'])
def duplicate_campaign(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    campaign = cursor.fetchone()
    if not campaign:
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    campaign = dict(campaign)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_name = f"Copy of {campaign['name']}"
    
    cursor.execute('''
        INSERT INTO campaigns (name, description, status, smtp_account_id, created_by, created_at, updated_at)
        VALUES (?, ?, 'draft', ?, ?, ?, ?)
    ''', (new_name, campaign['description'], campaign['smtp_account_id'], user_id, now, now))
    new_campaign_id = cursor.lastrowid
    
    # Duplicate leads inside campaign (resetting statuses)
    cursor.execute("SELECT * FROM leads WHERE campaign_id = ?", (campaign_id,))
    leads = cursor.fetchall()
    
    for lead in leads:
        lead = dict(lead)
        cursor.execute('''
            INSERT INTO leads (
                campaign_id, recipient_email, cc, bcc, subject, body, attachments, variables, 
                status, scheduled_time, retry_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', NULL, 0, ?, ?)
        ''', (
            new_campaign_id, lead['recipient_email'], lead['cc'], lead['bcc'], lead['subject'], 
            lead['body'], lead['attachments'], lead['variables'], now, now
        ))
        
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Campaign duplicated as "{new_name}".', 'campaign_id': new_campaign_id})

@app.route('/api/campaigns/<int:campaign_id>/pause', methods=['POST'])
def pause_campaign(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE campaigns SET status = 'paused' WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Campaign paused.'})

@app.route('/api/campaigns/<int:campaign_id>/resume', methods=['POST'])
def resume_campaign(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Check if there are scheduled times
    cursor.execute("SELECT COUNT(*) FROM leads WHERE campaign_id = ? AND scheduled_time IS NOT NULL", (campaign_id,))
    has_scheduled = cursor.fetchone()[0] > 0
    
    status = 'scheduled' if has_scheduled else 'running'
    
    cursor.execute("UPDATE campaigns SET status = ? WHERE id = ? AND created_by = ?", (status, campaign_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Campaign activated ({status.capitalize()}).'})

@app.route('/api/campaigns/<int:campaign_id>/cancel', methods=['POST'])
def cancel_campaign(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE campaigns SET status = 'cancelled' WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    cursor.execute("UPDATE leads SET scheduled_time = NULL WHERE campaign_id = ? AND status = 'Pending'", (campaign_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Campaign cancelled and scheduled times cleared.'})

@app.route('/api/campaigns/<int:campaign_id>/archive', methods=['POST'])
def archive_campaign(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE campaigns SET status = 'archived' WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Campaign archived.'})

@app.route('/api/campaigns/<int:campaign_id>/bulk-schedule', methods=['POST'])
def bulk_schedule(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.get_json() or {}
    start_time_str = data.get('start_time', '').strip() # e.g. "2026-06-14 10:00:00"
    interval = int(data.get('interval', 0)) # in minutes
    
    if not start_time_str:
        return jsonify({'success': False, 'message': 'Start time is required.'}), 400
        
    try:
        start_time = datetime.datetime.strptime(start_time_str.replace('T', ' '), "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            start_time = datetime.datetime.strptime(start_time_str.replace('T', ' '), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid date format. Use YYYY-MM-DD HH:MM.'}), 400
            
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Ownership
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    # Get all Pending leads in this campaign
    cursor.execute("SELECT id FROM leads WHERE campaign_id = ? AND status = 'Pending' ORDER BY id ASC", (campaign_id,))
    leads = cursor.fetchall()
    
    current_time = start_time
    for lead in leads:
        lead_id = lead['id']
        sched_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE leads SET scheduled_time = ? WHERE id = ?", (sched_time_str, lead_id))
        current_time += datetime.timedelta(minutes=interval)
        
    cursor.execute("UPDATE campaigns SET status = 'scheduled', start_time = ?, sending_interval = ? WHERE id = ?", 
                   (start_time_str, interval, campaign_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Successfully scheduled {len(leads)} emails with a {interval}-minute interval.'})

# --- Leads CRUD under Campaign ---
@app.route('/api/campaigns/<int:campaign_id>/leads', methods=['GET', 'POST'])
def manage_campaign_leads(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Ownership check
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    if request.method == 'GET':
        search = request.args.get('search', '').strip()
        status = request.args.get('status', 'All').strip()
        
        query = "SELECT * FROM leads WHERE campaign_id = ?"
        params = [campaign_id]
        
        if search:
            query += " AND (recipient_email LIKE ? OR subject LIKE ? OR body LIKE ? OR variables LIKE ?)"
            wild = f"%{search}%"
            params.extend([wild, wild, wild, wild])
            
        if status != 'All':
            query += " AND status = ?"
            params.append(status)
            
        query += " ORDER BY id DESC"
        
        cursor.execute(query, params)
        leads = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(leads)
        
    elif request.method == 'POST':
        import re
        data = request.get_json() or {}
        recipient_email = data.get('recipient_email', '').strip()
        emails_str = data.get('emails', '').strip()
        cc = data.get('cc', '').strip()
        bcc = data.get('bcc', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        attachments = data.get('attachments', '[]')
        variables = data.get('variables', '{}')
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if emails_str:
            # Bulk manual addition
            emails = [e.strip() for e in re.split(r'[,\n;]+', emails_str) if e.strip()]
            valid_emails = [e for e in emails if '@' in e]
            if not valid_emails:
                conn.close()
                return jsonify({'success': False, 'message': 'No valid emails found in the list.'}), 400
                
            inserted = 0
            for email in valid_emails:
                cursor.execute('''
                    INSERT INTO leads (campaign_id, recipient_email, cc, bcc, subject, body, attachments, variables, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
                ''', (campaign_id, email, cc, bcc, subject, body, attachments, variables, now, now))
                inserted += 1
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': f'Successfully added {inserted} leads manually.'})
        else:
            # Single manual addition
            if not recipient_email:
                conn.close()
                return jsonify({'success': False, 'message': 'Recipient email is required.'}), 400
                
            cursor.execute('''
                INSERT INTO leads (campaign_id, recipient_email, cc, bcc, subject, body, attachments, variables, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
            ''', (campaign_id, recipient_email, cc, bcc, subject, body, attachments, variables, now, now))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'Lead added successfully.'})

# --- Bulk Lead Actions ---
@app.route('/api/campaigns/<int:campaign_id>/leads/bulk-schedule', methods=['POST'])
def bulk_schedule_selected_leads(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    data = request.get_json() or {}
    lead_ids = data.get('lead_ids', [])
    start_time_str = data.get('start_time', '').strip()
    interval = int(data.get('interval', 0))
    
    if not lead_ids:
        conn.close()
        return jsonify({'success': False, 'message': 'No leads selected.'}), 400
    if not start_time_str:
        conn.close()
        return jsonify({'success': False, 'message': 'Start time is required.'}), 400
        
    try:
        start_time = datetime.datetime.strptime(start_time_str.replace('T', ' '), "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            start_time = datetime.datetime.strptime(start_time_str.replace('T', ' '), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid date format.'}), 400
            
    placeholders = ','.join('?' for _ in lead_ids)
    cursor.execute(f"SELECT id FROM leads WHERE id IN ({placeholders}) AND campaign_id = ? AND status = 'Pending' ORDER BY id ASC", (*lead_ids, campaign_id))
    leads = cursor.fetchall()
    
    current_time = start_time
    for lead in leads:
        lead_id = lead['id']
        sched_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE leads SET scheduled_time = ? WHERE id = ?", (sched_time_str, lead_id))
        current_time += datetime.timedelta(minutes=interval)
        
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Scheduled {len(leads)} selected emails with a {interval}-minute interval.'})

def run_bulk_dispatch_in_background(campaign_id, lead_ids, settings):
    import time
    for lead_id in lead_ids:
        try:
            if not check_rate_limit(settings):
                print(f"[Bulk Dispatch] Rate limit reached, stopping bulk send.")
                break
            conn_update = database.get_db()
            try:
                cursor_up = conn_update.cursor()
                cursor_up.execute("UPDATE leads SET status = 'Processing' WHERE id = ?", (lead_id,))
                conn_update.commit()
            finally:
                conn_update.close()
                
            success, msg = email_service.dispatch_lead_email(lead_id, settings)
            if success:
                update_send_tracker()
            cooldown = calculate_dynamic_cooldown(settings)
            time.sleep(cooldown)
        except Exception as e:
            print(f"[Bulk Dispatch Error] Failed for lead #{lead_id}: {str(e)}")
    try:
        check_and_update_campaign_completion(campaign_id)
    except Exception as e:
        print(f"[Bulk Dispatch Error] Failed completion check: {str(e)}")

@app.route('/api/campaigns/<int:campaign_id>/leads/bulk-dispatch', methods=['POST'])
def bulk_dispatch_selected_leads(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    data = request.get_json() or {}
    lead_ids = data.get('lead_ids', [])
    if not lead_ids:
        conn.close()
        return jsonify({'success': False, 'message': 'No leads selected.'}), 400
        
    cursor.execute("SELECT key, value FROM settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    
    import threading
    threading.Thread(target=run_bulk_dispatch_in_background, args=(campaign_id, lead_ids, settings), daemon=True).start()
    return jsonify({'success': True, 'message': f'Started background dispatch for {len(lead_ids)} selected emails.'})

@app.route('/api/campaigns/<int:campaign_id>/leads/bulk-reset', methods=['POST'])
def bulk_reset_selected_leads(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    data = request.get_json() or {}
    lead_ids = data.get('lead_ids', [])
    if not lead_ids:
        conn.close()
        return jsonify({'success': False, 'message': 'No leads selected.'}), 400
        
    placeholders = ','.join('?' for _ in lead_ids)
    cursor.execute(f'''
        UPDATE leads 
        SET status = 'Pending', scheduled_time = NULL, sent_time = NULL, error_message = NULL, open_count = 0, click_count = 0
        WHERE id IN ({placeholders}) AND campaign_id = ?
    ''', (*lead_ids, campaign_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Successfully reset {len(lead_ids)} leads back to Pending.'})

@app.route('/api/campaigns/<int:campaign_id>/leads/bulk-delete', methods=['POST'])
def bulk_delete_selected_leads(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    data = request.get_json() or {}
    lead_ids = data.get('lead_ids', [])
    if not lead_ids:
        conn.close()
        return jsonify({'success': False, 'message': 'No leads selected.'}), 400
        
    placeholders = ','.join('?' for _ in lead_ids)
    cursor.execute(f"DELETE FROM leads WHERE id IN ({placeholders}) AND campaign_id = ?", (*lead_ids, campaign_id))
    cursor.execute(f"DELETE FROM tracking_logs WHERE lead_id IN ({placeholders})", tuple(lead_ids))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Successfully deleted {len(lead_ids)} leads.'})

@app.route('/api/campaigns/<int:campaign_id>/leads/<int:lead_id>', methods=['PUT', 'DELETE'])
def update_delete_lead(campaign_id, lead_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Ownership
    cursor.execute("SELECT id FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    if request.method == 'PUT':
        data = request.get_json() or {}
        recipient_email = data.get('recipient_email', '').strip()
        cc = data.get('cc', '').strip()
        bcc = data.get('bcc', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '').strip()
        variables = data.get('variables', '{}')
        status = data.get('status', 'Pending')
        scheduled_time = data.get('scheduled_time')
        
        cursor.execute('''
            UPDATE leads 
            SET recipient_email = ?, cc = ?, bcc = ?, subject = ?, body = ?, variables = ?, status = ?, scheduled_time = ?, updated_at = ?
            WHERE id = ? AND campaign_id = ?
        ''', (recipient_email, cc, bcc, subject, body, variables, status, scheduled_time, 
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lead_id, campaign_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Lead details updated.'})
        
    elif request.method == 'DELETE':
        cursor.execute("DELETE FROM leads WHERE id = ? AND campaign_id = ?", (lead_id, campaign_id))
        cursor.execute("DELETE FROM tracking_logs WHERE lead_id = ?", (lead_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Lead deleted.'})

@app.route('/api/campaigns/<int:campaign_id>/leads/<int:lead_id>/send', methods=['POST'])
def send_lead_instant(campaign_id, lead_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    
    # Send
    success, msg = email_service.dispatch_lead_email(lead_id, settings)
    check_and_update_campaign_completion(campaign_id)
    
    if success:
        update_send_tracker()
        return jsonify({'success': True, 'message': 'Email dispatched successfully.'})
    else:
        return jsonify({'success': False, 'message': f'Sending failed: {msg}'})

@app.route('/api/campaigns/<int:campaign_id>/leads/<int:lead_id>/schedule', methods=['POST'])
def schedule_lead_instant(campaign_id, lead_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.get_json() or {}
    sched_time = data.get('scheduled_time', '').strip() # YYYY-MM-DD HH:MM
    
    if not sched_time:
        return jsonify({'success': False, 'message': 'Schedule time is required.'}), 400
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status = 'Pending', scheduled_time = ? WHERE id = ? AND campaign_id = ?", 
                   (sched_time, lead_id, campaign_id))
    cursor.execute("UPDATE campaigns SET status = 'scheduled' WHERE id = ? AND status = 'draft'", (campaign_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': f'Email scheduled for {sched_time}.'})

# --- Excel/CSV Upload Wizard ---
@app.route('/api/campaigns/<int:campaign_id>/upload', methods=['POST'])
def upload_campaign_leads(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
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
        preview_mode = request.form.get('preview', 'false') == 'true'
        
        if preview_mode:
            headers, sample_rows = file_parser.extract_raw_data(filepath)
            if not headers:
                try: os.remove(filepath)
                except: pass
                return jsonify({
                    'success': False,
                    'message': 'Failed to parse file. Please verify it is a valid, non-empty CSV or Excel (.xlsx) file.'
                }), 400
            return jsonify({
                'success': True,
                'preview': True,
                'headers': headers,
                'sample_rows': sample_rows,
                'filepath': filepath,
                'filename': filename
            })
            
        # Full Import with custom mappings
        mapping_str = request.form.get('column_mapping', '')
        column_mapping = json.loads(mapping_str) if mapping_str else None
        
        new_leads = file_parser.parse_file(filepath, column_mapping)
        if not new_leads:
            return jsonify({'success': False, 'message': 'No leads could be imported from the file.'}), 400
            
        # Get existing suppression list to skip unsubscribed emails
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email FROM suppression_list")
            suppressed_emails = set(row['email'].lower() for row in cursor.fetchall())
            
            # Check duplicate emails already in this campaign
            cursor.execute("SELECT recipient_email FROM leads WHERE campaign_id = ?", (campaign_id,))
            existing_campaign_emails = set(row['recipient_email'].lower() for row in cursor.fetchall())
            
            imported = 0
            duplicates = 0
            suppressed = 0
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for l in new_leads:
                email_lower = l['recipient_email'].lower().strip()
                
                if email_lower in suppressed_emails:
                    suppressed += 1
                elif email_lower in existing_campaign_emails:
                    duplicates += 1
                else:
                    cursor.execute('''
                        INSERT INTO leads (
                            campaign_id, recipient_email, cc, bcc, subject, body, attachments, variables, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
                    ''', (
                        campaign_id, l['recipient_email'], l['cc'], l['bcc'], l['subject'], 
                        l['body'], l['attachments'], l['variables'], now, now
                    ))
                    existing_campaign_emails.add(email_lower)
                    imported += 1
                    
            conn.commit()
        finally:
            conn.close()
            
        # Clean up file
        try:
            os.remove(filepath)
        except:
            pass
            
        return jsonify({
            'success': True,
            'message': f"Successfully imported {imported} leads. Skipped {duplicates} duplicates & {suppressed} unsubscribed.",
            'imported': imported,
            'duplicates': duplicates,
            'suppressed': suppressed
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error importing file: {str(e)}'}), 500

# --- Email Open Tracking Pixel ---
@app.route('/api/track/open/<int:lead_id>', methods=['GET'])
def track_open(lead_id):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT campaign_id, recipient_email FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()
    
    if lead:
        campaign_id = lead['campaign_id']
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Get real client IP address from proxy headers if available
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        ua = request.user_agent.string
        
        # Increment count
        cursor.execute("UPDATE leads SET open_count = open_count + 1, last_opened = ? WHERE id = ?", (now, lead_id))
        
        # Log activity
        cursor.execute('''
            INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details, ip_address, user_agent)
            VALUES (?, ?, 'opened', ?, ?, ?, ?)
        ''', (lead_id, campaign_id, now, f"Email opened by {lead['recipient_email']}", ip, ua))
        
        conn.commit()
        
    conn.close()
    
    # Serve 1x1 pixel image
    pixel_data = base64_pixel = (
        b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
        b'\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
        b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
    )
    response = make_response(pixel_data)
    response.headers['Content-Type'] = 'image/gif'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

# --- Email Link Click Tracking ---
@app.route('/api/track/click/<int:lead_id>', methods=['GET'])
def track_click(lead_id):
    destination_url = request.args.get('url', '').strip()
    if not destination_url:
        return "Missing URL parameters", 400
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT campaign_id, recipient_email FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()
    
    if lead:
        campaign_id = lead['campaign_id']
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Get real client IP address from proxy headers if available
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
        ua = request.user_agent.string
        
        # Increment click count
        cursor.execute("UPDATE leads SET click_count = click_count + 1, last_clicked = ? WHERE id = ?", (now, lead_id))
        
        # Log activity
        cursor.execute('''
            INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details, ip_address, user_agent)
            VALUES (?, ?, 'clicked', ?, ?, ?, ?)
        ''', (lead_id, campaign_id, now, f"Clicked link: {destination_url}", ip, ua))
        
        conn.commit()
        
    conn.close()
    
    # Redirect to final destination URL
    return make_response(render_template_string(
        f"<html><head><meta http-equiv='refresh' content='0;url={destination_url}'></head><body>Redirecting...</body></html>"
    ))

# --- Unsubscribe ---
@app.route('/unsubscribe/<int:lead_id>', methods=['GET'])
def unsubscribe_recipient(lead_id):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT campaign_id, recipient_email FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()
    
    if lead:
        recipient = lead['recipient_email']
        campaign_id = lead['campaign_id']
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Mark as unsubscribed in leads
        cursor.execute("UPDATE leads SET unsubscribed = 1 WHERE recipient_email = ?", (recipient,))
        
        # Add to global suppression list
        cursor.execute("INSERT OR IGNORE INTO suppression_list (email, reason, unsubscribed_at, campaign_id) VALUES (?, 'Unsubscribed via email link', ?, ?)",
                       (recipient.lower().strip(), now, campaign_id))
                       
        # Log tracking activity
        cursor.execute('''
            INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details)
            VALUES (?, ?, 'unsubscribed', ?, 'Recipient opted out of campaigns')
        ''', (lead_id, campaign_id, now))
        
        conn.commit()
        
    conn.close()
    
    # Render neat landing page
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Unsubscribed Successfully</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', sans-serif; text-align: center; padding: 60px 20px; background-color: #F9FAFB; color: #1F2937; }
            .card { max-width: 440px; margin: 0 auto; background: white; padding: 40px; border-radius: 24px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.02); border: 1px solid #E5E7EB; }
            h1 { font-size: 22px; font-weight: 600; color: #111827; margin-top: 16px; margin-bottom: 8px; }
            p { font-size: 14px; color: #6B7280; line-height: 1.5; margin-bottom: 0; }
            .success-icon { display: inline-flex; align-items: center; justify-content: center; width: 56px; height: 56px; background-color: #ECFDF5; color: #10B981; border-radius: 50%; font-size: 28px; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="success-icon">&#10004;</div>
            <h1>Successfully Unsubscribed</h1>
            <p>You have been removed from our list. You will no longer receive automated email campaigns from this system.</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

# --- Suppression List Management ---
@app.route('/api/suppression-list', methods=['GET', 'POST'])
def manage_suppression_list():
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM suppression_list ORDER BY id DESC")
        suppressions = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(suppressions)
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        reason = data.get('reason', 'Manual Suppression').strip()
        
        if not email or "@" not in email:
            conn.close()
            return jsonify({'success': False, 'message': 'Please provide a valid email address.'}), 400
            
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR IGNORE INTO suppression_list (email, reason, unsubscribed_at) VALUES (?, ?, ?)",
                       (email, reason, now))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'{email} added to suppression list.'})

@app.route('/api/suppression-list/<int:sup_id>', methods=['DELETE'])
def delete_suppression(sup_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM suppression_list WHERE id = ?", (sup_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Email removed from suppression list.'})

# --- Campaign Reports and Exports ---
@app.route('/api/campaigns/<int:campaign_id>/export', methods=['GET'])
def export_campaign_report(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return "Unauthorized", 401
        
    fmt = request.args.get('format', 'csv').lower()
    
    # Ownership Check
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM campaigns WHERE id = ? AND created_by = ?", (campaign_id, user_id))
    camp = cursor.fetchone()
    conn.close()
    
    if not camp:
        return "Campaign not found", 404
        
    filename_base = camp['name'].replace(' ', '_').lower()
    
    if fmt == 'csv':
        csv_data = export_service.generate_csv(campaign_id)
        response = make_response(csv_data)
        response.headers['Content-Disposition'] = f'attachment; filename=report_{filename_base}.csv'
        response.headers['Content-Type'] = 'text/csv'
        return response
        
    elif fmt == 'excel':
        excel_data = export_service.generate_excel(campaign_id)
        response = make_response(excel_data)
        response.headers['Content-Disposition'] = f'attachment; filename=report_{filename_base}.xlsx'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
        
    elif fmt == 'pdf':
        pdf_data = export_service.generate_pdf(campaign_id)
        response = make_response(pdf_data)
        response.headers['Content-Disposition'] = f'attachment; filename=report_{filename_base}.pdf'
        response.headers['Content-Type'] = 'application/pdf'
        return response
        
    return "Unsupported format type.", 400

@app.route('/api/campaigns/<int:campaign_id>/stats', methods=['GET'])
def get_campaign_stats(campaign_id):
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = export_service.get_campaign_data(campaign_id)
    if not data:
        return jsonify({'success': False, 'message': 'Campaign not found.'}), 404
        
    # Get tracking logs for live updates
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tracking_logs WHERE campaign_id = ? ORDER BY id DESC LIMIT 50", (campaign_id,))
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    data['recent_logs'] = logs
    return jsonify(data)

# --- Global Dashboard Stats ---
@app.route('/api/dashboard/summary', methods=['GET'])
def get_dashboard_summary():
    user_id = get_logged_in_user()
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Counts
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE created_by = ?", (user_id,))
    total_campaigns = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE created_by = ? AND status = 'running'", (user_id,))
    active_campaigns = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE created_by = ? AND status = 'scheduled'", (user_id,))
    scheduled_campaigns = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE created_by = ? AND status = 'completed'", (user_id,))
    completed_campaigns = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE created_by = ? AND status = 'failed'", (user_id,))
    failed_campaigns = cursor.fetchone()[0]
    
    # Global Leads Metrics for this user
    cursor.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='Sent' THEN 1 ELSE 0 END) as sent,
               SUM(CASE WHEN status='Failed' THEN 1 ELSE 0 END) as failed,
               SUM(CASE WHEN status='Pending' OR status='Processing' THEN 1 ELSE 0 END) as pending,
               SUM(CASE WHEN status='Scheduled' THEN 1 ELSE 0 END) as scheduled,
               SUM(CASE WHEN open_count > 0 THEN 1 ELSE 0 END) as opens,
               SUM(CASE WHEN click_count > 0 THEN 1 ELSE 0 END) as clicks,
               SUM(CASE WHEN bounce_status != 'none' THEN 1 ELSE 0 END) as bounces,
               SUM(CASE WHEN unsubscribed > 0 THEN 1 ELSE 0 END) as unsubscribes
        FROM leads WHERE campaign_id IN (SELECT id FROM campaigns WHERE created_by = ?)
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    metrics = dict(row) if row['total'] > 0 else {
        'total': 0, 'sent': 0, 'failed': 0, 'pending': 0, 'scheduled': 0,
        'opens': 0, 'clicks': 0, 'bounces': 0, 'unsubscribes': 0
    }
    
    # Safe percentages
    sent_cnt = metrics.get('sent') or 0
    total_cnt = metrics.get('total') or 0
    
    metrics['success_rate'] = round((sent_cnt / total_cnt * 100), 1) if total_cnt > 0 else 0
    metrics['open_rate'] = round(((metrics.get('opens') or 0) / sent_cnt * 100), 1) if sent_cnt > 0 else 0
    metrics['click_rate'] = round(((metrics.get('clicks') or 0) / sent_cnt * 100), 1) if sent_cnt > 0 else 0
    metrics['bounce_rate'] = round(((metrics.get('bounces') or 0) / total_cnt * 100), 1) if total_cnt > 0 else 0
    
    return jsonify({
        'campaigns': {
            'total': total_campaigns,
            'active': active_campaigns,
            'scheduled': scheduled_campaigns,
            'completed': completed_campaigns,
            'failed': failed_campaigns
        },
        'leads_metrics': metrics
    })

# --- Rate Limit API status ---
@app.route('/api/rate-limit-status', methods=['GET'])
def get_rate_limit_status():
    global email_send_tracker
    
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    conn.close()
    
    daily_limit = int(settings.get('daily_email_limit', 500))
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
