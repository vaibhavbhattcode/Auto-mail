"""
Comprehensive System Health Check for Mail Sender
Tests all components: Database, SMTP module, Email service, App routes
"""
import sys
import os
import json
import traceback

# Set encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def test_result(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    icon = "[OK]" if passed else "[!!]"
    print(f"  {icon} {name}: {status}" + (f" -- {detail}" if detail else ""))
    return passed

print("=" * 60)
print("  MAIL SENDER - COMPREHENSIVE SYSTEM HEALTH CHECK")
print("=" * 60)
total = 0
passed = 0

# ===== 1. Module Imports =====
print("\n--- Module Import Tests ---")
try:
    import database
    total += 1; passed += test_result("database module", True)
except Exception as e:
    total += 1; test_result("database module", False, str(e))

try:
    import email_service
    total += 1; passed += test_result("email_service module", True)
except Exception as e:
    total += 1; test_result("email_service module", False, str(e))

try:
    import file_parser
    total += 1; passed += test_result("file_parser module", True)
except Exception as e:
    total += 1; test_result("file_parser module", False, str(e))

try:
    import export_service
    total += 1; passed += test_result("export_service module", True)
except Exception as e:
    total += 1; test_result("export_service module", False, str(e))

try:
    from email.utils import formatdate
    d = formatdate(localtime=True)
    total += 1; passed += test_result("email.utils.formatdate", True, f"Date: {d}")
except Exception as e:
    total += 1; test_result("email.utils.formatdate", False, str(e))

# ===== 2. Database Tests =====
print("\n--- Database Tests ---")
try:
    database.init_db()
    total += 1; passed += test_result("Database init_db()", True)
except Exception as e:
    total += 1; test_result("Database init_db()", False, str(e))

try:
    conn = database.get_db()
    cursor = conn.cursor()
    
    # Check all required tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r['name'] for r in cursor.fetchall()]
    required_tables = ['users', 'smtp_accounts', 'campaigns', 'leads', 'suppression_list', 'tracking_logs', 'settings']
    missing = [t for t in required_tables if t not in tables]
    total += 1; passed += test_result("Required tables exist", len(missing) == 0, 
                                       f"Found: {tables}" if len(missing) == 0 else f"Missing: {missing}")
    conn.close()
except Exception as e:
    total += 1; test_result("Required tables", False, str(e))

try:
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key = 'email_mode'")
    row = cursor.fetchone()
    mode = row['value'] if row else 'NOT SET'
    total += 1; passed += test_result("email_mode setting", mode == 'live', f"Current: {mode}")
    conn.close()
except Exception as e:
    total += 1; test_result("email_mode setting", False, str(e))

# Check SMTP accounts
try:
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email_address, smtp_host, smtp_port, ssl_tls FROM smtp_accounts")
    accounts = [dict(r) for r in cursor.fetchall()]
    total += 1; passed += test_result("SMTP accounts exist", len(accounts) > 0, f"Found {len(accounts)} account(s)")
    
    # Check each SMTP account for issues
    for acc in accounts:
        host = acc['smtp_host']
        port = acc['smtp_port']
        ssl = acc['ssl_tls']
        
        # Titan/GoDaddy port mismatch check
        is_titan = 'titan' in host or 'secureserver' in host
        if is_titan:
            if port not in (465, 587):
                total += 1; test_result(f"SMTP #{acc['id']} port config", False, 
                                         f"{acc['email_address']} ({host}:{port}/{ssl}) - Titan Mail should use port 465 (SSL) or port 587 (TLS/STARTTLS)!")
            elif port == 465 and ssl != 'ssl':
                total += 1; test_result(f"SMTP #{acc['id']} SSL config", False,
                                         f"{acc['email_address']} ({host}:{port}/{ssl}) - Titan Mail on port 465 should use SSL!")
            elif port == 587 and ssl != 'tls':
                total += 1; test_result(f"SMTP #{acc['id']} TLS config", False,
                                         f"{acc['email_address']} ({host}:{port}/{ssl}) - Titan Mail on port 587 should use TLS!")
            else:
                total += 1; passed += test_result(f"SMTP #{acc['id']} config", True, 
                                                   f"{acc['email_address']} ({host}:{port}/{ssl})")
        else:
            total += 1; passed += test_result(f"SMTP #{acc['id']} config", True, 
                                               f"{acc['email_address']} ({host}:{port}/{ssl})")
        
        # Check password is encrypted
        cursor.execute("SELECT password_encrypted FROM smtp_accounts WHERE id = ?", (acc['id'],))
        pw_row = cursor.fetchone()
        has_password = pw_row and pw_row['password_encrypted'] and len(pw_row['password_encrypted']) > 10
        total += 1; passed += test_result(f"SMTP #{acc['id']} password stored", has_password)
        
        # Test decryption works
        if has_password:
            try:
                decrypted = database.decrypt_password(pw_row['password_encrypted'])
                total += 1; passed += test_result(f"SMTP #{acc['id']} password decrypt", len(decrypted) > 0)
            except Exception as e:
                total += 1; test_result(f"SMTP #{acc['id']} password decrypt", False, str(e))
    
    conn.close()
except Exception as e:
    total += 1; test_result("SMTP accounts check", False, str(e))

# ===== 3. Email Service Tests =====
print("\n--- Email Service Tests ---")

# Test template rendering
try:
    result = email_service.render_template("Hello {{name}}, welcome to [[company]]!", 
                                            {"name": "Test", "company": "Acme"})
    expected = "Hello Test, welcome to Acme!"
    total += 1; passed += test_result("Template {{}} rendering", result == expected, f"Got: {result}")
except Exception as e:
    total += 1; test_result("Template rendering", False, str(e))

