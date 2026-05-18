import json
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# =============================================================================
# Configuration
# =============================================================================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_SENDER = os.getenv("GMAIL_EMAIL")
EMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_TO")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
STATE_FILE = "previous_recommendations.json"

BIZNESRADAR_URL = "https://www.biznesradar.pl/rekomendacje/"
MBANK_URL = "https://serwis-informacyjny.mbank.pl/rekomendacje"

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

openai_client = OpenAI(api_key=OPENAI_API_KEY)


# =============================================================================
# Parsing and scoring
# =============================================================================

def clean_price(value):
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
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

    for suffix in (
        " SPOLKA AKCYJNA",
        " SPÓŁKA AKCYJNA",
        " SA",
        " S A",
        " NV",
        " N V",
        " PLC",
    ):
        normalized = normalized.replace(suffix, "")

    return " ".join(normalized.split())


def is_portfolio_match(company_name):
    normalized = normalize_name(company_name)
    return any(alias in normalized for alias in PORTFOLIO_ALIASES)


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

    if rec["current_price"] > 0:
        upside = (
            (rec["target_price"] - rec["current_price"]) / rec["current_price"]
        ) * 100
        if upside > 25:
            score += 2
        elif upside > 10:
            score += 1

    return max(1, min(score, 10))


def trading_signal(score):
    if score >= 8:
        return "BUY"
    if score >= 5:
        return "HOLD"
    return "REDUCE"


def upside_percent(rec):
    if rec["current_price"] <= 0:
        return 0.0
    return round(
        (rec["target_price"] - rec["current_price"]) / rec["current_price"] * 100,
        2,
    )


def enrich_recommendation(source, company, recommendation, target_price, current_price, date):
    rec = {
        "source": source,
        "company": company,
        "recommendation": recommendation,
        "target_price": target_price,
        "current_price": current_price,
        "date": date,
    }
    rec["score"] = calculate_score(rec)
    rec["signal"] = trading_signal(rec["score"])
    rec["portfolio_match"] = is_portfolio_match(company)
    return rec


# =============================================================================
# State persistence
# =============================================================================

def load_previous_state(path=STATE_FILE):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_current_state(portfolio_hits, path=STATE_FILE):
    state = {rec["company"]: rec["recommendation"] for rec in portfolio_hits}
    with open(path, "w") as f:
        json.dump(state, f)
    return state


# =============================================================================
# Scrapers
# =============================================================================

def scrape_biznesradar():
    response = requests.get(
        BIZNESRADAR_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    recommendations = []
    for row in table.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        try:
            recommendations.append(
                enrich_recommendation(
                    source="BiznesRadar",
                    company=cols[0].get_text(strip=True),
                    recommendation=cols[1].get_text(strip=True),
                    target_price=clean_price(cols[2].get_text(strip=True)),
                    current_price=clean_price(cols[3].get_text(strip=True)),
                    date=cols[5].get_text(strip=True),
                )
            )
        except Exception as e:
            print("BiznesRadar row parse error:", e)

    return recommendations


def scrape_mbank():
    recommendations = []

    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )

        try:
            driver.get(MBANK_URL)
            time.sleep(5)

            for row in driver.find_elements(By.TAG_NAME, "tr"):
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 5:
                    continue

                try:
                    recommendations.append(
                        enrich_recommendation(
                            source="mBank",
                            company=cols[0].text.strip(),
                            recommendation=cols[1].text.strip(),
                            target_price=clean_price(cols[2].text.strip()),
                            current_price=clean_price(cols[3].text.strip()),
                            date=cols[4].text.strip(),
                        )
                    )
                except Exception as e:
                    print("mBank row parse error:", e)
        finally:
            driver.quit()

    except Exception as e:
        print("mBank selenium error:", e)

    return recommendations


# =============================================================================
# Analysis and reporting
# =============================================================================

def filter_portfolio_hits(recommendations):
    return [rec for rec in recommendations if rec["portfolio_match"]]


def print_portfolio_matches(portfolio_hits):
    print("\n====================")
    print("PORTFOLIO MATCHES")
    print("====================")
    for rec in portfolio_hits:
        print(rec["source"], "|", rec["company"], "|", rec["recommendation"])


def detect_changes(portfolio_hits, previous_state):
    changes = []
    for rec in portfolio_hits:
        old = previous_state.get(rec["company"])
        if old != rec["recommendation"]:
            changes.append(rec)
    return changes


def get_top_trades(portfolio_hits, limit=5):
    return sorted(portfolio_hits, key=lambda x: x["score"], reverse=True)[:limit]


def generate_ai_summary(portfolio_hits):
    df = pd.DataFrame(portfolio_hits)
    prompt = f"""
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

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


def format_trade_section(trade):
    return f"""
{trade['company']}
Source: {trade['source']}
Signal: {trade['signal']}
Score: {trade['score']}/10
Recommendation: {trade['recommendation']}
Upside: {upside_percent(trade)}%
"""


def format_portfolio_action(rec):
    return f"""
{rec['company']}
Source: {rec['source']}
Signal: {rec['signal']}
Score: {rec['score']}/10
Recommendation: {rec['recommendation']}
"""


def format_change(rec):
    return f"""
{rec['company']}
Source: {rec['source']}
NEW Recommendation: {rec['recommendation']}
Signal: {rec['signal']}
"""


def build_email_body(top_trades, portfolio_hits, changes, ai_summary):
    body = f"""GPW DAILY ANALYSIS
Generated: {datetime.now()}

====================================
TOP CONVICTION TRADES
====================================
"""
    for trade in top_trades:
        body += format_trade_section(trade)

    body += """
====================================
PORTFOLIO ACTIONS
====================================
"""
    for rec in portfolio_hits:
        body += format_portfolio_action(rec)

    body += """
====================================
CHANGED RECOMMENDATIONS
====================================
"""
    if changes:
        for rec in changes:
            body += format_change(rec)
    else:
        body += "\nNo recommendation changes today.\n"

    body += f"""
====================================
AI MARKET SUMMARY
====================================

{ai_summary}
"""
    return body


def send_email(subject, body):
    if not EMAIL_PASSWORD:
        raise ValueError("EMAIL_PASSWORD is empty")

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)


# =============================================================================
# Main
# =============================================================================

def main():
    previous_state = load_previous_state()

    recommendations = scrape_biznesradar()
    recommendations.extend(scrape_mbank())
    print("Total recommendations:", len(recommendations)))

    portfolio_hits = filter_portfolio_hits(recommendations)
    print_portfolio_matches(portfolio_hits)

    changes = detect_changes(portfolio_hits, previous_state)
    save_current_state(portfolio_hits)

    top_trades = get_top_trades(portfolio_hits)
    ai_summary = generate_ai_summary(portfolio_hits)

    email_body = build_email_body(top_trades, portfolio_hits, changes, ai_summary)
    send_email("GPW Daily Analyst Recommendations", email_body)
    print("Email sent successfully.")


if __name__ == "__main__":
    main()
