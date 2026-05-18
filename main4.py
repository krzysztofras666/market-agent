import requests
from bs4 import BeautifulSoup
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
import json
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
from dotenv import load_dotenv
from datetime import datetime

# =========================
# CONFIG
# =========================

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = os.getenv("GMAIL_EMAIL")
EMAIL_PASSWORD = "ykjq ivjo pexv kkil"
EMAIL_RECEIVER  = os.getenv("EMAIL_TO")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

STATE_FILE = "previous_recommendations.json"

# =========================
# PORTFOLIO
# =========================

PORTFOLIO = {
    "11B": "11BIT",
    "AMC": "AMICA",
    "ASE": "ASSECOSEE",
    "ASB": "ASBIS",
    "ATA": "ATAL",
    "BNP": "BNPPPL",
    "CMP": "CLNPHARMA",
    "CBF": "CYBERFLKS",
    "DIG": "DIAG",
    "DNP": "DINOPL",
    "ELT": "ELEKTROTI",
    "ENA": "ENEA",
    "ENT": "ENTER",
    "ERB": "ERBUD",
    "EBS": "ERSTE",
    "HUG": "HUUUGE",
    "KER": "KERNEL",
    "KTY": "KETY",
    "KRU": "KRUK SA",
    "LPP": "LPP",
    "MDV": "MODIVO",
    "MOL": "MOLECURE",
    "NWG": "NEWAG",
    "NCL": "NOCTILUCA",
    "OPL": "OPONEO",
    "PAS": "PASSUS",
    "PCF": "PCFGROUP",
    "PEO": "PEKAO",
    "PCO": "PEPCO",
    "PEN": "PHOTON",
    "PKN": "PKNORLEN",
    "PRM": "PROCHEM",
    "PZU": "PZU",
    "RBW": "RAINBOW",
    "RVU": "RVU",
    "TEN": "TSGAMES",
    "UNT": "UNIMOT",
    "ZAB": "ZABKA",
}

PORTFOLIO_ALIASES = {
    "11 BIT STUDIOS": "11B",
    "AMICA": "AMC",
    "ASSECO SEE": "ASE",
    "ASBIS": "ASB",
    "ATAL": "ATA",
    "BNP PARIBAS": "BNP",
    "CYBER_FOLKS": "CBF",
    "DINO POLSKA": "DNP",
    "ELEKTROTIM": "ELT",
    "ENEA": "ENA",
    "ENTER AIR": "ENT",
    "ERBUD": "ERB",
    "ERSTE GROUP": "EBS",
    "HUUUGE": "HUG",
    "KERNEL": "KER",
    "KETY": "KTY",
    "KRUK": "KRU",
    "LPP": "LPP",
    "MODIVO": "MDV",
    "MOLECURE": "MOL",
    "NEWAG": "NWG",
    "NOCTILUCA": "NCL",
    "OPONEO": "OPL",
    "PASSUS": "PAS",
    "PCF GROUP": "PCF",
    "PEKAO": "PEO",
    "PEPCO GROUP": "PCO",
    "PHOTON ENERGY": "PEN",
    "PKN ORLEN": "PKN",
    "ORLEN": "PKN",
    "PROCHEM": "PRM",
    "PZU": "PZU",
    "RAINBOW TOURS": "RBW",
    "RVU": "RVU",
    "TEN SQUARE GAMES": "TEN",
    "TSGAMES": "TEN",
    "UNIMOT": "UNT",
    "ZABKA": "ZAB",
    "ŻABKA": "ZAB",
}

# =========================
# OPENAI
# =========================

#print OPENAI_API_KEY;
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# HELPERS
# =========================

def clean_price(value):
    try:
        return float(
            str(value)
            .replace(" ", "")
            .replace(",", ".")
        )
    except:
        return 0.0


def extract_ticker(company_name):

    match = re.search(r"\((.*?)\)", company_name)

    if match:
        return match.group(1).upper().strip()

    return company_name.upper().strip()


def normalize_name(name):

    normalized = (
        name.upper()
        .replace(".", "")
        .replace("-", " ")
        .replace("_", " ")
        .replace(",", "")
    )

    noise = [
        " SPOLKA AKCYJNA",
        " SPÓŁKA AKCYJNA",
        " SA",
        " S A",
        " NV",
        " N V",
        " PLC",
    ]

    for item in noise:
        normalized = normalized.replace(item, "")

    return " ".join(normalized.split())


def is_portfolio_match(company_name):

    normalized = normalize_name(company_name)

    # aliases
    for alias in PORTFOLIO_ALIASES:

        if alias in normalized:
            return True

    return False


def calculate_score(rec):

    score = 5

    recommendation = rec["recommendation"].lower()

    if "kupuj" in recommendation:
        score += 3

    elif "akumuluj" in recommendation:
        score += 2

    elif "trzymaj" in recommendation:
        score += 0

    elif "neutral" in recommendation:
        score -= 1

    elif "sprzedaj" in recommendation:
        score -= 3

    upside = (
        (rec["target_price"] - rec["current_price"])
        / rec["current_price"]
    ) * 100

    if upside > 25:
        score += 2

    elif upside > 10:
        score += 1

    return max(1, min(score, 10))


def trading_signal(score):

    if score >= 8:
        return "BUY"

    elif score >= 5:
        return "HOLD"

    else:
        return "REDUCE"

# =========================
# LOAD PREVIOUS STATE
# =========================

try:
    with open(STATE_FILE, "r") as f:
        previous_state = json.load(f)

except:
    previous_state = {}

# =========================
# SCRAPE BIZNESRADAR
# =========================

url = "https://www.biznesradar.pl/rekomendacje/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)

soup = BeautifulSoup(response.text, "html.parser")

table = soup.find("table")