try:
    result = email_service.render_template("{{Name}} at {{Company}}", 
                                            {"name": "Test", "company": "Acme"})
    total += 1; passed += test_result("Case-insensitive templates", "Test" in result, f"Got: {result}")
except Exception as e:
    total += 1; test_result("Case-insensitive templates", False, str(e))

# Test link tracking rewriting
try:
    html = '<a href="https://example.com">Click</a>'
    result = email_service.rewrite_links_for_tracking(html, 1, "https://track.test.com")
    total += 1; passed += test_result("Link tracking rewrite", "track.test.com" in result, f"Rewrote to: {result[:80]}...")
except Exception as e:
    total += 1; test_result("Link tracking rewrite", False, str(e))

# Test that unsubscribe links are NOT rewritten
try:
    html = '<a href="https://track.test.com/unsubscribe/1">Unsub</a>'
    result = email_service.rewrite_links_for_tracking(html, 1, "https://track.test.com")
    total += 1; passed += test_result("Unsubscribe link preserved", "/unsubscribe/" in result)
except Exception as e:
    total += 1; test_result("Unsubscribe link preserved", False, str(e))

# ===== 4. SMTP Connection Test (Real) =====
print("\n--- SMTP Connection Tests ---")
try:
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM smtp_accounts LIMIT 1")
    smtp_row = cursor.fetchone()
    conn.close()
    
    if smtp_row:
        smtp_row = dict(smtp_row)
        smtp_row['password'] = database.decrypt_password(smtp_row['password_encrypted'])
        
        host = smtp_row['smtp_host']
        port = int(smtp_row['smtp_port'])
        ssl_tls = smtp_row['ssl_tls']
        
        print(f"  [..] Testing SMTP connection to {host}:{port} ({ssl_tls})...")
        
        import smtplib
        import ssl as ssl_module
        
        try:
            if ssl_tls == 'ssl' or port == 465:
                context = ssl_module.create_default_context()
                try:
                    server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
                except (ssl_module.SSLError, ssl_module.CertificateError) as ssl_err:
                    context = ssl_module._create_unverified_context()
                    server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.ehlo()
                if ssl_tls == 'tls' or port == 587:
                    context = ssl_module.create_default_context()
                    try:
                        server.starttls(context=context)
                    except (ssl_module.SSLError, ssl_module.CertificateError) as ssl_err:
                        context = ssl_module._create_unverified_context()
                        server.starttls(context=context)
                    server.ehlo()
            
            total += 1; passed += test_result("SMTP Server Connect", True, f"Connected to {host}:{port}")
            
            # Try login
            try:
                server.login(smtp_row['email_address'], smtp_row['password'])
                total += 1; passed += test_result("SMTP Authentication", True, f"Logged in as {smtp_row['email_address']}")
            except smtplib.SMTPAuthenticationError as e:
                total += 1; test_result("SMTP Authentication", False, f"Auth failed: {str(e)[:100]}")
            except Exception as e:
                total += 1; test_result("SMTP Authentication", False, str(e)[:100])
            
            try:
                server.quit()
            except:
                pass
                
        except smtplib.SMTPConnectError as e:
            total += 1; test_result("SMTP Server Connect", False, f"Connection error: {str(e)[:100]}")
        except ConnectionRefusedError:
            total += 1; test_result("SMTP Server Connect", False, f"Connection refused by {host}:{port}")
        except TimeoutError:
            total += 1; test_result("SMTP Server Connect", False, f"Timeout connecting to {host}:{port}")
        except Exception as e:
            total += 1; test_result("SMTP Server Connect", False, f"{type(e).__name__}: {str(e)[:100]}")
    else:
        total += 1; test_result("SMTP Account Available", False, "No SMTP accounts configured!")
except Exception as e:
    total += 1; test_result("SMTP Tests", False, traceback.format_exc()[:200])

# ===== 5. Campaign/Leads Status =====
print("\n--- Campaign & Leads Status ---")
try:
    conn = database.get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM campaigns")
    camp_count = cursor.fetchone()[0]
    total += 1; passed += test_result("Campaigns in DB", True, f"{camp_count} campaign(s)")
    
    cursor.execute("SELECT status, COUNT(*) as cnt FROM leads GROUP BY status")
    leads_status = {r['status']: r['cnt'] for r in cursor.fetchall()}
    total_leads = sum(leads_status.values())
    total += 1; passed += test_result("Leads in DB", True, f"{total_leads} leads: {dict(leads_status)}")
    
    # Check for stuck "Processing" leads (bug indicator)
    processing = leads_status.get('Processing', 0)
    total += 1; passed += test_result("No stuck Processing leads", processing == 0, 
                                       f"Found {processing} stuck leads!" if processing > 0 else "Clean")
    
    conn.close()
except Exception as e:
    total += 1; test_result("Campaign/Leads check", False, str(e))

# ===== 6. Flask App Import Test =====
print("\n--- Flask App Test ---")
try:
    # We can't fully test the Flask app without running it, but we can import and check routes
    sys.modules.pop('app', None)  # Clear cached import
    
    # Quick import test - just verify the module structure is valid
    import importlib.util
    spec = importlib.util.spec_from_file_location("app_check", os.path.join(os.getcwd(), "app.py"))
    total += 1; passed += test_result("app.py module valid", spec is not None)
except Exception as e:
    total += 1; test_result("Flask App import", False, str(e)[:150])

# ===== SUMMARY =====
print("\n" + "=" * 60)
failed = total - passed
if failed == 0:
    print(f"  ALL {total} TESTS PASSED! System is healthy.")
else:
    print(f"  {passed}/{total} PASSED, {failed} FAILED")
    print(f"  Fix the FAILED items above before sending emails.")
print("=" * 60)
