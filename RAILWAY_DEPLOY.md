# Railway Deployment Guide - Outreach Campaign Hub

Railway is an excellent cloud platform that supports outgoing SMTP ports (465/587) and offers persistent disk storage so your SQLite database never resets.

---

## Step 1: Create a Railway Account
1. Go to: https://railway.app
2. Sign up using your GitHub account.

---

## Step 2: Create a New Project
1. On the Railway dashboard, click **"New Project"** (top right).
2. Select **"Deploy from GitHub repo"**.
3. Choose your repository: **vaibhavbhattcode/Auto-mail** (you may need to search for it).
4. Click **"Deploy Now"**.

---

## Step 3: Add a Persistent Disk (Crucial for SQLite)
Since your database is a SQLite file (`campaigns.db`), you need a persistent disk so your campaigns and leads are not deleted when the server restarts or redeploys:

1. Click on your newly created service block on the Railway canvas.
2. Go to the **Settings** tab.
3. Scroll down to the **Volumes** section.
4. Click **"Add Volume"**.
5. Name it `mail_volume` and set the Mount Path to:
   ```text
   /data
   ```

---

## Step 4: Configure Environment Variables
1. Go to the **Variables** tab of your service.
2. Click **"New Variable"** and add:
   - **Key**: `DATABASE_PATH`
   - **Value**: `/data/campaigns.db`
3. Click **"New Variable"** and add:
   - **Key**: `PORT`
   - **Value**: `5000` (or leave it empty, Railway binds automatically)

---

## Step 5: Configure the Start Command
Railway automatically detects Python and reads your `requirements.txt`, but to ensure it runs correctly:

1. Go to the **Settings** tab.
2. Scroll down to the **Deploy** section.
3. Set the **Start Command** to:
   ```bash
   gunicorn app:app --bind 0.0.0.0:$PORT
   ```

---

## Step 6: Generate a Public Domain
1. In the **Settings** tab, scroll to the **Networking** section.
2. Click **"Generate Domain"**.
3. Railway will give you a public HTTPS URL (e.g. `https://auto-mail-production.up.railway.app`).

🎉 **Your app is now live, fully persistent, and outbound SMTP works!**
