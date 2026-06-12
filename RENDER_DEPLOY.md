# Render Deployment - Bhatt Technologies Hub

## Quick Deploy Steps (5 Minutes)

### Step 1: Go to Render
👉 https://dashboard.render.com/register

- Click "Get Started for Free"
- Sign up with GitHub account
- Authorize Render

### Step 2: Create Web Service
1. Click "New +" button (top right)
2. Select "Web Service"
3. Click "Connect account" if needed
4. Find your repository: **vaibhavbhattcode/Auto-mail**
5. Click "Connect"

### Step 3: Configure Service
Fill in these details:

**Name:** `bhatt-tech-hub`

**Region:** Singapore (or closest to you)

**Branch:** `main`

**Root Directory:** (leave blank)

**Runtime:** `Python 3`

**Build Command:**
```
pip install -r requirements.txt
```

**Start Command:**
```
gunicorn app:app --bind 0.0.0.0:$PORT
```

**Instance Type:** `Free`

### Step 4: Environment Variables (Optional)
Click "Advanced" and add:
- Key: `PYTHON_VERSION`
- Value: `3.10.0`

### Step 5: Create Web Service
Click "Create Web Service" button at bottom

Wait 3-5 minutes for deployment...

✅ **Your app will be live at:**
```
https://bhatt-tech-hub.onrender.com
```

---

## Important Notes:

### Free Tier Limitations:
- ⚠️ Spins down after 15 minutes of inactivity
- ⚠️ Takes 30-50 seconds to wake up
- ⚠️ 750 hours/month (enough for 24/7 if only 1 app)
- ⚠️ Database may not persist between deploys

### Keep App Awake (FREE Solution):

**Use UptimeRobot:**
1. Go to: https://uptimerobot.com
2. Sign up (FREE - no credit card)
3. Add New Monitor:
   - Type: HTTP(s)
   - URL: `https://bhatt-tech-hub.onrender.com`
   - Interval: 5 minutes
4. Save

✅ Now app will NEVER sleep!

---

## After Deployment:

### 1. Test Your App:
Go to: https://bhatt-tech-hub.onrender.com
- Login: `dhruv2026`
- Configure Gmail SMTP in Settings
- Test email sending

### 2. Setup UptimeRobot:
Keep app awake 24/7 (see above)

### 3. Custom Domain (Optional):
In Render dashboard:
- Settings → Custom Domain
- Add: `app.bhatttechnologies.com`
- Update DNS at your domain registrar

---

## View Logs:
Render Dashboard → Logs (real-time)

## Redeploy After Changes:
```bash
cd "e:\mail sender"
git add .
git commit -m "Update"
git push
```
Render auto-deploys!

---

## Troubleshooting:

### Build Failed?
Check logs in Render dashboard

### App Not Loading?
- Wait 50 seconds (cold start)
- Check if gunicorn is in requirements.txt
- Verify start command is correct

### Database Issues?
Free tier doesn't persist SQLite. Options:
1. Accept database resets on deploy
2. Use external PostgreSQL (free on Render)
3. Use PythonAnywhere instead (SQLite persists)

---

## Summary:
✅ FREE forever
✅ Auto-deploy from GitHub
✅ HTTPS included
✅ Easy setup
⚠️ Sleeps after 15 min (use UptimeRobot to fix)
⚠️ Database may reset

---

Ready to deploy? Follow steps above! 🚀
