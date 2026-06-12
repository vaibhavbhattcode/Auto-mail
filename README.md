# Bhatt Technologies Hub

Automated lead outreach dashboard for managing prospects, editing pitch templates, uploading lead sheets, and sending or scheduling email campaigns.

## Features

- 🔐 Secure login gate
- 📊 Lead management (Create, Edit, Delete, Search, Bulk actions)
- 📤 File upload support (`.xlsx`, `.csv`, `.pdf`)
- 📝 Dynamic pitch templates with placeholders
- ✉️ Instant send & scheduled email campaigns
- 📧 Gmail & Titan Mail SMTP support
- 📋 Audit logs for all email activities
- ⚙️ Background scheduler for automated emails

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Locally
```bash
python app.py
```

Open: `http://localhost:5000`

**Default Login:** `dhruv2026`

### 3. Deploy Publicly (FREE)

#### Option 1: Cloudflare Tunnel (Recommended)
```bash
# Double-click to start:
start_cloudflare.bat
```

#### Option 2: PythonAnywhere
1. Sign up: https://www.pythonanywhere.com
2. Upload files via web interface
3. Configure WSGI and deploy

Full deployment guides available in project documentation.

## Configuration

1. Login to dashboard
2. Go to **Settings** tab
3. Configure SMTP:
   - Gmail: Use 16-character App Password
   - Titan: Use regular password
4. Test connection before sending emails

## Tech Stack

- **Backend:** Flask (Python)
- **Database:** SQLite
- **Frontend:** Vue.js 3 + Tailwind CSS
- **Email:** SMTP (Gmail/Titan)

## File Structure

```
bhatt-tech-hub/
├── app.py                 # Main Flask application
├── database.py            # Database setup & queries
├── email_service.py       # SMTP email functionality
├── file_parser.py         # Excel/CSV/PDF parser
├── campaigns.db           # SQLite database
├── initial_leads.json     # Seed data
├── requirements.txt       # Python dependencies
├── start_cloudflare.bat   # Quick deployment script
├── templates/
│   └── index.html        # Frontend dashboard
└── uploads/              # Lead file uploads

```

## Environment Variables

- `PORT` - Server port (default: 5000)

## Support

For issues or questions, contact: vaibhavbhatt2022@gmail.com

## License

Private project - Bhatt Technologies © 2024
