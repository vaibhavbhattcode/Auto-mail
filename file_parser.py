import pandas as pd
import pypdf
import re

def parse_file(file_path):
    ext = file_path.split('.')[-1].lower()
    leads = []
    
    if ext in ['xlsx', 'xls', 'csv']:
        if ext == 'csv':
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
            
        # Clean column names
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Helper to find column
        def find_col(keywords, default_val=''):
            for col in df.columns:
                for kw in keywords:
                    if kw in col:
                        return col
            return None
            
        col_company = find_col(['company', 'business', 'name', 'client'])
        col_web = find_col(['website', 'url', 'domain'])
        col_ind = find_col(['industry', 'niche', 'sector'])
        col_loc = find_col(['location', 'city', 'country'])
        col_status = find_col(['status', 'app'])
        col_email = find_col(['email', 'contact', 'mail'])
        col_phone = find_col(['whatsapp', 'phone', 'number', 'mobile'])
        col_linkedin = find_col(['linkedin', 'social'])
        col_sub = find_col(['subject'])
        col_pitch = find_col(['pitch', 'message', 'body', 'details', 'text'])
        
        for _, row in df.iterrows():
            company = str(row[col_company]).strip() if col_company and pd.notna(row[col_company]) else "Unnamed Company"
            if company == "Unnamed Company" and col_web and pd.notna(row[col_web]):
                company = str(row[col_web]).split('.')[0].capitalize()
                
            email = str(row[col_email]).strip() if col_email and pd.notna(row[col_email]) else "contact@example.com"
            # Quick email clean
            if email.startswith("UI"): email = email[2:]
            elif email.startswith("App"): email = email[3:]
            elif email.startswith("only"): email = email[4:]
            
            web = str(row[col_web]).strip() if col_web and pd.notna(row[col_web]) else "example.com"
            ind = str(row[col_ind]).strip() if col_ind and pd.notna(row[col_ind]) else "Technology"
            loc = str(row[col_loc]).strip() if col_loc and pd.notna(row[col_loc]) else "India"
            app_st = str(row[col_status]).strip() if col_status and pd.notna(row[col_status]) else "Review Needed"
            phone = str(row[col_phone]).strip() if col_phone and pd.notna(row[col_phone]) else "+91 9510539603"
            linkedin = str(row[col_linkedin]).strip() if col_linkedin and pd.notna(row[col_linkedin]) else ""
            
            sub = str(row[col_sub]).strip() if col_sub and pd.notna(row[col_sub]) else f"Your {company} app — quick thought"
            pitch = str(row[col_pitch]).strip() if col_pitch and pd.notna(row[col_pitch]) else ""
            
            # If pitch is empty, generate a nice default pitch
            if not pitch or pitch == 'nan':
                pitch = f"Hi Team at {company},\n\nI came across {company} and your platform at {web}. I noticed your current app setup is {app_st} — which seems like an untapped opportunity for your business in the {ind} space.\n\nIn your highly competitive industry, a modern, frictionless mobile app is exactly what keeps customers engaged, streamlines reorders/bookings, and drives retention.\n\nI run DhruvBuilds (dhruvbuilds.in), a specialized app development agency. We rebuild and modernize apps for businesses like yours.\n\nIf improving your app is on your roadmap this year, I'd love to share a few quick tailored ideas.\n\nHappy to connect over a short call or chat. Feel free to reply here or drop me a message on WhatsApp at {phone}.\n\nBest regards,\nDhruv Patel\nDhruvBuilds"
                
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
