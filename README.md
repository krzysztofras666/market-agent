GPW Recommendations Daily Emailer
---------------------------------

Features:
- Scrapes GPW analyst recommendations
- Summarizes them with OpenAI
- Sends HTML email via Gmail
- Ready for cron scheduling

Sources:
- BiznesRadar
- mBank recommendations

SETUP
-----

1. Install dependencies

pip install requests beautifulsoup4 pandas openai python-dotenv lxml

2. Create .env file

OPENAI_API_KEY=your_openai_api_key
GMAIL_EMAIL=your@gmail.com
GMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_TO=recipient@gmail.com

3. Gmail App Password
https://myaccount.google.com/apppasswords

4. Run

python gpw_daily_email.py