rows = table.find_all("tr")

recommendations = []

for row in rows[1:]:

    cols = row.find_all("td")

    if len(cols) < 6:
        continue

    try:
        company = cols[0].get_text(strip=True)
        recommendation = cols[1].get_text(strip=True)
        target_price = clean_price(cols[2].get_text(strip=True))
        current_price = clean_price(cols[3].get_text(strip=True))
        date = cols[5].get_text(strip=True)

        rec = {
	   "source": "BiznesRadar",
            "company": company,
            "recommendation": recommendation,
            "target_price": target_price,
            "current_price": current_price,
            "date": date,
        }

        rec["score"] = calculate_score(rec)
        rec["signal"] = trading_signal(rec["score"])
        rec["portfolio_match"] = is_portfolio_match(company)

        recommendations.append(rec)

    except Exception as e:
        print("Error:", e)


# =========================
# SCRAPE MBANK (SELENIUM)
# =========================

try:

    options = webdriver.ChromeOptions()

    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(
            ChromeDriverManager().install()
        ),
        options=options
    )

    mbank_url = "https://serwis-informacyjny.mbank.pl/rekomendacje"

    driver.get(mbank_url)

    time.sleep(5)

    rows = driver.find_elements(
        By.TAG_NAME,
        "tr"
    )

    for row in rows:

        cols = row.find_elements(By.TAG_NAME, "td")

        if len(cols) < 5:
            continue

        try:

            company = cols[0].text.strip()

            recommendation = cols[1].text.strip()

            target_price = clean_price(
                cols[2].text.strip()
            )

            current_price = clean_price(
                cols[3].text.strip()
            )

            date = cols[4].text.strip()

            rec = {
                "source": "mBank",
                "company": company,
                "recommendation": recommendation,
                "target_price": target_price,
                "current_price": current_price,
                "date": date,
            }

            rec["score"] = calculate_score(rec)

            rec["signal"] = trading_signal(
                rec["score"]
            )

            rec["portfolio_match"] = is_portfolio_match(
                company
            )

            recommendations.append(rec)
	    



        except Exception as e:

            print(
                "mBank row parse error:",
                e
            )

    driver.quit()

except Exception as e:

    print(
        "mBank selenium error:",
        e
    )

print("mBank recommendations:", len(recommendations))

# =========================
# FILTER PORTFOLIO
# =========================

portfolio_hits = [
    rec for rec in recommendations
    if rec["portfolio_match"]
]

print("\n====================")
print("PORTFOLIO MATCHES")
print("====================")

for rec in portfolio_hits:

    print(
        rec["source"],
        "|",
        rec["company"],
        "|",
        rec["recommendation"]
    )

# =========================
# DETECT CHANGES
# =========================

changes = []

for rec in portfolio_hits:

    ticker = rec["company"]

    old = previous_state.get(ticker)

    if old != rec["recommendation"]:
        changes.append(rec)

# =========================
# SAVE CURRENT STATE
# =========================

current_state = {
    rec["company"]: rec["recommendation"]
    for rec in portfolio_hits
}

with open(STATE_FILE, "w") as f:
    json.dump(current_state, f)

# =========================
# TOP CONVICTION
# =========================

top_trades = sorted(
    portfolio_hits,
    key=lambda x: x["score"],
    reverse=True
)[:5]

# =========================
# DATAFRAME
# =========================

df = pd.DataFrame(portfolio_hits)

# =========================
# GPT SUMMARY
# =========================

summary_prompt = f"""
Analyze today's GPW analyst recommendations.

Recommendations:

{df.to_string(index=False)}

Provide:
1. Market sentiment
2. Top conviction trades
3. Portfolio actions
4. Only changed recommendations
5. BUY / HOLD / REDUCE summary
"""

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "user",
            "content": summary_prompt
        }
    ]
)

ai_summary = completion.choices[0].message.content

# =========================
# BUILD EMAIL
# =========================

email_body = f"""
GPW DAILY ANALYSIS
Generated: {datetime.now()}

====================================
TOP CONVICTION TRADES
====================================

"""

for trade in top_trades:

    upside = round(
        (
            (trade["target_price"] - trade["current_price"])
            / trade["current_price"]
        ) * 100,
        2
    )

    email_body += f"""
{trade['company']}
Source: {trade['source']}
Signal: {trade['signal']}
Score: {trade['score']}/10
Recommendation: {trade['recommendation']}
Upside: {upside}%
"""

email_body += """

====================================
PORTFOLIO ACTIONS
====================================

"""

for rec in portfolio_hits:

    email_body += f"""
{rec['company']}
Source: {rec['source']}
Signal: {rec['signal']}
Score: {rec['score']}/10
Recommendation: {rec['recommendation']}
"""

email_body += """

====================================
CHANGED RECOMMENDATIONS
====================================

"""

if changes:

    for rec in changes:

        email_body += f"""
{rec['company']}
Source: {rec['source']}
NEW Recommendation: {rec['recommendation']}
Signal: {rec['signal']}
"""

else:
    email_body += "\nNo recommendation changes today.\n"

email_body += f"""

====================================
AI MARKET SUMMARY
====================================

{ai_summary}
"""

# =========================
# SEND EMAIL
# =========================

msg = MIMEMultipart()

msg["From"] = EMAIL_SENDER
msg["To"] = EMAIL_RECEIVER
msg["Subject"] = "GPW Daily Analyst Recommendations"

msg.attach(MIMEText(email_body, "plain"))

server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)

server.starttls()

if not EMAIL_PASSWORD:
    raise Exception("EMAIL_PASSWORD is empty")


server.login(
    EMAIL_SENDER,
    EMAIL_PASSWORD
)

server.send_message(msg)

server.quit()

print("Email sent successfully.")