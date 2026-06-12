import openpyxl
import pypdf
import re

def parse_file(file_path):
    ext = file_path.split('.')[-1].lower()
    leads = []
    
    if ext in ['xlsx', 'xls']:
        # Use openpyxl directly
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active
        
        # Get headers
        headers = []
        for cell in sheet[1]:
            headers.append(str(cell.value).strip().lower() if cell.value else '')
        
        # Helper to find column index
        def find_col_idx(keywords):
            for i, col in enumerate(headers):
                for kw in keywords:
                    if kw in col:
                        return i
            return None
        
        col_company = find_col_idx(['company', 'business', 'name', 'client'])
        col_web = find_col_idx(['website', 'url', 'domain'])
        col_ind = find_col_idx(['industry', 'niche', 'sector'])
        col_loc = find_col_idx(['location', 'city', 'country'])
        col_status = find_col_idx(['status', 'app'])
        col_email = find_col_idx(['email', 'contact', 'mail'])
        col_phone = find_col_idx(['whatsapp', 'phone', 'number', 'mobile'])
        col_linkedin = find_col_idx(['linkedin', 'social'])
        col_sub = find_col_idx(['subject'])
        col_pitch = find_col_idx(['pitch', 'message', 'body', 'details', 'text'])
        
        # Process rows (skip header)
        for row in list(sheet.rows)[1:]:
            cells = [cell.value for cell in row]
            
            company = str(cells[col_company]).strip() if col_company is not None and cells[col_company] else "Unnamed Company"
            if company == "Unnamed Company" and col_web is not None and cells[col_web]:
                company = str(cells[col_web]).split('.')[0].capitalize()
            
            email = str(cells[col_email]).strip() if col_email is not None and cells[col_email] else "contact@example.com"
            if email.startswith("UI"): email = email[2:]
            elif email.startswith("App"): email = email[3:]
            elif email.startswith("only"): email = email[4:]
            
            web = str(cells[col_web]).strip() if col_web is not None and cells[col_web] else "example.com"
            ind = str(cells[col_ind]).strip() if col_ind is not None and cells[col_ind] else "Technology"
            loc = str(cells[col_loc]).strip() if col_loc is not None and cells[col_loc] else "India"
            app_st = str(cells[col_status]).strip() if col_status is not None and cells[col_status] else "Review Needed"
            phone = str(cells[col_phone]).strip() if col_phone is not None and cells[col_phone] else "+91 9510539603"
            linkedin = str(cells[col_linkedin]).strip() if col_linkedin is not None and cells[col_linkedin] else ""
            sub = str(cells[col_sub]).strip() if col_sub is not None and cells[col_sub] else f"Your {company} app — quick thought"
            pitch = str(cells[col_pitch]).strip() if col_pitch is not None and cells[col_pitch] else ""
            
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
