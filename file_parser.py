import openpyxl
import pypdf
import csv
import re

def extract_raw_data(file_path):
    """Extract raw headers and rows for preview/mapping"""
    ext = file_path.split('.')[-1].lower()
    
    if ext in ['xlsx', 'xls']:
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active
        rows = list(sheet.rows)
        if not rows:
            return [], []
        headers = [str(cell.value).strip() if cell.value else f'Column_{i}' for i, cell in enumerate(rows[0])]
        data_rows = [[str(cell.value) if cell.value else '' for cell in row] for row in rows[1:6]]  # First 5 rows
        return headers, data_rows
    
    elif ext == 'csv':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                return [], []
            headers = rows[0]
            data_rows = rows[1:6]  # First 5 rows
            return headers, data_rows
    
    return [], []

def parse_file(file_path, column_mapping=None):
    """Parse file with optional column mapping"""
    ext = file_path.split('.')[-1].lower()
    leads = []
    
    if ext in ['xlsx', 'xls', 'csv']:
        if ext in ['xlsx', 'xls']:
            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active
            rows = list(sheet.rows)
            headers = [str(cell.value).strip().lower() if cell.value else '' for cell in rows[0]]
            data_rows = [[str(cell.value) if cell.value else '' for cell in row] for row in rows[1:]]
        else:  # CSV
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                all_rows = list(reader)
                if not all_rows:
                    return []
                headers = [h.strip().lower() for h in all_rows[0]]
                data_rows = all_rows[1:]
        
        # Use provided mapping or auto-detect
        if column_mapping:
            col_map = column_mapping
        else:
            def find_col_idx(keywords):
                for i, col in enumerate(headers):
                    for kw in keywords:
                        if kw in col:
                            return i
                return None
            
            col_map = {
                'company_name': find_col_idx(['company', 'business', 'name', 'client']),
                'website': find_col_idx(['website', 'url', 'domain']),
                'industry': find_col_idx(['industry', 'niche', 'sector']),
                'location': find_col_idx(['location', 'city', 'country']),
                'app_status': find_col_idx(['status', 'app']),
                'contact_email': find_col_idx(['email', 'contact', 'mail']),
                'whatsapp_number': find_col_idx(['whatsapp', 'phone', 'number', 'mobile']),
                'linkedin': find_col_idx(['linkedin', 'social']),
                'subject': find_col_idx(['subject']),
                'pitch': find_col_idx(['pitch', 'message', 'body', 'details', 'text'])
            }
        
        # Process data rows
        for cells in data_rows:
            company = cells[col_map['company_name']].strip() if col_map.get('company_name') is not None and len(cells) > col_map['company_name'] else "Unnamed Company"
            email = cells[col_map['contact_email']].strip() if col_map.get('contact_email') is not None and len(cells) > col_map['contact_email'] else "contact@example.com"
            web = cells[col_map['website']].strip() if col_map.get('website') is not None and len(cells) > col_map['website'] else "example.com"
            
            if company == "Unnamed Company" and web != "example.com":
                company = web.split('.')[0].capitalize()
            
            email = email.lstrip('UIAponly')
            
            ind = cells[col_map['industry']].strip() if col_map.get('industry') is not None and len(cells) > col_map['industry'] else "Technology"
            loc = cells[col_map['location']].strip() if col_map.get('location') is not None and len(cells) > col_map['location'] else "India"
            app_st = cells[col_map['app_status']].strip() if col_map.get('app_status') is not None and len(cells) > col_map['app_status'] else "Review Needed"
            phone = cells[col_map['whatsapp_number']].strip() if col_map.get('whatsapp_number') is not None and len(cells) > col_map['whatsapp_number'] else "+91 9510539603"
            linkedin = cells[col_map['linkedin']].strip() if col_map.get('linkedin') is not None and len(cells) > col_map['linkedin'] else ""
            sub = cells[col_map['subject']].strip() if col_map.get('subject') is not None and len(cells) > col_map['subject'] else f"Your {company} app — quick thought"
            pitch = cells[col_map['pitch']].strip() if col_map.get('pitch') is not None and len(cells) > col_map['pitch'] else ""
            
            if not pitch or pitch == 'None':
                pitch = f"Hi Team at {company},\n\nI came across {company} and your platform at {web}. I noticed your current app setup is {app_st}.\n\nI run Bhatt Technologies, a specialized app development agency.\n\nHappy to connect. Reply here or WhatsApp at {phone}.\n\nBest regards,\nVaibhav Bhatt\nBhatt Technologies"
            
            leads.append({
                "company_name": company,
                "website": web,
                "industry": ind,
                "location": loc,
                "app_status": app_st,
                "contact_email": email,
                "whatsapp_number": phone,
                "linkedin": linkedin,
                "subject": sub,
                "pitch": pitch,
                "status": "Pending"
            })
            
    elif ext == 'pdf':
        reader = pypdf.PdfReader(file_path)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() + "\n"

        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        for i in range(len(lines)):
            line = lines[i]
            if line.startswith("Hi,") or ("DhruvBuilds" in line and not lines[i-1].startswith("Hi,")):
                continue
            if "Company/Business Name" in line:
                continue
                
            if i + 1 < len(lines) and lines[i+1].startswith("Hi,"):
                meta = lines[i]
                pitch = lines[i+1]
                
                meta_spaced = re.sub(r'(https?://)', r' \1', meta)
                meta_spaced = re.sub(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,})', r' \1 ', meta_spaced)
                
                email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,})', meta_spaced)
                contact_email = email_match.group(1).strip() if email_match else "contact@example.com"
                if contact_email.startswith("UI"): contact_email = contact_email[2:]
                elif contact_email.startswith("App"): contact_email = contact_email[3:]
                elif contact_email.startswith("only"): contact_email = contact_email[4:]

                parts = meta.split('Pending')
                if len(parts) > 1:
                    subject = parts[1].strip()
                    before_pending = parts[0].strip()
                else:
                    subject = "App Development Pitch"
                    before_pending = meta
                    
                web_match = re.search(r'([a-zA-Z0-9-]+\.(?:com|co|in|org|net|co\.in))', before_pending, re.IGNORECASE)
                website = web_match.group(1).strip() if web_match else "example.com"
                
                if website != "example.com" and website in before_pending:
                    company_name = before_pending.split(website)[0].strip()
                else:
                    company_name = before_pending[:15].strip()
                    
                company_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', company_name)
                if not company_name or len(company_name) < 2:
                    company_name = website.split('.')[0].capitalize()
                    
                phone_match = re.search(r'(\+?\d{1,3}[\s-]?\d{4,5}[\s-]?\d{4,5})', pitch)
                whatsapp_number = phone_match.group(1) if phone_match else "+91 9510539603"
                
                industry = "Health & Wellness"
                if "EdTech" in before_pending or "Education" in before_pending or "Learning" in before_pending or "IIDE" in before_pending or "Vedantu" in before_pending or "Cuemath" in before_pending:
                    industry = "EdTech & Learning"
                elif "E-commerce" in before_pending or "Commerce" in before_pending or "Store" in before_pending or "IndiaMART" in before_pending:
                    industry = "E-commerce & Retail"
                elif "Fitness" in before_pending or "Gym" in before_pending or "Fit" in before_pending or "Health" in before_pending:
                    industry = "Fitness & Wellness"

                leads.append({
                    "company_name": company_name,
                    "website": website,
                    "industry": industry,
                    "location": "India",
                    "app_status": "Review Needed",
                    "contact_email": contact_email,
                    "whatsapp_number": whatsapp_number,
                    "linkedin": "",
                    "subject": subject,
                    "pitch": pitch,
                    "status": "Pending"
                })
                
    return leads
