# 📬 **PitchCraft AI**
# ai-cold-email-generator-agent


A fast, polished AI-powered outreach tool that helps users generate, edit, personalize, and send high-quality cold emails—without touching a single template. Built with **Mistral**, **Chat GPT**, **Streamlit**, **Cursor** and a clean modular architecture.

This project focuses on **real personalization**, **tone control**, and **a built-in analytics dashboard** that tracks email generation/sending statistics.

---

## 🚀 **Why This App? What Makes It Different?**

Most “AI email generators” online:
❌ Give generic fluff
❌ Don’t let you edit before sending
❌ Don’t allow attachments
❌ Don’t let you control tone
❌ Don’t show analytics
❌ Never explain how they work internally

**This project:**
✔️ Lets you tailor tone (Formal / Friendly / Startup)
✔️ Gives you full editing before sending
✔️ Lets you attach files (resume, portfolio, etc.)
✔️ Logs analytics for insights
✔️ Uses circuit-breaker + fallback model logic for reliability
✔️ Doesn’t hallucinate thanks to strong guardrails
✔️ Gives users the freedom to deploy on their own infra (no SaaS nonsense)

---

# 🧠 **Features**

### **✔️ Email Generator**

* High-quality outreach emails using Mistral
* Built-in tone selector
* Company insight / One-liner / How-found personalization fields

### **✔️ Edit Before Sending**

* Completely editable subject & body
* No locked templates

### **✔️ Email Sender**

* Uses Gmail SMTP securely
* Supports attachments

### **✔️ Analytics Dashboard**

* Total emails generated
* Total emails sent
* Tone usage stats
* Top companies contacted
* Daily & weekly stats

### **✔️ Reliability Enhancements**

* Circuit breaker for Mistral API
* Automatic fallback model
* Strong input validation
* Rich logger system

---

# 🗂️ Folder & File Overview

```
project/
├── app.py                # Main Streamlit app (UI + routing)
├── generate_email.py     # Handles LLM prompts & email generation logic
├── email_utils.py        # Email sending, validation, attachments
├── logger.py             # Logging configuration + utilities
├── requirements.txt      # Dependencies
├── .env.example          # Template for env variables
└── logs/
    └── app.log           # Generated logs for analytics
```

### **app.py**

* UI, layout, tone selector
* Sidebar navigation
* Routes to Email Generator + Analytics Dashboard
* Handles Streamlit state

### **generate_email.py**

* All LLM prompt engineering
* System & user prompt templates
* Sanitization
* Circuit breaker + fallback logic

### **email_utils.py**

* Validates emails
* Sends email via SMTP
* Handles attachments safely

### **logger.py**

* Writes rich logs for analytics
* Logs tone usage, generation events, errors, sent emails

---

# ⚙️ **How to Run Locally**

### **1. Clone the Repository**

```bash
git clone https://github.com/Siddharth1254/ai-cold-email-generator.git
cd ai-cold-email-generator
```

### **2. Create a Virtual Environment**

```bash
python -m venv venv
source venv/bin/activate     # Mac/Linux
venv\Scripts\activate        # Windows
```

### **3. Install Dependencies**

```bash
pip install -r requirements.txt
```

### **4. Generate Your Gmail App Password (Required)**

Google blocks normal passwords. You must generate a Gmail App Password.

Steps

Go to https://myaccount.google.com

Open Security

Enable 2-Step Verification

After enabling, open App Passwords

Re-enter your password

Under "Select app": choose Mail

Under "Select device": choose Other, name it anything

Click Generate

Google shows a 16-character password

⚠️ Use it without spaces:
If Google shows: abcd efgh ijkl mnop
Your actual password is:
abcdefghijklmnop


Paste that in your .env as:
```
EMAIL_PASSWORD=abcdefghijklmnop
```

### **5. Create the `.env` File**

Create `.env` in project root:

```
MISTRAL_API_KEY=your_key
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_app_password(abcdefghijklmnop)
```

### **6. Create the logs folder**

```
mkdir logs
touch logs/app.log
```

### **7. Run the App**

```bash
streamlit run app.py
```

---

# ☁️ **Deploy on Streamlit Cloud (Safe Method)**

⚠️ **Users must deploy their own version with their own keys (never expose your own Gmail)**

### **1. Fork this repo**

* Go to your GitHub
* Click **Fork**

### **2. Connect to Streamlit**

* [https://share.streamlit.io](https://share.streamlit.io)
* “New App”
* Select your fork
* Set branch → main
* File → `app.py`

### **3. Add Secrets**

In Streamlit → *Settings → Secrets*:

```
MISTRAL_API_KEY=...
EMAIL_ADDRESS=...
EMAIL_PASSWORD=...
```

### **4. Deploy**

Done.
The user now has their own isolated instance.

---

# 🧭 How to Contribute / Customize

* Modify tone templates
* Add more tone options
* Integrate CV extraction
* Add website scraping
* Improve design 
* Make UI with any other option
* Add cold DM generator (LinkedIn, Instagram, etc.)
