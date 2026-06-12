import sqlite3
import json
import datetime
import os

DB_PATH = 'campaigns.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # Default settings
    default_settings = {
        'admin_password': 'password123',
        'google_email': '',
        'google_app_password': '',
        'sender_name': 'Vaibhav Bhatt - Bhatt Technologies',
        'smtp_host': 'smtp.gmail.com',
        'smtp_port': '587',
        'max_emails_per_hour': '30',
        'auto_send_enabled': 'true',
        'mail_provider': 'gmail'
    }
    
    for k, v in default_settings.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))
        
    # Leads table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT,
        website TEXT,
        industry TEXT,
        location TEXT,
        app_status TEXT,
        contact_email TEXT,
        whatsapp_number TEXT,
        linkedin TEXT,
        subject TEXT,
        pitch TEXT,
        status TEXT,
        scheduled_time TEXT,
        sent_time TEXT,
        error_message TEXT,
        created_at TEXT
    )
    ''')
    
    # Templates table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        subject TEXT,
        body TEXT,
        is_default INTEGER
    )
    ''')
    
    # Seed templates if empty
    cursor.execute('SELECT COUNT(*) FROM templates')
    if cursor.fetchone()[0] == 0:
        templates = [
            (
                "Modernizing Mobile App Experience",
                "Your {{company_name}} app — quick thought",
                "Hi Team at {{company_name}},\n\nI came across {{company_name}} and your platform at {{website}}. I noticed your current mobile setup is {{app_status}} — which seems like an untapped opportunity for your business in the {{industry}} space.\n\nIn your highly competitive industry, a modern, frictionless mobile app is exactly what keeps customers engaged, streamlines reorders/bookings, and drives retention.\n\nI run Bhatt Technologies (bhatttechnologies.com), a specialized app development agency. We rebuild and modernize apps for businesses like yours — giving them exceptional UX, blazingly fast performance, and clean, high-conversion flows.\n\nIf improving your app or building a custom solution is on your roadmap this year, I'd love to share a few quick tailored ideas.\n\nHappy to connect over a short call or chat. Feel free to reply here or drop me a message on WhatsApp at {{whatsapp_number}}.\n\nBest regards,\nVaibhav Bhatt\nFounder, Bhatt Technologies",
                1
            ),
            (
                "Transforming Web Strategy to Native App",
                "Mobile App for {{company_name}}?",
                "Hi Team,\n\nI was looking at {{company_name}} and you have built an impressive presence in {{location}}, but from what I can see, everything is currently running through your website ({{website}}).\n\nFor a leader in {{industry}}, relying solely on a web browser on mobile adds friction for repeat customers. A dedicated native app simplifies daily interactions, push notifications, custom workflows, and loyalty—things that dramatically cut down drop-offs and improve Customer Lifetime Value.\n\nI'm Vaibhav Bhatt, founder of Bhatt Technologies (bhatttechnologies.com). We build lightning-fast, lightweight native apps for brands that want to build a direct, premium relationship with their audience.\n\nWould it make sense to have a quick 5-minute chat about what an app could look like for {{company_name}}?\n\nFeel free to reply to this email or reach out to me directly on WhatsApp at {{whatsapp_number}}.\n\nCheers,\nVaibhav Bhatt\nBhatt Technologies | bhatttechnologies.com",
                0
            )
        ]
        cursor.executemany('INSERT INTO templates (name, subject, body, is_default) VALUES (?, ?, ?, ?)', templates)

    # Logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        recipient_email TEXT,
        subject TEXT,
        status TEXT,
        timestamp TEXT,
        message TEXT
    )
    ''')
    
    # Seed leads from initial_leads.json if empty
    cursor.execute('SELECT COUNT(*) FROM leads')
    if cursor.fetchone()[0] == 0:
        if os.path.exists('initial_leads.json'):
            with open('initial_leads.json', 'r') as f:
                initial_leads = json.load(f)
            
            for lead in initial_leads:
                cursor.execute('''
                INSERT INTO leads (
                    company_name, website, industry, location, app_status,
                    contact_email, whatsapp_number, linkedin, subject, pitch,
                    status, scheduled_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lead.get('company_name', 'Unknown'),
                    lead.get('website', 'example.com'),
                    lead.get('industry', 'Technology'),
                    lead.get('location', 'India'),
                    lead.get('app_status', 'Review Needed'),
                    lead.get('contact_email', 'contact@example.com'),
                    lead.get('whatsapp_number', '+91 9510539603'),
                    lead.get('linkedin', ''),
                    lead.get('subject', 'App Dev Pitch'),
                    lead.get('pitch', ''),
                    'Pending',
                    None,
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
