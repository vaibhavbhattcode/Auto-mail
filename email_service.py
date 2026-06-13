import smtplib
import os
import json
import re
import datetime
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import database

def render_template(text, variables):
    """Render text replacing {{placeholder}} and [[placeholder]] with values"""
    if not text:
        return ""
    
    norm_vars = {}
    for k, v in variables.items():
        norm_vars[k.lower().strip()] = v
        norm_vars[k] = v
        
    # Support {{placeholder}}
    placeholders = re.findall(r'\{\{([^}]+)\}\}', text)
    for p in placeholders:
        p_clean = p.strip()
        p_lower = p_clean.lower()
        val = ""
        if p_clean in norm_vars:
            val = norm_vars[p_clean]
        elif p_lower in norm_vars:
            val = norm_vars[p_lower]
        text = text.replace(f"{{{{{p}}}}}", str(val))
        
    # Support [[placeholder]]
    placeholders_alt = re.findall(r'\[\[([^\]]+)\]\]', text)
    for p in placeholders_alt:
        p_clean = p.strip()
        p_lower = p_clean.lower()
        val = ""
        if p_clean in norm_vars:
            val = norm_vars[p_clean]
        elif p_lower in norm_vars:
            val = norm_vars[p_lower]
        text = text.replace(f"[[{p}]]", str(val))
        
    return text

def rewrite_links_for_tracking(html_body, lead_id, tracking_domain):
    """Replace normal anchor links with redirect tracking links"""
    def replace_link(match):
        quote_char = match.group(1)
        url = match.group(2)
        # Skip unsubscribe or existing tracker urls
        if "/unsubscribe/" in url or "/api/track/" in url:
            return match.group(0)
        encoded_url = urllib.parse.quote(url)
        return f'href={quote_char}{tracking_domain}/api/track/click/{lead_id}?url={encoded_url}{quote_char}'
    
    pattern = r'href=(["\'])(https?://.*?)\1'
    return re.sub(pattern, replace_link, html_body)

