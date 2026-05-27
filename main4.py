import json
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

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
STREFA_INWESTOROW_URL = (
    "https://strefainwestorow.pl/rekomendacje/lista-rekomendacji"
)
MAX_RECOMMENDATION_AGE_DAYS = 30

POLISH_MONTHS = {
    "sty": 1,
    "lut": 2,
    "mar": 3,
    "kwi": 4,
    "maj": 5,
    "cze": 6,
    "lip": 7,
    "sie": 8,
    "wrz": 9,
    "paź": 10,
    "paz": 10,
    "lis": 11,
    "gru": 12,
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "wrzesnia": 9,
    "października": 10,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}

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

# Alternate tickers used on some sites -> portfolio ticker
TICKER_ALIASES = {
    "MOC": "MOL",
    "1AT": "ATA",
    "OPN": "OPL",
    "RYVU": "RVU",
}

openai_client = OpenAI(api_key=OPENAI_API_KEY)


# =============================================================================
# Parsing and scoring
# =============================================================================

def parse_recommendation_date(date_str):
    text = (date_str or "").strip().lower()
    if not text:
        return None

    match = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        return datetime(year, month, day)

    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        return datetime(year, month, day)

    match = re.search(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", text)
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))
        month = POLISH_MONTHS.get(month_name)
        if month:
            return datetime(year, month, day)

    return None


def is_recent_recommendation(date_str, max_age_days=MAX_RECOMMENDATION_AGE_DAYS):
    parsed = parse_recommendation_date(date_str)
    if parsed is None:
        return False

    cutoff = datetime.now() - timedelta(days=max_age_days)
    return parsed.date() >= cutoff.date()


def clean_price(value):
    text = str(value).replace(" ", "").replace(",", ".")
    match = re.search(r"[\d.]+", text)
    if not match:
        return 0.0
    try:
        return float(match.group())
    except (ValueError, TypeError):
        return 0.0


def extract_ticker(company_name):
    match = re.search(r"\((.*?)\)", company_name)
    if match:
        return match.group(1).upper().strip()
    return company_name.upper().strip()


def resolve_canonical_ticker(company_name):
    ticker = extract_ticker(company_name)
    ticker = TICKER_ALIASES.get(ticker, ticker)

    if ticker in PORTFOLIO:
        return ticker

    normalized = normalize_name(company_name)
    for alias, port_ticker in PORTFOLIO_ALIASES.items():
        if alias in normalized:
            return port_ticker

    return None


def canonical_company_name(ticker):
    return f"{PORTFOLIO[ticker]} ({ticker})"


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
    elif "sprzedaj" in recommendation or "redukuj" in recommendation:
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
    ticker = resolve_canonical_ticker(company)
    rec = {
        "source": source,
        "company": company,
        "ticker": ticker,
        "recommendation": recommendation,
        "target_price": target_price,
        "current_price": current_price,
        "date": date,
    }
    rec["score"] = calculate_score(rec)
    rec["signal"] = trading_signal(rec["score"])
    rec["portfolio_match"] = ticker is not None
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
        if len(cols) < 7:
            continue

        try:
            date = cols[6].get_text(strip=True)
            if not is_recent_recommendation(date):
                continue

            recommendations.append(
                enrich_recommendation(
                    source="BiznesRadar",
                    company=cols[0].get_text(strip=True),
                    recommendation=cols[1].get_text(strip=True),
                    target_price=clean_price(cols[2].get_text(strip=True)),
                    current_price=clean_price(cols[3].get_text(strip=True)),
                    date=date,
                )
            )
        except Exception as e:
            print("BiznesRadar row parse error:", e)

    return recommendations


