# PythonAnywhere Deployment - Bhatt Technologies Hub

PythonAnywhere is the **best FREE platform** to host this tool because, unlike Render's free tier, PythonAnywhere offers a **persistent filesystem**. This means your SQLite database (`campaigns.db`) and all uploaded sheets/attachments will **never be deleted** when the server goes to sleep or restarts.

Follow these simple steps to deploy your campaign hub live in 5 minutes.

---

## 🚀 Step-by-Step Deployment Guide

### Step 1: Create a Free Account
1. Go to 👉 [PythonAnywhere Registration](https://www.pythonanywhere.com/registration/register/free/)
2. Register for a free "Beginner" account.
3. Verify your email and log in to your PythonAnywhere Dashboard.

---

### Step 2: Clone Your Repository
1. Go to your PythonAnywhere **Consoles** tab.
2. Under "Start a new console:", click on **Bash**.
3. Clone your GitHub repository by running:
   ```bash
   git clone https://github.com/vaibhavbhattcode/Auto-mail.git
   ```
4. Navigate into the folder:
   ```bash
   cd Auto-mail
   ```

---

### Step 3: Create a Virtual Environment & Install Packages
While inside the Bash console in the `Auto-mail` folder, run these commands:
1. Create a virtual environment:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 campaign-env
   ```
2. Install all required dependencies (including cryptography and openpyxl):
   ```bash
   pip install -r requirements.txt
   ```
3. Initialize the database schema:
   ```bash
   python database.py
   ```
4. Type `exit` to close the console.

---

### Step 4: Configure the Web App
1. Go back to your PythonAnywhere Dashboard and click on the **Web** tab (top right menu).
2. Click **Add a new web app**.
3. Select **Manual configuration** (do NOT select Flask directly).
4. Select **Python 3.10** and click Next.

Now, configure the settings on the Web App page:

#### 1. Code Configuration
* **Source code:** Set to the absolute path of your cloned repo:
  `/home/yourusername/Auto-mail` *(replace `yourusername` with your PythonAnywhere username)*
* **Working directory:** Set to:
  `/home/yourusername/Auto-mail`

#### 2. Virtualenv Configuration
* **Virtualenv:** Set to:
  `/home/yourusername/.virtualenvs/campaign-env`

---

### Step 5: Edit the WSGI Configuration File
1. Under the **Code** section on the Web tab, look for **WSGI configuration file** (it will look like `/var/www/yourusername_pythonanywhere_com_wsgi.py`).
2. Click on the file link to open the editor.
3. Select all text, delete it, and replace it with the code below:

```python
import sys
import os

# Define project path
path = '/home/yourusername/Auto-mail'  # Change yourusername to your actual PythonAnywhere username
if path not in sys.path:
    sys.path.insert(0, path)

# Set the working directory
os.chdir(path)

# Import and start Flask application
from app import app as application
```

4. Click **Save** (top right) and go back to the Web tab.

---

### Step 6: Reload the App & Test Live!
1. Scroll to the top of the **Web** tab page.
2. Click the green **Reload yourusername.pythonanywhere.com** button.
3. Visit your live site at:
   `https://yourusername.pythonanywhere.com`
4. Login with username/email and default password (`password123`), and start sending campaign emails!

---

## 🔒 Security Notice
Once you log in for the first time, go to the **Global Controls** tab to change your administrator password and secure your live portal from unauthorized access.

## 📈 Auto-Tracking Domain Configuration
We have added an **auto-tracking configuration** to the system. Whenever you open your live portal at `https://yourusername.pythonanywhere.com`, the app will automatically update the tracking settings in the database, ensuring that all subsequent emails sent contain the correct tracking links.