def send_email_actual(to_email, cc, bcc, subject, body, html_body, attachments, smtp_settings, campaign_id=None):
    """Core SMTP sending function with support for CC, BCC, and Attachments"""
    host = smtp_settings.get('smtp_host', '').strip()
    port = int(smtp_settings.get('smtp_port', 587))
    user = smtp_settings.get('email_address', '').strip()
    password = smtp_settings.get('password', '').strip()
    sender_name = smtp_settings.get('sender_name', '').strip()
    ssl_tls = smtp_settings.get('ssl_tls', 'tls').strip().lower()
    
    if not user or not password:
        raise ValueError("SMTP Credentials are not configured.")
        
    msg = MIMEMultipart('mixed')
    msg['X-Mailer'] = 'Antigravity Outreach Hub'
    msg['X-Priority'] = '3'
    msg['Importance'] = 'Normal'
    
    msg['From'] = f"{sender_name} <{user}>" if sender_name else user
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Reply-To'] = user
    msg['Date'] = datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    
    # Process CC / BCC recipients
    all_recipients = [to_email]
    if cc:
        cc_emails = [email.strip() for email in cc.split(',') if email.strip()]
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
            all_recipients.extend(cc_emails)
    if bcc:
        bcc_emails = [email.strip() for email in bcc.split(',') if email.strip()]
        if bcc_emails:
            all_recipients.extend(bcc_emails)
            
    # Attach body contents
    msg_body = MIMEMultipart('alternative')
    part1 = MIMEText(body, 'plain', 'utf-8')
    part2 = MIMEText(html_body, 'html', 'utf-8')
    msg_body.attach(part1)
    msg_body.attach(part2)
    msg.attach(msg_body)
    
    # Attachments
    if attachments:
        try:
            attachment_list = json.loads(attachments) if isinstance(attachments, str) else attachments
            for filename in attachment_list:
                # Resolve file path
                paths_to_check = [
                    os.path.join("uploads", filename),
                    os.path.join("uploads", f"campaign_{campaign_id}", filename) if campaign_id else None
                ]
                
                filepath = None
                for path in paths_to_check:
                    if path and os.path.exists(path):
                        filepath = path
                        break
                        
                if filepath:
                    with open(filepath, 'rb') as f:
                        part = MIMEApplication(f.read(), Name=filename)
                        part['Content-Disposition'] = f'attachment; filename="{filename}"'
                        msg.attach(part)
        except Exception as e:
            print(f"[Attachment Error] Failed to attach files: {str(e)}")
            
    server = None
    try:
        if ssl_tls == 'ssl' or port == 465:
            import ssl
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            if ssl_tls == 'tls' or port == 587:
                import ssl
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                
        server.login(user, password)
        server.sendmail(user, all_recipients, msg.as_string())
        server.quit()
        return True, "Email sent successfully."
        
    except smtplib.SMTPRecipientsRefused as e:
        # Hard bounce - address rejected by server
        raise ValueError(f"Recipient Refused (Bounce): {str(e)}")
    except smtplib.SMTPAuthenticationError as e:
        raise ValueError(f"SMTP authentication failed: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"SMTP Error: {str(e)}")
    finally:
        if server:
            try:
                server.quit()
            except:
                pass

def send_test_email(smtp_settings):
    """Send a basic SMTP test email"""
    user = smtp_settings.get('email_address', '').strip()
    if not user:
        raise ValueError("Please provide a sender email address.")
    
    subject = "Verification Check: SMTP Working Properly"
    body = "Hello!\n\nThis email verifies that your SMTP settings are active and correct.\n\nBest regards,\nOutreach Team"
    html_body = "<p>Hello!</p><p>This email verifies that your SMTP settings are active and correct.</p>"
    
    return send_email_actual(user, None, None, subject, body, html_body, None, smtp_settings)

def dispatch_lead_email(lead_id, global_settings=None, simulated=False):
    """Loads a lead, renders template, tracks delivery, and executes SMTP send"""
    conn = database.get_db()
    try:
        cursor = conn.cursor()
        
        # 1. Fetch Lead
        cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
        lead = cursor.fetchone()
        if not lead:
            return False, "Lead not found."
            
        lead = dict(lead)
        recipient = lead['recipient_email']
        campaign_id = lead['campaign_id']
        
        # 2. Fetch Campaign & User ID
        cursor.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))
        campaign = cursor.fetchone()
        if not campaign:
            return False, "Campaign not found."
        campaign = dict(campaign)
        
        # 3. Check Suppression List
        cursor.execute('SELECT id FROM suppression_list WHERE email = ?', (recipient.lower().strip(),))
        if cursor.fetchone():
            cursor.execute("UPDATE leads SET status = 'Failed', error_message = 'Suppressed: Recipient unsubscribed' WHERE id = ?", (lead_id,))
            cursor.execute('''
                INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details)
                VALUES (?, ?, 'bounced', ?, 'Suppressed: Recipient unsubscribed')
            ''', (lead_id, campaign_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            return False, "Recipient is unsubscribed (suppressed)."
            
        # 4. Fetch SMTP Account
        smtp_account_id = campaign.get('smtp_account_id')
        if not smtp_account_id:
            return False, "No SMTP account configured for this campaign."
            
        cursor.execute('SELECT * FROM smtp_accounts WHERE id = ?', (smtp_account_id,))
        smtp_row = cursor.fetchone()
        if not smtp_row:
            return False, "Configured SMTP account not found."
        smtp_row = dict(smtp_row)
        
        # Decrypt SMTP Password
        smtp_row['password'] = database.decrypt_password(smtp_row['password_encrypted'])
        
        # Get global settings if not passed
        if not global_settings:
            cursor.execute('SELECT key, value FROM settings')
            global_settings = {row['key']: row['value'] for row in cursor.fetchall()}
            
        tracking_domain = global_settings.get('tracking_domain', 'http://localhost:5000').rstrip('/')
        
        # 5. Render Templates (Placeholders)
        variables = json.loads(lead['variables']) if lead['variables'] else {}
        # Make sure standard fields are also variables
        variables['recipient_email'] = lead['recipient_email']
        variables['cc'] = lead['cc'] or ''
        variables['bcc'] = lead['bcc'] or ''
        variables['subject'] = lead['subject'] or ''
        
        subject_rendered = render_template(lead['subject'] or "Outreach Pitch", variables)
        body_rendered = render_template(lead['body'] or "", variables)
        
        # Create HTML body
        html_body_rendered = body_rendered.replace('\n', '<br>')
        # Auto click links styling
        html_body_rendered = re.sub(
            r'(https?://[^\s<]+)', 
            r'<a href="\1" style="color: #2563EB; text-decoration: underline;">\1</a>', 
            html_body_rendered
        )
        # Add CSS wrapper
        html_body_rendered = f"<div style='font-family: Arial, sans-serif; font-size: 14px; color: #1F2937; line-height: 1.6;'>{html_body_rendered}</div>"
        
        # Replace URLs for link tracking
        html_body_rendered = rewrite_links_for_tracking(html_body_rendered, lead_id, tracking_domain)
        
        # Add open tracking pixel
        open_pixel = f'<img src="{tracking_domain}/api/track/open/{lead_id}" width="1" height="1" style="display:none;" />'
        html_body_rendered += open_pixel
        
        # Add unsubscribe footer
        unsub_url = f"{tracking_domain}/unsubscribe/{lead_id}"
        unsub_footer_html = f'''
        <br><br>
        <hr style="border:none;border-top:1px solid #E5E7EB;margin:20px 0;" />
        <p style="font-size:11px;color:#9CA3AF;text-align:center;">
            You received this email because you are in our outreach system. If you no longer wish to receive emails, you can 
            <a href="{unsub_url}" style="color:#2563EB;text-decoration:underline;">unsubscribe here</a>.
        </p>
        '''
        html_body_rendered += unsub_footer_html
        body_rendered += f"\n\n---\nTo unsubscribe, please click this link: {unsub_url}"
        
        # 6. Dispatch Email
        email_mode = global_settings.get('email_mode', 'simulated')
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if simulated or email_mode == 'simulated':
            success = True
            msg = "Simulated Success (Test Mode)"
        else:
            try:
                success, msg = send_email_actual(
                    to_email=recipient,
                    cc=lead['cc'],
                    bcc=lead['bcc'],
                    subject=subject_rendered,
                    body=body_rendered,
                    html_body=html_body_rendered,
                    attachments=lead['attachments'],
                    smtp_settings=smtp_row,
                    campaign_id=campaign_id
                )
            except Exception as e:
                success = False
                msg = str(e)
                
        # 7. Update Lead and logs
        if success:
            cursor.execute("UPDATE leads SET status = 'Sent', sent_time = ?, error_message = '' WHERE id = ?", (now_str, lead_id))
            cursor.execute('''
                INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details)
                VALUES (?, ?, 'sent', ?, ?)
            ''', (lead_id, campaign_id, now_str, msg))
            
            # Check if campaign was running, we can increment its sent count
            cursor.execute('UPDATE campaigns SET status = "running" WHERE id = ? AND status = "scheduled"', (campaign_id,))
        else:
            # Check if it was a hard bounce
            is_bounce = "bounce" in msg.lower() or "recipient refused" in msg.lower() or "550" in msg.lower() or "user unknown" in msg.lower()
            
            if is_bounce:
                cursor.execute('''
                    UPDATE leads 
                    SET status = 'Failed', bounce_status = 'hard', bounce_reason = ?, error_message = ? 
                    WHERE id = ?
                ''', (msg, f"Hard Bounce: {msg}", lead_id))
                # Automatically add to suppression list
                cursor.execute('INSERT OR IGNORE INTO suppression_list (email, reason, unsubscribed_at, campaign_id) VALUES (?, ?, ?, ?)',
                               (recipient.lower().strip(), f"Hard Bounce: {msg}", now_str, campaign_id))
                cursor.execute('''
                    INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details)
                    VALUES (?, ?, 'bounced', ?, ?)
                ''', (lead_id, campaign_id, now_str, f"Hard Bounce: {msg}"))
            else:
                # Temporary failure - retry logic
                current_retries = lead.get('retry_count', 0)
                if current_retries < 3:
                    # Reset to Pending for retry, increment retry count
                    cursor.execute('''
                        UPDATE leads 
                        SET status = 'Pending', retry_count = ?, error_message = ? 
                        WHERE id = ?
                    ''', (current_retries + 1, f"Attempt {current_retries + 1} Failed: {msg}", lead_id))
                else:
                    cursor.execute('''
                        UPDATE leads 
                        SET status = 'Failed', error_message = ? 
                        WHERE id = ?
                    ''', (f"Permanent Failure after 3 retries: {msg}", lead_id))
                    
                cursor.execute('''
                    INSERT INTO tracking_logs (lead_id, campaign_id, activity_type, timestamp, details)
                    VALUES (?, ?, 'bounced', ?, ?)
                ''', (lead_id, campaign_id, now_str, f"Soft Failure: {msg}"))
                
        conn.commit()
        return success, msg
    finally:
        conn.close()
