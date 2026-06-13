import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime
import database
import re
import random
import time

def send_email_actual(to_email, subject, body, settings):
    provider = settings.get('mail_provider', 'gmail').strip().lower()
    
    # Anti-spam headers for better deliverability
    msg = MIMEMultipart('alternative')
    msg['X-Mailer'] = 'Bhatt Technologies Outreach System'
    msg['X-Priority'] = '3'
    msg['Importance'] = 'Normal'
    
    # Auto-configure based on provider
    if provider == 'titan':
        default_host = 'smtp.titan.email'
        default_port = '587'
    elif provider == 'gmail':
        default_host = 'smtp.gmail.com'
        default_port = '587'
    else:
        default_host = 'smtp.gmail.com'
        default_port = '587'
    
    host = settings.get('smtp_host', default_host).strip()
    port = int(settings.get('smtp_port', default_port).strip())
    user = settings.get('google_email', '').strip()
    password = settings.get('google_app_password', '').strip()
    sender_name = settings.get('sender_name', 'Dhruv Patel - DhruvBuilds').strip()
    
    if not user or not password:
        raise ValueError("Email and password/app password are not configured in Settings.")
    
    # Professional email formatting
    msg['From'] = f"{sender_name} <{user}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Reply-To'] = user
    msg['Date'] = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    
    # Create HTML version of body
    html_body = body.replace('\n', '<br>')
    # Make urls clickable in HTML
    html_body = re.sub(r'(https?://[^\s<]+)', r'<a href="\1" style="color: #2563EB; text-decoration: underline;">\1</a>', html_body)
    
    part1 = MIMEText(body, 'plain')
    part2 = MIMEText(f"<div style='font-family: Arial, sans-serif; font-size: 14px; color: #1F2937; line-height: 1.6;'>{html_body}</div>", 'html')
    
    msg.attach(part1)
    msg.attach(part2)
    
    try:
        # Enhanced connection logic with better error handling
        server = None
        
        if port == 465:
            import ssl
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
            server.set_debuglevel(0)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.set_debuglevel(0)
            server.ehlo()
            
            # Start TLS with explicit context
            import ssl
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
        
        # Attempt login
        server.login(user, password)
        
        # Send email
        server.sendmail(user, to_email, msg.as_string())
        server.quit()
        
        return True, f"Email sent successfully via {provider.upper()} SMTP."
        
    except smtplib.SMTPAuthenticationError as e:
        if server:
            try:
                server.quit()
            except:
                pass
        raise ValueError(
            f"SMTP authentication failed for {user} on {host}:{port}. "
            "Please verify mailbox password/app password and SMTP login permissions. "
            f"Error: {str(e)}"
        )
    except smtplib.SMTPServerDisconnected as e:
        if server:
            try:
                server.quit()
            except:
                pass
        raise ValueError(
            f"SMTP server disconnected unexpectedly. "
            f"For Titan Mail: Please enable 'External Email Clients' in your Titan webmail settings. "
            f"For Gmail: Use a 16-character App Password, not your regular password. "
            f"Error: {str(e)}"
        )
    except Exception as e:
        if server:
            try:
                server.quit()
            except:
                pass
        raise RuntimeError(f"SMTP Error: {str(e)}")

def send_test_email(settings):
    user = settings.get('google_email', '').strip()
    provider = settings.get('mail_provider', 'custom').strip().lower()
    provider_name = {'gmail': 'Gmail', 'titan': 'Titan', 'custom': 'SMTP'}.get(provider, 'SMTP')
    if not user:
        raise ValueError("Please enter your sender email first.")
        
    subject = f"Success! {provider_name} SMTP Verified for Bhatt Technologies Outreach"
    body = (
        f"Hi there!\n\nYour {provider_name} SMTP credentials were authenticated successfully.\n\n"
        "You can now send and schedule outreach emails from your dashboard.\n\n"
        "Best regards,\nBhatt Technologies Automated Outreach Hub"
    )
    
    return send_email_actual(user, subject, body, settings)

def dispatch_lead_email(lead_id, settings, simulated=False):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
    lead = cursor.fetchone()
    
    if not lead:
        conn.close()
        return False, "Lead not found."
        
    recipient = lead['contact_email']
    subject = lead['subject']
    body = lead['pitch']
    
    mode = settings.get('email_mode', 'simulated')
    if simulated or mode == 'simulated':
        # Simulate send
        success = True
        msg = "Simulated Success (Test Mode)"
    else:
        try:
            success, msg = send_email_actual(recipient, subject, body, settings)
        except Exception as e:
            success = False
            msg = str(e)
            
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if success:
        cursor.execute("UPDATE leads SET status = 'Sent', sent_time = ?, error_message = '' WHERE id = ?", (now, lead_id))
    else:
        cursor.execute("UPDATE leads SET status = 'Failed', error_message = ? WHERE id = ?", (msg, lead_id))
        
    cursor.execute('''
        INSERT INTO logs (lead_id, recipient_email, subject, status, timestamp, message)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (lead_id, recipient, subject, 'Success' if success else 'Error', now, msg))
    
    conn.commit()
    conn.close()
    return success, msg
