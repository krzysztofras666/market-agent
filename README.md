# GPW Recommendations Daily Emailer

Scrapes GPW analyst recommendations, summarizes them with OpenAI, and sends a daily email via Gmail.

**Sources:** BiznesRadar, mBank (when available)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create `.env` (see `.env.example`):

```
OPENAI_API_KEY=your_openai_api_key
GMAIL_EMAIL=your@gmail.com
GMAIL_APP_PASSWORD=your_gmail_app_password
EMAIL_TO=recipient@gmail.com
```

3. Gmail app password: https://myaccount.google.com/apppasswords

4. Run:

```bash
python main4.py
```
