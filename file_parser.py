import openpyxl
import csv
import json
import re

def extract_raw_data(file_path):
    """Extract raw headers and sample rows for preview and mapping"""
    ext = file_path.split('.')[-1].lower()
    
    if ext in ['xlsx', 'xls']:
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
            rows = list(sheet.rows)
            if not rows:
                return [], []
            headers = [str(cell.value).strip() if cell.value is not None else f'Column_{i}' for i, cell in enumerate(rows[0])]
            data_rows = [[str(cell.value).strip() if cell.value is not None else '' for cell in row] for row in rows[1:6]] # First 5 rows
            return headers, data_rows
        except Exception as e:
            print(f"[Parser Error] Failed to read Excel: {str(e)}")
            return [], []
            
    elif ext == 'csv':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                rows = list(reader)
                if not rows:
                    return [], []
                headers = [h.strip() for h in rows[0]]
                data_rows = [[c.strip() for c in row] for row in rows[1:6]] # First 5 rows
                return headers, data_rows
        except Exception as e:
            print(f"[Parser Error] Failed to read CSV: {str(e)}")
            return [], []
            
    return [], []

def parse_file(file_path, column_mapping=None):
    """Parse file and return lead dicts with variables mapping"""
    ext = file_path.split('.')[-1].lower()
    leads = []
    
    if ext in ['xlsx', 'xls', 'csv']:
        headers_original = []
        data_rows = []
        
        if ext in ['xlsx', 'xls']:
            try:
                wb = openpyxl.load_workbook(file_path, data_only=True)
                sheet = wb.active
                rows = list(sheet.rows)
                if not rows:
                    return []
                headers_original = [str(cell.value).strip() if cell.value is not None else f'Column_{i}' for i, cell in enumerate(rows[0])]
                data_rows = [[str(cell.value).strip() if cell.value is not None else '' for cell in row] for row in rows[1:]]
            except Exception as e:
                print(f"[Parser Error] Failed to parse Excel: {str(e)}")
                return []
        else: # CSV
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f)
                    all_rows = list(reader)
                    if not all_rows:
                        return []
                    headers_original = [h.strip() for h in all_rows[0]]
                    data_rows = [[c.strip() for c in row] for row in all_rows[1:]]
            except Exception as e:
                print(f"[Parser Error] Failed to parse CSV: {str(e)}")
                return []
                
        # Lowercase headers for auto matching
        headers_lower = [h.lower() for h in headers_original]
        
        # Use provided mapping or auto-detect index mapping
        if column_mapping:
            # Map system keys (like 'recipient_email') to their column indices
            col_map = {k: int(v) for k, v in column_mapping.items() if v is not None and str(v).isdigit()}
        else:
            # Auto detect fallback mapping
            def find_col_idx(keywords):
                for i, col in enumerate(headers_lower):
                    for kw in keywords:
                        if kw in col:
                            return i
                return None
                
            col_map = {
                'recipient_email': find_col_idx(['email', 'contact', 'mail', 'to']),
                'cc': find_col_idx(['cc']),
                'bcc': find_col_idx(['bcc']),
                'subject': find_col_idx(['subject', 'title']),
                'body': find_col_idx(['body', 'pitch', 'message', 'text']),
                'attachments': find_col_idx(['attachment', 'file', 'files']),
                'company_name': find_col_idx(['company', 'business', 'name', 'client'])
            }
            
        # Process rows
        for cells in data_rows:
            # Skip empty rows
            if not any(cells):
                continue
                
            # Extract variables (all column names and values)
            variables = {}
            for idx, col_name in enumerate(headers_original):
                if idx < len(cells):
                    variables[col_name] = cells[idx]
                    # Also include a lowercase trimmed version for easy mapping
                    variables[col_name.lower().strip()] = cells[idx]
            
            # Map standard fields
            email = ""
            email_idx = col_map.get('recipient_email')
            if email_idx is not None and email_idx < len(cells):
                email = cells[email_idx].strip()
                
            # If email is empty, skip
            if not email or "@" not in email:
                continue
                
            cc = ""
            cc_idx = col_map.get('cc')
            if cc_idx is not None and cc_idx < len(cells):
                cc = cells[cc_idx].strip()
            elif column_mapping and 'cc' in column_mapping and column_mapping['cc'] is not None:
                val = str(column_mapping['cc']).strip()
                if not val.isdigit() and val != '':
                    cc = val
                
            bcc = ""
            bcc_idx = col_map.get('bcc')
            if bcc_idx is not None and bcc_idx < len(cells):
                bcc = cells[bcc_idx].strip()
            elif column_mapping and 'bcc' in column_mapping and column_mapping['bcc'] is not None:
                val = str(column_mapping['bcc']).strip()
                if not val.isdigit() and val != '':
                    bcc = val
                
            subject = ""
            subj_idx = col_map.get('subject')
            if subj_idx is not None and subj_idx < len(cells):
                subject = cells[subj_idx].strip()
            elif column_mapping and 'subject' in column_mapping and column_mapping['subject'] is not None:
                val = str(column_mapping['subject']).strip()
                if not val.isdigit() and val != '':
                    subject = val
                
            body = ""
            body_idx = col_map.get('body')
            if body_idx is not None and body_idx < len(cells):
                body = cells[body_idx].strip()
            elif column_mapping and 'body' in column_mapping and column_mapping['body'] is not None:
                val = str(column_mapping['body']).strip()
                if not val.isdigit() and val != '':
                    body = val
                
            attachments = ""
            attach_idx = col_map.get('attachments')
            if attach_idx is not None and attach_idx < len(cells):
                attach_val = cells[attach_idx].strip()
                if attach_val:
                    # Parse as JSON list or comma separated
                    if attach_val.startswith('[') and attach_val.endswith(']'):
                        attachments = attach_val
                    else:
                        attachments = json.dumps([f.strip() for f in attach_val.split(',') if f.strip()])
            elif column_mapping and 'attachments' in column_mapping and column_mapping['attachments'] is not None:
                val = str(column_mapping['attachments']).strip()
                if not val.isdigit() and val != '':
                    attachments = val
            
            # Add company name variable
            comp_idx = col_map.get('company_name')
            company_name = ""
            if comp_idx is not None and comp_idx < len(cells):
                company_name = cells[comp_idx].strip()
            elif column_mapping and 'company_name' in column_mapping and column_mapping['company_name'] is not None:
                val = str(column_mapping['company_name']).strip()
                if not val.isdigit() and val != '':
                    company_name = val
                    
            if not company_name:
                company_name = variables.get('company', variables.get('business', 'Client'))
            variables['company_name'] = company_name
            
            leads.append({
                'recipient_email': email,
                'cc': cc,
                'bcc': bcc,
                'subject': subject,
                'body': body,
                'attachments': attachments,
                'variables': json.dumps(variables)
            })
            
    return leads
