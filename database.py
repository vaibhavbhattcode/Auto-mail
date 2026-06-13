import sqlite3
import json
import datetime
import os
import hashlib
import base64
from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.environ.get('DATABASE_PATH', 'campaigns.db')
ENCRYPTION_KEY = os.environ.get('SECRET_KEY', 'arena_agent_secure_secret_key_2026_dhruvbuilds')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_fernet_cipher():
    key = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
    key_b64 = base64.urlsafe_b64encode(key)
    return Fernet(key_b64)

def encrypt_password(password):
    if not password:
        return ""
    cipher = get_fernet_cipher()
    return cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    if not encrypted_password:
        return ""
    cipher = get_fernet_cipher()
    try:
        return cipher.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        print(f"[Decrypt Error] Failed to decrypt password: {str(e)}")
        return ""

def hash_password(password):
    """Hash password using Werkzeug security (PBKDF2/scrypt)"""
    return generate_password_hash(password)

def verify_password(password, hashed):
    """Verify password against hash"""
    return check_password_hash(hashed, password)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TEXT,
        last_login TEXT
    )
    ''')
    
    # 2. SMTP Accounts table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS smtp_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        email_address TEXT NOT NULL,
        sender_name TEXT,
        smtp_host TEXT NOT NULL,
        smtp_port INTEGER NOT NULL,
        ssl_tls TEXT NOT NULL,
        password_encrypted TEXT NOT NULL,
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')
    
    # 3. Campaigns table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'draft',
        smtp_account_id INTEGER,
        created_by INTEGER NOT NULL,
        created_at TEXT,
        updated_at TEXT,
        start_time TEXT,
        sending_interval INTEGER DEFAULT 0, -- in minutes, 0 means individual/no interval
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (smtp_account_id) REFERENCES smtp_accounts(id) ON DELETE SET NULL
    )
    ''')
    
    # 4. Leads table (updated to link with Campaign)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        recipient_email TEXT NOT NULL,
        cc TEXT,
        bcc TEXT,
        subject TEXT,
        body TEXT,
        attachments TEXT, -- JSON string of file names
        variables TEXT, -- JSON string of all row values for custom placeholders
        status TEXT DEFAULT 'Pending',
        scheduled_time TEXT,
        sent_time TEXT,
        error_message TEXT,
        open_count INTEGER DEFAULT 0,
        last_opened TEXT,
        click_count INTEGER DEFAULT 0,
        last_clicked TEXT,
        bounce_status TEXT DEFAULT 'none', -- 'none', 'hard', 'soft'
        bounce_reason TEXT,
        unsubscribed INTEGER DEFAULT 0,
        retry_count INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
    )
    ''')
    
    # 5. Suppression list table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suppression_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        reason TEXT,
        unsubscribed_at TEXT,
        campaign_id INTEGER,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL
    )
    ''')
    
    # 6. Tracking logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracking_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        campaign_id INTEGER NOT NULL,
        activity_type TEXT NOT NULL, -- 'sent', 'opened', 'clicked', 'bounced', 'unsubscribed'
        timestamp TEXT NOT NULL,
        details TEXT,
        ip_address TEXT,
        user_agent TEXT,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
    )
    ''')
    
    # 7. Settings table (keeps global limits/configs)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # --- SCHEMA MIGRATIONS (Upgrade existing databases dynamically) ---
    # Check leads columns
    cursor.execute("PRAGMA table_info(leads)")
    leads_columns = [row['name'] for row in cursor.fetchall()]
    
    # Rename contact_email to recipient_email if old schema exists
    if 'contact_email' in leads_columns and 'recipient_email' not in leads_columns:
        print("[Migration] Renaming 'contact_email' to 'recipient_email' in 'leads' table...")
        cursor.execute("ALTER TABLE leads RENAME COLUMN contact_email TO recipient_email")
        cursor.execute("PRAGMA table_info(leads)")
        leads_columns = [row['name'] for row in cursor.fetchall()]
        
    # Rename pitch to body if old schema exists
    if 'pitch' in leads_columns and 'body' not in leads_columns:
        print("[Migration] Renaming 'pitch' to 'body' in 'leads' table...")
        cursor.execute("ALTER TABLE leads RENAME COLUMN pitch TO body")
        cursor.execute("PRAGMA table_info(leads)")
        leads_columns = [row['name'] for row in cursor.fetchall()]
    
    leads_upgrades = {
        'campaign_id': 'INTEGER',
        'cc': 'TEXT',
        'bcc': 'TEXT',
        'attachments': 'TEXT',
        'variables': 'TEXT',
        'open_count': 'INTEGER DEFAULT 0',
        'last_opened': 'TEXT',
        'click_count': 'INTEGER DEFAULT 0',
        'last_clicked': 'TEXT',
        'bounce_status': "TEXT DEFAULT 'none'",
        'bounce_reason': 'TEXT',
        'unsubscribed': 'INTEGER DEFAULT 0',
        'retry_count': 'INTEGER DEFAULT 0',
        'updated_at': 'TEXT'
    }
    
    for col, definition in leads_upgrades.items():
        if col not in leads_columns:
            print(f"[Migration] Adding missing column '{col}' to table 'leads'...")
            cursor.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")
            
    # Check users columns
    cursor.execute("PRAGMA table_info(users)")
    users_columns = [row['name'] for row in cursor.fetchall()]
    if 'username' not in users_columns:
        print("[Migration] Adding missing column 'username' to table 'users'...")
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT UNIQUE")
    if 'email' not in users_columns:
        print("[Migration] Adding missing column 'email' to table 'users'...")
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
        
    # Default global settings
    default_settings = {
        'daily_email_limit': '500',
        'max_emails_per_hour': '50',
        'min_cooldown_seconds': '10',
        'max_cooldown_seconds': '30',
        'emails_per_batch': '5',
        'batch_cooldown_minutes': '5',
        'randomize_cooldown': 'true',
        'tracking_domain': 'http://localhost:5000',
        'company_name': 'Bhatt Technologies',
        'support_email': 'support@bhatttechnologies.com',
        'timezone': 'Asia/Kolkata'
    }
    
    for k, v in default_settings.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully with the upgraded multi-user campaign schema.")
