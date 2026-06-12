# GitHub Setup & Push Instructions

## Step 1: Create GitHub Repository

1. Go to: https://github.com/new
2. Repository name: **bhatt-tech-hub**
3. Description: **Automated lead outreach dashboard for Bhatt Technologies**
4. Choose: **Private** (recommended) or Public
5. **DO NOT** check "Initialize with README"
6. Click **Create repository**

## Step 2: Push to GitHub

Copy your repository URL (looks like):
```
https://github.com/yourusername/bhatt-tech-hub.git
```

Then run these commands in PowerShell:

```bash
cd "e:\mail sender"

git branch -M main

git remote add origin https://github.com/yourusername/bhatt-tech-hub.git

git push -u origin main
```

Enter your GitHub credentials when prompted.

## Step 3: Verify

Go to your GitHub repository URL - all files should be there!

## Files Included (Clean):
✅ app.py
✅ database.py
✅ email_service.py
✅ file_parser.py
✅ campaigns.db
✅ initial_leads.json
✅ requirements.txt
✅ start_cloudflare.bat
✅ templates/index.html
✅ README.md
✅ .gitignore

## Files Excluded (Unwanted):
❌ All test files removed
❌ All deployment guides removed
❌ Diagnostic scripts removed
❌ Setup scripts removed
❌ cloudflared.exe excluded

---

## Next Steps After Push:

### Option A: Deploy on Render
1. Go to: https://render.com
2. Connect GitHub repository
3. Auto-deploy!

### Option B: Deploy on PythonAnywhere
1. Download zip from GitHub
2. Upload to PythonAnywhere
3. Configure and deploy

---

Your GitHub repository is ready! 🚀