def scrape_strefa_inwestorow():
    response = requests.get(
        STREFA_INWESTOROW_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    recommendations = []
    for row in table.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        try:
            date = cols[7].get_text(strip=True)
            if not is_recent_recommendation(date):
                continue

            recommendations.append(
                enrich_recommendation(
                    source="Strefa Inwestorów",
                    company=cols[0].get_text(strip=True),
                    recommendation=cols[1].get_text(strip=True),
                    target_price=clean_price(cols[3].get_text(strip=True)),
                    current_price=clean_price(cols[2].get_text(strip=True)),
                    date=date,
                )
            )
        except Exception as e:
            print("Strefa Inwestorów row parse error:", e)

    return recommendations


# =============================================================================
# Analysis and reporting
# =============================================================================

def filter_portfolio_hits(recommendations):
    return [rec for rec in recommendations if rec["portfolio_match"]]


def merge_portfolio_hits(portfolio_hits):
    """Merge BiznesRadar + Strefa rows into one entry per portfolio ticker."""
    grouped = {}
    for rec in portfolio_hits:
        ticker = rec["ticker"]
        grouped.setdefault(ticker, []).append(rec)

    merged = []
    for ticker, entries in grouped.items():
        entries.sort(
            key=lambda r: parse_recommendation_date(r["date"]) or datetime.min,
            reverse=True,
        )

        best = max(entries, key=lambda r: r["score"])
        priced = next((e for e in entries if e["current_price"] > 0), entries[0])

        details = []
        seen = set()
        for entry in entries:
            key = (entry["source"], entry["recommendation"].lower(), entry["date"])
            if key in seen:
                continue
            seen.add(key)
            details.append(
                f"{entry['source']}: {entry['recommendation']} ({entry['date']})"
            )

        merged.append(
            {
                "source": ", ".join(sorted({e["source"] for e in entries})),
                "company": canonical_company_name(ticker),
                "ticker": ticker,
                "recommendation": best["recommendation"],
                "recommendation_details": details,
                "target_price": priced["target_price"],
                "current_price": priced["current_price"],
                "date": entries[0]["date"],
                "score": best["score"],
                "signal": trading_signal(best["score"]),
                "portfolio_match": True,
            }
        )

    return sorted(merged, key=lambda r: r["score"], reverse=True)


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


def get_top_trades(portfolio_hits, limit=10):
    return sorted(portfolio_hits, key=lambda x: x["score"], reverse=True)[:limit]


def generate_ai_summary(records, portfolio_only=False):
    df = pd.DataFrame(records)
    if portfolio_only:
        prompt = f"""
Analyze today's analyst recommendations for my GPW portfolio holdings only.

Recommendations:

{df.to_string(index=False)}

Provide:
1. Portfolio sentiment
2. Top conviction holdings
3. Actions to consider (buy/hold/reduce)
4. Notable changes between sources
5. BUY / HOLD / REDUCE summary for my portfolio
"""
    else:
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
Date: {trade['date']}
Signal: {trade['signal']}
Score: {trade['score']}/10
Recommendation: {trade['recommendation']}
Upside: {upside_percent(trade)}%
"""


def format_portfolio_action(rec):
    block = f"""
{rec['company']}
Source: {rec['source']}
Date: {rec['date']}
Signal: {rec['signal']}
Score: {rec['score']}/10
Recommendation: {rec['recommendation']}
"""
    details = rec.get("recommendation_details") or []
    if len(details) > 1:
        block += "Details:\n"
        for line in details:
            block += f"  - {line}\n"
    return block


def format_change(rec):
    return f"""
{rec['company']}
Source: {rec['source']}
Date: {rec['date']}
NEW Recommendation: {rec['recommendation']}
Signal: {rec['signal']}
"""


def build_email_body(
    top_trades,
    portfolio_hits,
    changes,
    ai_summary,
    portfolio_top_trades,
    portfolio_ai_summary,
):
    body = f"""GPW DAILY ANALYSIS
Generated: {datetime.now()}

====================================
TOP CONVICTION TRADES (ALL)
====================================
"""
    for trade in top_trades:
        body += format_trade_section(trade)

    body += f"""
====================================
AI MARKET SUMMARY (ALL)
====================================

{ai_summary}

====================================
TOP PORTFOLIO TRADES
====================================
"""
    for trade in portfolio_top_trades:
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
AI PORTFOLIO SUMMARY
====================================

{portfolio_ai_summary}
"""
    return body


def send_email(subject, body):
    if not EMAIL_PASSWORD:
        raise ValueError("EMAIL_PASSWORD is empty")

   # List of recipients
    recipients = [
       EMAIL_RECEIVER,
        "grzegorz.ras@onet.eu",
        "Sebastian.ozdoba@gmail.com"
    ]

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(recipients)
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

    biznesradar = scrape_biznesradar()
    strefa = scrape_strefa_inwestorow()
    recommendations = biznesradar + strefa
    print(
        f"Scraped {len(biznesradar)} from BiznesRadar, "
        f"{len(strefa)} from Strefa Inwestorów ({len(recommendations)} total)"
    )

    portfolio_hits = merge_portfolio_hits(filter_portfolio_hits(recommendations))
    print_portfolio_matches(portfolio_hits)

    changes = detect_changes(portfolio_hits, previous_state)
    save_current_state(portfolio_hits)

    top_trades = get_top_trades(recommendations)
    ai_summary = generate_ai_summary(recommendations)

    portfolio_top_trades = get_top_trades(portfolio_hits)
    portfolio_ai_summary = generate_ai_summary(portfolio_hits, portfolio_only=True)

    email_body = build_email_body(
        top_trades,
        portfolio_hits,
        changes,
        ai_summary,
        portfolio_top_trades,
        portfolio_ai_summary,
    )
    send_email("GPW Daily Analyst Recommendations", email_body)
    print("Email sent successfully.")


if __name__ == "__main__":
    main()
