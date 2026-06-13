import sqlite3
import json
import datetime
import os
import bcrypt

DB_PATH = os.environ.get('DATABASE_PATH', 'campaigns.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table for authentication
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT,
        role TEXT DEFAULT 'admin',
        created_at TEXT,
        last_login TEXT
    )
    ''')
    
    # Settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        category TEXT DEFAULT 'general',
        description TEXT
    )
    ''')
    
    # Check if admin exists, if not create default
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        # Create default admin (will be changed on first login)
        default_pass = hash_password('admin@2024')
        cursor.execute('''
            INSERT INTO users (username, password_hash, email, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', default_pass, 'admin@bhatttechnologies.com', 'admin', 
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    # Default settings with categories
    default_settings = {
        # Email Settings
        'smtp_provider': ('gmail', 'email', 'Email service provider'),
        'smtp_host': ('smtp.gmail.com', 'email', 'SMTP server host'),
        'smtp_port': ('587', 'email', 'SMTP server port'),
        'smtp_email': ('', 'email', 'Sender email address'),
        'smtp_password': ('', 'email', 'Email password or app password'),
        'sender_name': ('Bhatt Technologies', 'email', 'Display name for sent emails'),
        'email_mode': ('live', 'email', 'Email mode: live or simulated'),
        
        # Application Settings
        'company_name': ('Bhatt Technologies', 'general', 'Company name'),
        'company_website': ('bhatttechnologies.com', 'general', 'Company website'),
        'support_email': ('support@bhatttechnologies.com', 'general', 'Support email'),
        'timezone': ('Asia/Kolkata', 'general', 'Application timezone'),
        
        # Advanced Settings
        'max_emails_per_hour': ('50', 'advanced', 'Rate limit for emails'),
        'session_timeout': ('3600', 'advanced', 'Session timeout in seconds'),
        'enable_analytics': ('true', 'advanced', 'Enable analytics tracking'),
    }
    
    for key, (value, category, description) in default_settings.items():
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value, category, description)
            VALUES (?, ?, ?, ?)
        ''', (key, value, category, description))
    
    # Leads table with enhanced fields
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        website TEXT,
        industry TEXT,
        location TEXT,
        app_status TEXT,
        contact_email TEXT NOT NULL,
        whatsapp_number TEXT,
        linkedin TEXT,
        subject TEXT,
        pitch TEXT,
        status TEXT DEFAULT 'Pending',
        scheduled_time TEXT,
        sent_time TEXT,
        opened_time TEXT,
        clicked_time TEXT,
        replied_time TEXT,
        error_message TEXT,
        tags TEXT,
        priority TEXT DEFAULT 'medium',
        source TEXT DEFAULT 'manual',
        created_at TEXT,
        updated_at TEXT,
        created_by INTEGER,
        FOREIGN KEY (created_by) REFERENCES users(id)
    )
    ''')
    
    # Templates table with enhanced fields
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        category TEXT DEFAULT 'general',
        is_default INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        usage_count INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        created_by INTEGER,
        FOREIGN KEY (created_by) REFERENCES users(id)
    )
    ''')
    
    # Seed default templates if empty
    cursor.execute('SELECT COUNT(*) FROM templates')
    if cursor.fetchone()[0] == 0:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        templates = [
            (
                "Modern App Development Pitch",
                "Your {{company_name}} mobile experience",
                "Hi Team at {{company_name}},\\n\\nI noticed your current mobile setup is {{app_status}}. As a specialized app development agency, we help businesses like yours build modern, high-performance mobile applications.\\n\\nWe'd love to discuss how a custom mobile app could enhance your {{industry}} business.\\n\\nBest regards,\\nVaibhav Bhatt\\nBhatt Technologies",
                "sales",
                1,
                1,
                0,
                now,
                now,
                1
            ),
            (
                "Quick Follow-up",
                "Following up - {{company_name}}",
                "Hi,\\n\\nJust following up on my previous message about modernizing your mobile presence at {{company_name}}.\\n\\nWould you have 15 minutes for a quick call this week?\\n\\nBest,\\nVaibhav Bhatt",
                "followup",
                0,
                1,
                0,
                now,
                now,
                1
            )
        ]
        cursor.executemany('''
            INSERT INTO templates (name, subject, body, category, is_default, is_active, usage_count, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', templates)
    
    # Logs table with enhanced tracking
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        recipient_email TEXT,
        subject TEXT,
        status TEXT,
        timestamp TEXT,
        message TEXT,
        ip_address TEXT,
        user_agent TEXT,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    )
    ''')
    
    # Column mappings table for dynamic imports
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS column_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mapping_name TEXT NOT NULL,
        file_column TEXT NOT NULL,
        system_field TEXT NOT NULL,
        is_default INTEGER DEFAULT 0,
        created_at TEXT
    )
    ''')
    
    # Campaigns table for grouping leads
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'draft',
        start_date TEXT,
        end_date TEXT,
        total_leads INTEGER DEFAULT 0,
        sent_count INTEGER DEFAULT 0,
        opened_count INTEGER DEFAULT 0,
        clicked_count INTEGER DEFAULT 0,
        replied_count INTEGER DEFAULT 0,
        created_at TEXT,
        created_by INTEGER,
        FOREIGN KEY (created_by) REFERENCES users(id)
    )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("✅ Enhanced database initialized successfully!")
    print("📧 Default admin credentials:")
    print("   Username: admin")
    print("   Password: admin@2024")
    print("⚠️  Change password immediately after first login!")
