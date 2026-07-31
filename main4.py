import html
import json
import os
import random
import re
import smtplib
import time
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from xml.etree import ElementTree as ET

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
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
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "previous_recommendations.json")
PORTFOLIO_FILE = os.path.join(SCRIPT_DIR, "portfolio.json")

BIZNESRADAR_URL = "https://www.biznesradar.pl/rekomendacje/"
STREFA_INWESTOROW_URL = (
    "https://strefainwestorow.pl/rekomendacje/lista-rekomendacji"
)
BANKIER_URL = "https://www.bankier.pl/gielda/rekomendacje"
INVESTING_COM_BASE = "https://www.investing.com"
INVESTING_COM_SLUGS_FILE = os.path.join(SCRIPT_DIR, "investing_slugs.json")
INVESTING_COM_REQUEST_DELAY_SEC = 2
FOOL_TOP_STOCKS_URL = "https://www.fool.com/investing/top-stocks-to-buy-and-hold/"
FOOL_HOME_URL = "https://www.fool.com/"
FOOL_BASE_URL = "https://www.fool.com"
SOURCE_URLS = {
    "BiznesRadar": BIZNESRADAR_URL,
    "Strefa Inwestorów": STREFA_INWESTOROW_URL,
    "Bankier": BANKIER_URL,
    "Investing.com": INVESTING_COM_BASE,
    "Motley Fool": FOOL_TOP_STOCKS_URL,
    "Yahoo Finance": "https://finance.yahoo.com",
}
ALWAYS_INCLUDE_PORTFOLIO_TICKERS = ["V"]
MAX_RECOMMENDATION_AGE_DAYS = 30

REDDIT_SUBREDDITS = ["investing", "stocks", "Investments"]
REDDIT_USER_AGENT = "market-agent/1.0 (GPW daily email digest)"
REDDIT_RSS_DELAY_SEC = 12
REDDIT_POST_LIMIT = 50
REDDIT_COMMENT_POST_LIMIT = 8
REDDIT_COMMENT_LIMIT = 80
STREET_TALK_TICKER_LIMIT = 10
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

TICKER_STOPWORDS = {
    "A", "AI", "ALL", "AM", "AND", "ANY", "ARE", "AS", "ATH", "ATM", "BE", "BUT",
    "CEO", "CFO", "CPI", "DD", "DR", "EPS", "ESG", "ETF", "EU", "EOD", "EUR",
    "FDA", "FED", "FOMC", "FOR", "GBP", "GDP", "HR", "HSA", "INC", "IRA", "IPO",
    "IT", "IV", "LLC", "LTD", "MACD", "MOM", "NOT", "NYSE", "OP", "OTM", "PC",
    "PE", "PM", "ROTH", "RSI", "SEC", "TA", "TL", "TV", "UK", "USA", "USD", "WSB",
    "YOLO", "YOU", "THE", "OR", "TO", "IN", "ON", "AT", "IS", "IF", "MY", "ME",
    "WE", "SO", "NO", "UP", "OUT", "NEW", "OLD", "BIG", "LOW", "HIGH", "TOP",
    "BUY", "SELL", "HOLD", "PUT", "CALL", "FUN", "RUN", "GET", "GOT", "HAS",
    "HAD", "CAN", "MAY", "DAY", "WAS", "ONE", "TWO", "NOW", "JUST", "ONLY",
    "REAL", "TRUE", "GOOD", "BAD", "LONG", "SHORT", "CASH", "FUND", "RATE",
    "YEAR", "WEEK", "MONTH", "DAILY", "NEWS", "EDIT", "LINK", "POST", "READ",
}

TICKER_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
TICKER_BRACKET_RE = re.compile(r"\[([A-Z]{1,5})\]")
FOOL_TICKER_RE = re.compile(
    r"(?:NASDAQ|NYSE|NYSEMKT|SNPINDEX)\s*:\s*([A-Z]{1,5})",
    re.IGNORECASE,
)
FOOL_QUOTE_PATH_RE = re.compile(
    r"/quote/(?:nasdaq|nyse|nysemkt|amex)/([^/]+)/?",
    re.IGNORECASE,
)
INVESTING_UPDATED_RE = re.compile(
    r"Updated\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)
STREET_TALK_COMPANY_ALIASES = {
    "ALPHABET": "GOOGL",
    "GOOGLE": "GOOGL",
    "AMAZON": "AMZN",
    "APPLE": "AAPL",
    "BERKSHIRE HATHAWAY": "BRKB",
    "CROWDSTRIKE": "CRWD",
    "INTEL": "INTC",
    "MICRON": "MU",
    "MICROSOFT": "MSFT",
    "NVIDIA": "NVDA",
    "ORACLE": "ORCL",
    "SANDISK": "SNDK",
    "SHOPIFY": "SHOP",
    "TESLA": "TSLA",
    "WALT DISNEY": "DIS",
    "DISNEY": "DIS",
}

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
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

def load_portfolio(path=PORTFOLIO_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["portfolio"], data["aliases"]
    except FileNotFoundError:
        print(f"Portfolio file not found: {path}")
        return {}, {}
    except json.JSONDecodeError as exc:
        print(f"Portfolio JSON invalid ({path}): {exc}")
        return {}, {}


def load_investing_slugs(path=INVESTING_COM_SLUGS_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Investing.com slugs file not found: {path}")
        return {}
    except json.JSONDecodeError as exc:
        print(f"Investing.com slugs JSON invalid ({path}): {exc}")
        return {}


PORTFOLIO, PORTFOLIO_ALIASES = load_portfolio()
INVESTING_COM_SLUGS = load_investing_slugs()

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

    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        return datetime(year, month, day)

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


def format_recommendation_date(date_str):
    parsed = parse_recommendation_date(date_str)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return (date_str or "").strip()


def recommendation_sort_date(rec):
    date_str = rec.get("date") or ""
    parsed_dates = [
        parse_recommendation_date(part.strip())
        for part in re.split(r"\s*·\s*", date_str)
        if part.strip()
    ]
    valid = [d for d in parsed_dates if d]
    if valid:
        return max(valid)
    return parse_recommendation_date(date_str) or datetime.min


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

    for port_ticker, port_name in PORTFOLIO.items():
        if normalize_name(port_name) in normalized or normalize_name(port_name) == normalize_name(ticker):
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

    if "kupuj" in recommendation or "buy" in recommendation or "strong buy" in recommendation:
        score += 3
    elif "akumuluj" in recommendation or "overweight" in recommendation:
        score += 2
    elif "trzymaj" in recommendation or "hold" in recommendation:
        score += 0
    elif "neutral" in recommendation:
        score -= 1
    elif (
        "sprzedaj" in recommendation
        or "redukuj" in recommendation
        or "sell" in recommendation
        or "underweight" in recommendation
    ):
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


def enrich_recommendation(
    source,
    company,
    recommendation,
    target_price,
    current_price,
    date,
    source_url=None,
):
    ticker = resolve_canonical_ticker(company)
    url = source_url or SOURCE_URLS.get(source, "")
    rec = {
        "source": source,
        "source_url": url,
        "source_links": [{"source": source, "url": url}] if url else [{"source": source, "url": ""}],
        "company": company,
        "ticker": ticker,
        "recommendation": recommendation,
        "target_price": target_price,
        "current_price": current_price,
        "date": format_recommendation_date(date),
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
    state = {portfolio_state_key(rec): rec["recommendation"] for rec in portfolio_hits}
    with open(path, "w") as f:
        json.dump(state, f)
    return state


# =============================================================================
# Scrapers
# =============================================================================

def _absolute_url(base, href):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"{base.rstrip('/')}/{href.lstrip('/')}"


def _row_source_url(row, base_url, fallback_url):
    for cell in row.find_all("td"):
        link = cell.find("a", href=True)
        if link and link["href"] not in ("#", ""):
            return _absolute_url(base_url, link["href"])
    return fallback_url


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
                    source_url=_row_source_url(row, "https://www.biznesradar.pl", BIZNESRADAR_URL),
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
                    source_url=_row_source_url(
                        row,
                        "https://strefainwestorow.pl",
                        STREFA_INWESTOROW_URL,
                    ),
                )
            )
        except Exception as e:
            print("Strefa Inwestorów row parse error:", e)

    return recommendations


def scrape_bankier():
    recommendations = []
    page = 1

    while page <= 20:
        url = BANKIER_URL if page == 1 else f"{BANKIER_URL}?strona={page}"
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        if not table:
            break

        recent_on_page = 0
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 8:
                continue

            try:
                date = cols[0].get_text(strip=True)
                if not is_recent_recommendation(date):
                    continue

                company = cols[1].get_text(strip=True)
                recent_on_page += 1
                recommendations.append(
                    enrich_recommendation(
                        source="Bankier",
                        company=company,
                        recommendation=cols[2].get_text(strip=True),
                        target_price=clean_price(cols[4].get_text(strip=True)),
                        current_price=clean_price(cols[3].get_text(strip=True)),
                        date=date,
                        source_url=_row_source_url(
                            row,
                            "https://www.bankier.pl",
                            url,
                        ),
                    )
                )
            except Exception as e:
                print("Bankier row parse error:", e)

        if recent_on_page == 0:
            break
        page += 1

    return recommendations


def _browser_headers(referer=None):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _investing_session():
    session = cffi_requests.Session()
    session.get(
        f"{INVESTING_COM_BASE}/equities/poland",
        headers=_browser_headers(),
        impersonate="chrome120",
        timeout=30,
    )
    return session


def _parse_investing_faq_page(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "FAQPage":
            continue

        rating = None
        target_price = 0.0
        for entity in data.get("mainEntity", []):
            question = entity.get("name", "")
            answer = entity.get("acceptedAnswer", {}).get("text", "")
            if "buy, sell, or hold" in question.lower():
                match = re.search(r'consensus rating for .+ is "([^"]+)"', answer, re.I)
                if match:
                    rating = match.group(1)
            if "price target" in question.lower():
                for pattern in (
                    r"average price target for .+ is ([\d,.]+)",
                    r"price target for .+ is ([\d,.]+)",
                    r"average target price is ([\d,.]+)",
                    r"12-month price target is ([\d,.]+)",
                    r"price target of ([\d,.]+)",
                ):
                    match = re.search(pattern, answer, re.I)
                    if match:
                        target_price = clean_price(match.group(1))
                        break
        if rating:
            return rating, target_price
    return None, 0.0


def _parse_investing_current_price(soup):
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(\d+[,.]\d{2,})\s*PLN", text)
    if match:
        return clean_price(match.group(1))
    return 0.0


def _investing_consensus_to_recommendation(rating):
    normalized = (rating or "").strip().lower()
    mapping = {
        "strong buy": "Strong Buy",
        "buy": "Buy",
        "hold": "Hold",
        "neutral": "Neutral",
        "sell": "Sell",
        "strong sell": "Strong Sell",
        "outperform": "Buy",
        "underperform": "Sell",
    }
    return mapping.get(normalized, rating or "Neutral")


def scrape_investing_com():
    recommendations = []
    session = _investing_session()
    headers = _browser_headers(f"{INVESTING_COM_BASE}/equities/poland")
    consensus_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for index, (ticker, slug) in enumerate(INVESTING_COM_SLUGS.items()):
        if index > 0:
            time.sleep(INVESTING_COM_REQUEST_DELAY_SEC)

        consensus_url = f"{INVESTING_COM_BASE}/equities/{slug}-consensus-estimates"
        try:
            response = session.get(
                consensus_url,
                headers=headers,
                impersonate="chrome120",
                timeout=30,
            )
            if not response.ok:
                if response.status_code != 404:
                    print(f"Investing.com consensus failed for {ticker}: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            rating, target_price = _parse_investing_faq_page(soup)
            if not rating:
                continue

            equity_url = f"{INVESTING_COM_BASE}/equities/{slug}"
            equity_response = session.get(
                equity_url,
                headers=headers,
                impersonate="chrome120",
                timeout=30,
            )
            current_price = 0.0
            company_name = f"{PORTFOLIO.get(ticker, ticker)} ({ticker})"
            if equity_response.ok:
                equity_soup = BeautifulSoup(equity_response.text, "html.parser")
                current_price = _parse_investing_current_price(equity_soup)
                title = equity_soup.find("h1")
                if title:
                    company_name = title.get_text(" ", strip=True)

            recommendations.append(
                enrich_recommendation(
                    source="Investing.com",
                    company=company_name,
                    recommendation=_investing_consensus_to_recommendation(rating),
                    target_price=target_price,
                    current_price=current_price,
                    date=consensus_date,
                    source_url=consensus_url,
                )
            )
        except Exception as exc:
            print(f"Investing.com row parse error for {ticker}:", exc)

    return recommendations


def _parse_fool_updated_date(soup):
    match = INVESTING_UPDATED_RE.search(soup.get_text(" ", strip=True))
    if match:
        raw_date = match.group(1)
        for fmt in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return format_recommendation_date(raw_date)
    return datetime.now().strftime("%Y-%m-%d")


def _normalize_fool_ticker(raw_ticker):
    ticker = (raw_ticker or "").upper().replace(".", "")
    aliases = {
        "BRK-B": "BRKB",
        "BRK-A": "BRKA",
        "GOOG": "GOOGL",
    }
    return aliases.get(ticker, ticker)


def scrape_motley_fool_top_stocks():
    response = requests.get(
        FOOL_TOP_STOCKS_URL,
        headers=_browser_headers(),
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    updated_date = _parse_fool_updated_date(soup)
    recommendations = []
    seen = set()

    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [cell.get_text(" ", strip=True) for cell in header_row.find_all(["th", "td"])]
        if "Name and ticker" not in " ".join(headers):
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            row_text = row.get_text(" ", strip=True)
            ticker_match = FOOL_TICKER_RE.search(row_text)
            link = row.find("a", href=True)
            if link:
                path_match = FOOL_QUOTE_PATH_RE.search(link["href"])
                if path_match:
                    ticker = _normalize_fool_ticker(path_match.group(1))
                elif ticker_match:
                    ticker = _normalize_fool_ticker(ticker_match.group(1))
                else:
                    continue
            elif ticker_match:
                ticker = _normalize_fool_ticker(ticker_match.group(1))
            else:
                continue

            if ticker in seen or ticker in TICKER_STOPWORDS:
                continue

            company_cell = cells[0].get_text(" ", strip=True)
            company_name = company_cell.split("(")[0].strip(" ,") or ticker
            if f"({ticker})" not in company_name.upper():
                company_name = f"{company_name} ({ticker})"

            current_price = 0.0
            source_url = FOOL_TOP_STOCKS_URL
            if len(cells) > 1:
                current_price = clean_price(cells[1].get_text(" ", strip=True))
            if link and link.get("href"):
                source_url = _absolute_url(FOOL_BASE_URL, link["href"])

            seen.add(ticker)
            recommendations.append(
                enrich_recommendation(
                    source="Motley Fool",
                    company=company_name,
                    recommendation="Buy and Hold",
                    target_price=0.0,
                    current_price=current_price,
                    date=updated_date,
                    source_url=source_url,
                )
            )

    if recommendations:
        return recommendations

    for match in FOOL_TICKER_RE.findall(soup.get_text(" ", strip=True)):
        ticker = _normalize_fool_ticker(match)
        if ticker in seen or ticker in TICKER_STOPWORDS:
            continue
        seen.add(ticker)
        recommendations.append(
            enrich_recommendation(
                source="Motley Fool",
                company=f"{ticker} ({ticker})",
                recommendation="Buy and Hold",
                target_price=0.0,
                current_price=0.0,
                date=updated_date,
                source_url=FOOL_TOP_STOCKS_URL,
            )
        )

    return recommendations[:10]


def scrape_motley_fool_trending():
    response = requests.get(
        FOOL_HOME_URL,
        headers=_browser_headers(),
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    posts = []
    seen_urls = set()

    for rank, link in enumerate(soup.find_all("a", href=True)):
        href = link["href"]
        if "/investing/20" not in href:
            continue
        if href in seen_urls:
            continue

        title = link.get_text(" ", strip=True)
        if len(title) < 25:
            continue

        url = href if href.startswith("http") else f"https://www.fool.com{href}"
        seen_urls.add(href)
        posts.append(
            {
                "subreddit": "Motley Fool",
                "source": "Motley Fool",
                "title": title,
                "selftext": "",
                "url": url,
                "num_comments": 0,
                "score": max(30 - len(posts), 1),
                "rank": len(posts),
                "is_discussion": False,
                "comments": [],
            }
        )
        if len(posts) >= 20:
            break

    return posts


# =============================================================================
# Reddit street talk
# =============================================================================

def _reddit_http_headers(token=None):
    headers = {"User-Agent": REDDIT_USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_reddit_access_token():
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None

    response = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers=_reddit_http_headers(),
        timeout=30,
    )
    if not response.ok:
        print("Reddit OAuth failed:", response.status_code, response.text[:200])
        return None

    return response.json().get("access_token")


def _normalize_reddit_post(subreddit, post_data, rank):
    created = datetime.utcfromtimestamp(post_data.get("created_utc", 0))
    return {
        "subreddit": subreddit,
        "title": post_data.get("title", ""),
        "selftext": post_data.get("selftext", ""),
        "url": f"https://www.reddit.com{post_data.get('permalink', '')}",
        "num_comments": int(post_data.get("num_comments", 0) or 0),
        "score": int(post_data.get("score", 0) or 0),
        "created_utc": created,
        "rank": rank,
        "is_discussion": _is_discussion_thread(post_data.get("title", "")),
    }


def _is_discussion_thread(title):
    lower = (title or "").lower()
    return "daily" in lower and ("discussion" in lower or "thread" in lower)


def fetch_subreddit_posts_api(subreddit, token, limit=REDDIT_POST_LIMIT):
    response = requests.get(
        f"https://oauth.reddit.com/r/{subreddit}/hot",
        params={"limit": limit},
        headers=_reddit_http_headers(token),
        timeout=30,
    )
    if not response.ok:
        print(f"Reddit API failed for r/{subreddit}:", response.status_code)
        return []

    posts = []
    for rank, child in enumerate(response.json().get("data", {}).get("children", [])):
        post_data = child.get("data", {})
        if post_data.get("stickied") and not _is_discussion_thread(post_data.get("title", "")):
            continue
        posts.append(_normalize_reddit_post(subreddit, post_data, rank))
    return posts


def fetch_subreddit_posts_rss(subreddit, limit=REDDIT_POST_LIMIT):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(REDDIT_RSS_DELAY_SEC * attempt)
        response = requests.get(
            f"https://www.reddit.com/r/{subreddit}/hot/.rss",
            headers=headers,
            timeout=30,
        )
        if response.ok and response.text.strip().startswith("<?xml"):
            break
        if response.status_code != 429:
            break

    if not response or not response.ok or not response.text.strip().startswith("<?xml"):
        print(f"Reddit RSS failed for r/{subreddit}:", getattr(response, "status_code", "no response"))
        return []

    root = ET.fromstring(response.content)
    posts = []
    for rank, entry in enumerate(root.findall("atom:entry", ATOM_NS)):
        if rank >= limit:
            break

        title = entry.findtext("atom:title", default="", namespaces=ATOM_NS)
        link = ""
        for link_el in entry.findall("atom:link", ATOM_NS):
            if link_el.attrib.get("rel") == "alternate":
                link = link_el.attrib.get("href", "")
                break
        content = entry.findtext("atom:content", default="", namespaces=ATOM_NS)
        updated = entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
        created = parse_recommendation_date(updated[:10]) or datetime.utcnow()

        posts.append(
            {
                "subreddit": subreddit,
                "title": title,
                "selftext": BeautifulSoup(content, "html.parser").get_text(" ", strip=True),
                "url": link,
                "num_comments": 0,
                "score": max(limit - rank, 1),
                "created_utc": created,
                "rank": rank,
                "is_discussion": _is_discussion_thread(title),
            }
        )
    return posts


def scrape_reddit_investment_subs(token=None):
    if token is None:
        token = get_reddit_access_token()
    posts = []

    for index, subreddit in enumerate(REDDIT_SUBREDDITS):
        if index > 0 and not token:
            time.sleep(REDDIT_RSS_DELAY_SEC)

        if token:
            sub_posts = fetch_subreddit_posts_api(subreddit, token)
        else:
            sub_posts = fetch_subreddit_posts_rss(subreddit)

        print(f"Reddit r/{subreddit}: {len(sub_posts)} posts")
        posts.extend(sub_posts)

    return posts


def extract_tickers_from_text(text):
    if not text:
        return set()

    tickers = set()
    upper_text = text.upper()
    for match in TICKER_CASHTAG_RE.findall(upper_text):
        if match not in TICKER_STOPWORDS:
            tickers.add(match)
    for match in TICKER_BRACKET_RE.findall(upper_text):
        if match not in TICKER_STOPWORDS:
            tickers.add(match)
    for match in FOOL_TICKER_RE.findall(text):
        ticker = _normalize_fool_ticker(match)
        if ticker not in TICKER_STOPWORDS:
            tickers.add(ticker)

    normalized_text = normalize_name(text)
    for alias, ticker in STREET_TALK_COMPANY_ALIASES.items():
        if alias in normalized_text:
            tickers.add(ticker)

    return tickers


def fetch_post_comments(post, token=None):
    permalink = post.get("url", "")
    if not permalink or "reddit.com" not in permalink:
        return []

    json_url = permalink.rstrip("/") + ".json"
    headers = _reddit_http_headers(token)
    if not token:
        headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    try:
        response = requests.get(
            json_url,
            headers=headers,
            timeout=30,
            params={"limit": REDDIT_COMMENT_LIMIT},
        )
        if not response.ok:
            return []
        payload = response.json()
        if len(payload) < 2:
            return []
        post_data = payload[0]["data"]["children"][0]["data"]
        post["num_comments"] = int(post_data.get("num_comments", post.get("num_comments", 0)) or 0)
        post["score"] = int(post_data.get("score", post.get("score", 0)) or 0)
        return _flatten_reddit_comments(payload[1]["data"]["children"])
    except (ValueError, KeyError, IndexError, requests.RequestException) as exc:
        print("Reddit comment fetch error:", exc)
        return []


def _flatten_reddit_comments(children, limit=REDDIT_COMMENT_LIMIT):
    comments = []
    for child in children:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        body = data.get("body", "")
        if body and body not in ("[deleted]", "[removed]"):
            comments.append(body)
        if len(comments) >= limit:
            break
        replies = data.get("replies")
        if isinstance(replies, dict):
            comments.extend(
                _flatten_reddit_comments(
                    replies.get("data", {}).get("children", []),
                    limit=limit - len(comments),
                )
            )
    return comments[:limit]


def _post_engagement_weight(post):
    comments = post.get("num_comments", 0)
    score = post.get("score", 0)
    rank = post.get("rank", 0)
    rank_weight = max(REDDIT_POST_LIMIT - rank, 1)
    discussion_bonus = 3 if post.get("is_discussion") else 1
    return (comments * 2) + score + (rank_weight * discussion_bonus)


def collect_reddit_commentary(posts, token=None):
    commentary_posts = sorted(posts, key=_post_engagement_weight, reverse=True)
    selected = []
    seen_urls = set()

    for post in commentary_posts:
        if post["url"] in seen_urls:
            continue
        if post.get("is_discussion") or len(selected) < REDDIT_COMMENT_POST_LIMIT:
            selected.append(post)
            seen_urls.add(post["url"])
        if len(selected) >= REDDIT_COMMENT_POST_LIMIT:
            break

    for index, post in enumerate(selected):
        if index > 0:
            time.sleep(2 if token else 4)
        post["comments"] = fetch_post_comments(post, token=token)

    return selected


def rank_hot_tickers(posts):
    ticker_stats = defaultdict(
        lambda: {
            "mentions": 0,
            "engagement": 0.0,
            "subreddits": set(),
            "sample_posts": [],
        }
    )

    for post in posts:
        text_parts = [post.get("title", ""), post.get("selftext", "")]
        for comment in post.get("comments", []):
            text_parts.append(comment)
        text = "\n".join(text_parts)
        tickers = extract_tickers_from_text(text)
        weight = _post_engagement_weight(post)
        source_label = post.get("source") or post.get("subreddit") or "Unknown"
        for ticker in tickers:
            stats = ticker_stats[ticker]
            stats["mentions"] += 1
            stats["engagement"] += weight
            stats["subreddits"].add(source_label)
            if len(stats["sample_posts"]) < 3:
                stats["sample_posts"].append(
                    {
                        "title": post["title"],
                        "subreddit": source_label,
                        "url": post["url"],
                        "num_comments": post.get("num_comments", 0),
                    }
                )

    ranked = []
    for ticker, stats in ticker_stats.items():
        ranked.append(
            {
                "ticker": ticker,
                "mentions": stats["mentions"],
                "engagement": round(stats["engagement"], 1),
                "subreddits": sorted(stats["subreddits"]),
                "sample_posts": stats["sample_posts"],
            }
        )

    ranked.sort(key=lambda item: (item["engagement"], item["mentions"]), reverse=True)
    return ranked[:STREET_TALK_TICKER_LIMIT]


def fetch_ticker_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        history = stock.history(period="6mo")
        price_change_6m = None
        if not history.empty:
            first_close = float(history["Close"].iloc[0])
            last_close = float(history["Close"].iloc[-1])
            if first_close > 0:
                price_change_6m = round((last_close - first_close) / first_close * 100, 2)

        news_items = []
        for item in (stock.news or [])[:4]:
            title = item.get("title") or item.get("content", {}).get("title")
            if title:
                news_items.append(title)

        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        target_price = info.get("targetMeanPrice") or info.get("targetMedianPrice")
        upside = None
        if current_price and target_price and current_price > 0:
            upside = round((target_price - current_price) / current_price * 100, 2)

        return {
            "ticker": ticker,
            "name": info.get("shortName") or info.get("longName") or ticker,
            "sector": info.get("sector") or "—",
            "price": current_price,
            "target_price": target_price,
            "upside_pct": upside,
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "analyst_recommendation": info.get("recommendationKey"),
            "price_change_6m_pct": price_change_6m,
            "news": news_items,
            "yahoo_url": f"https://finance.yahoo.com/quote/{ticker}",
        }
    except Exception as exc:
        print(f"Yahoo Finance lookup failed for {ticker}:", exc)
        return {
            "ticker": ticker,
            "name": ticker,
            "sector": "—",
            "price": None,
            "target_price": None,
            "upside_pct": None,
            "pe_ratio": None,
            "analyst_recommendation": None,
            "price_change_6m_pct": None,
            "news": [],
            "yahoo_url": f"https://finance.yahoo.com/quote/{ticker}",
        }


def build_street_talk_dataset(reddit_posts, fool_posts=None, token=None):
    enriched_posts = collect_reddit_commentary(reddit_posts, token=token)
    comments_by_url = {post["url"]: post.get("comments", []) for post in enriched_posts}
    for post in reddit_posts:
        post["comments"] = comments_by_url.get(post["url"], [])

    all_posts = list(reddit_posts) + list(fool_posts or [])
    hot_tickers = rank_hot_tickers(all_posts)
    dataset = []

    for item in hot_tickers:
        finance = fetch_ticker_financials(item["ticker"])
        dataset.append({**item, "finance": finance})

    return dataset


def generate_street_talk_analysis(street_talk_data):
    if not street_talk_data:
        return "No street talk data available today."

    rows = []
    for item in street_talk_data:
        finance = item["finance"]
        sample_titles = "; ".join(post["title"] for post in item["sample_posts"][:2])
        rows.append(
            {
                "ticker": item["ticker"],
                "mentions": item["mentions"],
                "engagement": item["engagement"],
                "sources": ", ".join(item["subreddits"]),
                "sample_headlines": sample_titles,
                "name": finance.get("name"),
                "price": finance.get("price"),
                "target_price": finance.get("target_price"),
                "upside_pct": finance.get("upside_pct"),
                "pe_ratio": finance.get("pe_ratio"),
                "analyst_recommendation": finance.get("analyst_recommendation"),
                "price_change_6m_pct": finance.get("price_change_6m_pct"),
                "news": " | ".join(finance.get("news", [])[:3]),
            }
        )

    df = pd.DataFrame(rows)
    prompt = f"""
Analyze investment chatter from Reddit and The Motley Fool, cross-checked with Yahoo Finance data.

Sources: r/investing, r/stocks, r/Investments, fool.com trending headlines.
Use the table below. Treat social chatter as sentiment/rumor, not fact.

{df.to_string(index=False)}

Provide:
1. What the street is buzzing about (themes and narratives)
2. Risk flags (hype, crowded trades, weak fundamentals)
3. 3 bullet takeaways for a long-term investor

Be concise and skeptical of hype. Do not repeat the rumor vs fundamentals table.
"""

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


# =============================================================================
# Analysis and reporting
# =============================================================================

def filter_portfolio_hits(recommendations):
    return [rec for rec in recommendations if rec["portfolio_match"]]


YAHOO_RECOMMENDATION_LABELS = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "underperform": "Underperform",
    "sell": "Sell",
    "strong_sell": "Strong Sell",
    "none": "No rating",
}


def fetch_yahoo_analyst_recommendation(ticker):
    finance = fetch_ticker_financials(ticker)
    raw_rec = (finance.get("analyst_recommendation") or "hold").lower().replace(" ", "_")
    recommendation = YAHOO_RECOMMENDATION_LABELS.get(
        raw_rec,
        raw_rec.replace("_", " ").title(),
    )
    company = f"{finance.get('name', ticker)} ({ticker})"
    return enrich_recommendation(
        source="Yahoo Finance",
        company=company,
        recommendation=recommendation,
        target_price=float(finance.get("target_price") or 0),
        current_price=float(finance.get("price") or 0),
        date=datetime.now().strftime("%Y-%m-%d"),
        source_url=finance.get("yahoo_url") or f"https://finance.yahoo.com/quote/{ticker}",
    )


def ensure_extra_portfolio_recommendations(portfolio_hits):
    hits = list(portfolio_hits)
    present = {rec.get("ticker") for rec in hits}
    for ticker in ALWAYS_INCLUDE_PORTFOLIO_TICKERS:
        if ticker not in present:
            hits.append(fetch_yahoo_analyst_recommendation(ticker))
    return hits


def exclude_source(recommendations, source):
    return [rec for rec in recommendations if rec["source"] != source]


def build_investing_portfolio_hits(investing_recs):
    hits = filter_portfolio_hits(investing_recs)
    expanded = []
    for rec in dedupe_by_stock_and_source(hits):
        expanded.append(
            {
                **rec,
                "company": canonical_company_name(rec["ticker"]),
            }
        )
    return sort_by_recommendation_date(expanded)


def portfolio_state_key(rec):
    return f"{rec['ticker']}|{rec['source']}"


def expand_portfolio_by_venue(portfolio_hits):
    """One row per portfolio holding, merging identical recommendations across venues."""
    expanded = []
    for rec in dedupe_by_stock_and_source(portfolio_hits):
        expanded.append(
            {
                **rec,
                "company": canonical_company_name(rec["ticker"]),
            }
        )
    return sort_by_company_name(combine_identical_recommendations(expanded))


def combine_identical_recommendations(recommendations):
    """Merge rows for the same stock and target price into one row with all venues and dates."""
    groups = {}
    for rec in recommendations:
        key = (
            _stock_key(rec),
            round(rec["target_price"], 2),
            (rec["recommendation"] or "").strip().lower(),
        )
        groups.setdefault(key, []).append(rec)

    combined = []
    for group in groups.values():
        if len(group) == 1:
            combined.append(group[0])
            continue

        base = max(group, key=lambda r: (r["score"], recommendation_sort_date(r)))
        sources = []
        source_links = []
        dates = []
        seen_sources = set()
        for item in sorted(group, key=recommendation_sort_date, reverse=True):
            if item["source"] not in seen_sources:
                seen_sources.add(item["source"])
                sources.append(item["source"])
                source_links.append(
                    {
                        "source": item["source"],
                        "url": item.get("source_url") or SOURCE_URLS.get(item["source"], ""),
                    }
                )
            if item["date"] not in dates:
                dates.append(item["date"])

        merged = {**base}
        merged["source"] = " · ".join(sources)
        merged["source_links"] = source_links
        merged["source_url"] = source_links[0]["url"] if len(source_links) == 1 else ""
        merged["date"] = " · ".join(dates)
        combined.append(merged)

    return combined


def sort_by_recommendation_date(recommendations, reverse=True):
    return sorted(recommendations, key=recommendation_sort_date, reverse=reverse)


def sort_by_company_name(recommendations):
    return sorted(recommendations, key=lambda rec: normalize_name(rec.get("company", "")))


def print_portfolio_matches(portfolio_hits):
    print("\n====================")
    print("PORTFOLIO MATCHES")
    print("====================")
    for rec in portfolio_hits:
        print(rec["source"], "|", rec["company"], "|", rec["recommendation"])


def detect_changes(portfolio_hits, previous_state):
    changes = []
    for rec in portfolio_hits:
        old = previous_state.get(portfolio_state_key(rec))
        if old != rec["recommendation"]:
            changes.append(rec)
    return changes


def get_top_trades(portfolio_hits, limit=10):
    return sorted(portfolio_hits, key=lambda x: x["score"], reverse=True)[:limit]


def _stock_key(rec):
    return rec.get("ticker") or normalize_name(rec["company"])


def dedupe_by_stock_and_source(recommendations):
    """Keep one row per stock per source (highest score, then newest date)."""
    best = {}
    for rec in recommendations:
        key = (_stock_key(rec), rec["source"])
        existing = best.get(key)
        if existing is None:
            best[key] = rec
            continue
        if rec["score"] > existing["score"]:
            best[key] = rec
            continue
        if rec["score"] == existing["score"]:
            rec_date = recommendation_sort_date(rec)
            existing_date = recommendation_sort_date(existing)
            if rec_date > existing_date:
                best[key] = rec
    return list(best.values())


def get_market_picks(recommendations, portfolio_hits, limit=10):
    portfolio_tickers = {p.get("ticker") for p in portfolio_hits if p.get("ticker")}
    non_portfolio = [
        rec for rec in recommendations if rec.get("ticker") not in portfolio_tickers
    ]
    deduped = dedupe_by_stock_and_source(non_portfolio)
    merged = combine_identical_recommendations(deduped)
    return sort_by_recommendation_date(merged)[:limit]


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

Use short paragraphs and bullet points only. Do not use markdown tables.
"""

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


def _merge_source_labels(*labels):
    seen = []
    for label in labels:
        for part in re.split(r"\s·\s", label or ""):
            part = part.strip()
            if part and part not in seen:
                seen.append(part)
    return " · ".join(seen)


def compute_portfolio_actions(portfolio_hits):
    groups = {}
    order = []
    for rec in portfolio_hits:
        key = (
            _stock_key(rec),
            (rec.get("recommendation") or "").strip().lower(),
            rec.get("score", 0),
        )
        if key not in groups:
            groups[key] = {
                "company": rec.get("company", "—"),
                "recommendation": rec.get("recommendation", "—"),
                "signal": rec.get("signal", "HOLD"),
                "score": rec.get("score", 0),
                "upside_values": [],
                "source_labels": [],
            }
            order.append(key)

        entry = groups[key]
        entry["upside_values"].append(upside_percent(rec))
        entry["source_labels"].append(rec.get("source", "—"))

    actions = []
    for key in order:
        entry = groups[key]
        upsides = entry["upside_values"]
        unique_upsides = sorted({round(value, 2) for value in upsides})
        if len(unique_upsides) == 1:
            upside = unique_upsides[0]
            upside_range = None
        else:
            upside = upsides[0]
            upside_range = f"{min(upsides):+.2f}% – {max(upsides):+.2f}%"

        actions.append(
            {
                "company": entry["company"],
                "recommendation": entry["recommendation"],
                "signal": entry["signal"],
                "score": entry["score"],
                "upside": upside,
                "upside_range": upside_range,
                "source": _merge_source_labels(*entry["source_labels"]),
            }
        )

    return sort_by_company_name(actions)


def _portfolio_actions_html(portfolio_hits):
    actions = compute_portfolio_actions(portfolio_hits)
    if not actions:
        return (
            '<p style="color:#5f6368;margin:0 0 16px;padding:16px;background:#fff;'
            'border:1px solid #e8eaed;border-radius:8px;">'
            "No portfolio actions available.</p>"
        )

    rows = []
    for index, action in enumerate(actions):
        bg = "#ffffff" if index % 2 == 0 else "#fafafa"
        if action.get("upside_range"):
            upside_html = (
                f'<span style="color:#5f6368;font-weight:600;">'
                f'{html.escape(action["upside_range"])}</span>'
            )
        else:
            upside = action["upside"]
            if upside > 0:
                upside_html = f'<span style="color:#0f9d58;font-weight:600;">{upside:+.2f}%</span>'
            elif upside < 0:
                upside_html = f'<span style="color:#c5221f;font-weight:600;">{upside:+.2f}%</span>'
            else:
                upside_html = '<span style="color:#9aa0a6;">—</span>'

        rows.append(
            f'<tr style="background:{bg};">'
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;font-weight:600;">'
            f"{html.escape(action['company'])}</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">'
            f"{_recommendation_html(action['recommendation'])}</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">'
            f"{_signal_badge_html(action['signal'])}</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">'
            f"{_score_bar_html(action['score'])}</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{upside_html}</td>'
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;color:#5f6368;font-size:12px;">'
            f"{html.escape(action['source'])}</td>"
            f"</tr>"
        )

    return f"""
<div style="background:#fff;border:1px solid #e8eaed;border-radius:8px;padding:18px 22px;margin-bottom:16px;overflow:hidden;">
  <div style="font-size:13px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px;">Portfolio actions</div>
  <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">
    <thead>
      <tr style="background:#f8f9fa;text-align:left;">
        <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;">Company</th>
        <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;">Recommendation</th>
        <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;">Action</th>
        <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;">Score</th>
        <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;">Upside</th>
        <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;">Sources</th>
      </tr>
    </thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</div>
"""


def _portfolio_actions_text(portfolio_hits):
    actions = compute_portfolio_actions(portfolio_hits)
    lines = [
        "PORTFOLIO ACTIONS",
        "",
        f"{'Company':<28} {'Action':<8} {'Score':>5} {'Upside':>8}",
        "-" * 55,
    ]
    for action in actions:
        upside_text = action.get("upside_range") or f"{action['upside']:+.2f}%"
        lines.append(
            f"{action['company']:<28} {action['signal']:<8} {action['score']:>5} "
            f"{upside_text:>8}"
        )
        if action.get("source"):
            lines.append(f"  Sources: {action['source']}")
    return "\n".join(lines)


# =============================================================================
# Email rendering (HTML)
# =============================================================================

JAPA_JOKE_BANK = [
    (
        "programista",
        "Programista wraca do domu o północy. Żona pyta: „Gdzie byłeś?” "
        "Programista: „W produkcji.” Żona: „Znowu?” Programista: „Tym razem bez downtime’u.”",
    ),
    (
        "inwestor",
        "Inwestor mówi znajomemu: „Kupuję, gdy inni się boją.” "
        "Znajomy: „Super strategia!” Inwestor: „Jeszcze nie wiem jak, ale na pewno tak robię.”",
    ),
    (
        "lekarz",
        "Lekarz pyta pacjenta: „Pal Pan papierosy?” Pacjent: „Nie, one same się palą.” "
        "Lekarz: „To może Pan przestanie chodzić na spacer z zapalniczką?”",
    ),
    (
        "nauczyciel",
        "Nauczyciel pyta ucznia: „Dlaczego spóźniasz się codziennie?” "
        "Uczeń: „Bo wcześniej nie mogę.” Nauczyciel: „Rozumiem. To logiczne.”",
    ),
    (
        "kierowca",
        "Kierowca zatrzymuje autobus co 100 metrów. Pasażer: „Proszę jechać dalej!” "
        "Kierowca: „To nie ja, to GPS ma tryb oszczędzania paliwa.”",
    ),
    (
        "kucharz",
        "Kucharz próbuje nowego przepisu. Żona: „Smakuje jak karton.” "
        "Kucharz: „To fusion kuchni zero waste.”",
    ),
    (
        "fizyk",
        "Fizyk mówi do żony: „Nie kłóćmy się, to bez sensu energetycznie.” "
        "Żona: „Ty zawsze wszystko liczysz!” Fizyk: „Tak, i wyszło, że masz rację.”",
    ),
    (
        "detektyw",
        "Detektyw patrzy na ślad w mące. Pomocnik: „To chyba pies.” "
        "Detektyw: „Nie. To człowiek, który udaje psa. Widzisz te buty?”",
    ),
    (
        "poeta",
        "Poeta czyta wiersz o deszczu. Krytyk: „Brakuje głębi.” "
        "Poeta: „To był wiersz o kapuśniaku, nie o egzystencji.”",
    ),
    (
        "astronauta",
        "Astronauta dzwoni do domu z kosmosu. Syn: „Tato, kiedy wracasz?” "
        "Astronauta: „Jak skończę odrabiać lekcje z grawitacji.”",
    ),
    (
        "barman",
        "Barman podaje klientowi drinka. Klient: „Bez alkoholu, proszę.” "
        "Barman: „To woda?” Klient: „Nie, to mój dzisiejszy portfel po sesji GPW.”",
    ),
    (
        "ogrodnik",
        "Ogrodnik mówi roślinom: „Rośnijcie szybciej, mam deadline.” "
        "Sąsiad: „One cię słyszą.” Ogrodnik: „Dobrze. Niech też wysłuchają stand-upu.”",
    ),
    (
        "pilot",
        "Pilot ogłasza: „Lecimy przez lekkie turbulencje.” "
        "Pasażer: „To wszystko?” Pilot: „To moja ulubiona forma medytacji.”",
    ),
    (
        "matematyk",
        "Matematyk idzie na randkę z kwadratem. Przyjaciel: „Serio?” "
        "Matematyk: „Ma stabilne relacje i przewidywalne zachowanie.”",
    ),
    (
        "listonosz",
        "Listonosz puka do drzwi o 6 rano. Właściciel: „To list czy horror?” "
        "Listonosz: „Zależy, czy to faktura.”",
    ),
    (
        "trener",
        "Trener krzyczy: „Jeszcze pięć powtórzeń!” "
        "Podopieczny: „To już było pięć razy.” Trener: „To była rozgrzewka do liczenia.”",
    ),
    (
        "filozof",
        "Filozof siedzi w restauracji i patrzy na menu. Kelner: „Co wybierze Pan?” "
        "Filozof: „Czy wolna wola istnieje, skoro już jestem głodny?”",
    ),
    (
        "elektryk",
        "Elektryk naprawia instalację. Klient: „Ile to potrwa?” "
        "Elektryk: „Tyle, ile potrzeba, żebyś już nigdy nie pytał o prąd.”",
    ),
]


def get_japa_joke():
    protagonist, joke = random.choice(JAPA_JOKE_BANK)
    return re.sub(re.escape(protagonist), "Japa", joke, flags=re.IGNORECASE)


POSITIVE_REC_KEYWORDS = ("kupuj", "akumuluj", "przeważaj", "buy", "overweight")
NEGATIVE_REC_KEYWORDS = ("sprzedaj", "redukuj", "sell", "underweight")

SIGNAL_STYLES = {
    "BUY": ("#0f9d58", "#e6f4ea"),
    "HOLD": ("#b06000", "#fef7e0"),
    "REDUCE": ("#c5221f", "#fce8e6"),
}


def _signal_badge_html(signal):
    fg, bg = SIGNAL_STYLES.get(signal, ("#5f6368", "#f1f3f4"))
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
        f'background:{bg};color:{fg};font-weight:700;font-size:11px;'
        f'letter-spacing:0.4px;">{signal}</span>'
    )


def _recommendation_color(text):
    lower = (text or "").lower()
    if any(k in lower for k in POSITIVE_REC_KEYWORDS):
        return "#0f9d58"
    if any(k in lower for k in NEGATIVE_REC_KEYWORDS):
        return "#c5221f"
    return "#5f6368"


def _recommendation_html(text):
    color = _recommendation_color(text)
    return (
        f'<span style="color:{color};font-weight:600;text-transform:capitalize;">'
        f'{html.escape(text or "—")}</span>'
    )


def _upside_html(rec):
    pct = upside_percent(rec)
    if rec.get("current_price", 0) <= 0 or rec.get("target_price", 0) <= 0:
        return '<span style="color:#9aa0a6;">—</span>'
    if pct > 0:
        color = "#0f9d58"
    elif pct < 0:
        color = "#c5221f"
    else:
        color = "#5f6368"
    return f'<span style="color:{color};font-weight:600;">{pct:+.2f}%</span>'


def _score_bar_html(score):
    pct = max(0, min(score, 10)) * 10
    if score >= 8:
        color = "#0f9d58"
    elif score >= 5:
        color = "#b06000"
    else:
        color = "#c5221f"
    return (
        f'<div style="display:inline-block;vertical-align:middle;width:60px;'
        f'height:6px;background:#f1f3f4;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{color};"></div>'
        f'</div>'
        f'<span style="display:inline-block;vertical-align:middle;margin-left:6px;'
        f'color:#5f6368;font-size:12px;">{score}/10</span>'
    )


def _price_html(rec):
    cur = rec.get("current_price", 0)
    tgt = rec.get("target_price", 0)
    if cur <= 0 and tgt <= 0:
        return '<span style="color:#9aa0a6;">—</span>'
    parts = []
    if cur > 0:
        parts.append(f'{cur:.2f} zł')
    if tgt > 0:
        arrow = "→"
        parts.append(f'<span style="color:#5f6368;">{arrow}</span> '
                     f'<strong>{tgt:.2f} zł</strong>')
    return " ".join(parts)


def _source_links_html(rec):
    links = rec.get("source_links") or []
    if not links and rec.get("source_url"):
        links = [{"source": rec["source"], "url": rec["source_url"]}]

    parts = []
    for link in links:
        label = link.get("source") or rec.get("source", "Source")
        url = link.get("url") or ""
        if url:
            parts.append(
                f'<a href="{html.escape(url)}" style="color:#1a73e8;text-decoration:none;">'
                f"{html.escape(label)}</a>"
            )
        else:
            parts.append(html.escape(label))

    return " · ".join(parts) if parts else html.escape(rec.get("source", ""))


def _source_links_text(rec):
    links = rec.get("source_links") or []
    if not links and rec.get("source_url"):
        links = [{"source": rec["source"], "url": rec["source_url"]}]

    parts = []
    for link in links:
        label = link.get("source") or rec.get("source", "Source")
        url = link.get("url") or ""
        parts.append(f"{label}: {url}" if url else label)

    return " · ".join(parts) if parts else rec.get("source", "")


def _portfolio_row_html(rec, index):
    bg = "#ffffff" if index % 2 == 0 else "#fafafa"
    return f"""
<tr style="background:{bg};">
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;">
    <div style="font-weight:600;color:#202124;font-size:14px;">{html.escape(rec['company'])}</div>
    <div style="color:#5f6368;font-size:12px;margin-top:2px;">{_source_links_html(rec)}</div>
  </td>
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;">{_recommendation_html(rec['recommendation'])}</td>
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;">{_signal_badge_html(rec['signal'])}</td>
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;">{_score_bar_html(rec['score'])}</td>
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;font-size:13px;">{_price_html(rec)}</td>
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;">{_upside_html(rec)}</td>
  <td style="padding:14px 16px;border-bottom:1px solid #e8eaed;color:#5f6368;font-size:12px;white-space:nowrap;">{html.escape(rec['date'])}</td>
</tr>
"""


def _market_row_html(rec, index):
    bg = "#ffffff" if index % 2 == 0 else "#fafafa"
    return f"""
<tr style="background:{bg};">
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">
    <div style="font-weight:600;color:#202124;font-size:14px;">{html.escape(rec['company'])}</div>
    <div style="color:#5f6368;font-size:12px;margin-top:2px;">{_source_links_html(rec)}</div>
  </td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{_recommendation_html(rec['recommendation'])}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{_signal_badge_html(rec['signal'])}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{_score_bar_html(rec['score'])}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{_upside_html(rec)}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;color:#5f6368;font-size:12px;white-space:nowrap;">{html.escape(rec['date'])}</td>
</tr>
"""


STREET_ACTION_STYLES = {
    "BUY": ("#0f9d58", "#e6f4ea"),
    "HOLD": ("#b06000", "#fef7e0"),
    "WATCH": ("#1a73e8", "#e8f0fe"),
    "AVOID": ("#c5221f", "#fce8e6"),
}


def _street_action_badge_html(action):
    fg, bg = STREET_ACTION_STYLES.get(action, ("#5f6368", "#f1f3f4"))
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
        f'background:{bg};color:{fg};font-weight:700;font-size:11px;'
        f'letter-spacing:0.4px;">{action}</span>'
    )


def _street_buzz_label(item):
    engagement = item.get("engagement", 0)
    mentions = item.get("mentions", 0)
    if engagement >= 50 or mentions >= 5:
        return "High buzz"
    if engagement >= 20 or mentions >= 2:
        return "Moderate buzz"
    return "Low buzz"


def _street_narrative(item):
    posts = item.get("sample_posts", [])
    if posts:
        return posts[0].get("title", "—")[:100]
    return "—"


def _rumor_fundamental_action(item):
    finance = item.get("finance", {})
    buzz = item.get("engagement", 0)
    upside = finance.get("upside_pct")
    analyst = (finance.get("analyst_recommendation") or "").lower().replace(" ", "_")

    bullish = (
        (isinstance(upside, (int, float)) and upside > 10)
        or analyst in ("buy", "strong_buy")
    )
    bearish = (
        (isinstance(upside, (int, float)) and upside < -5)
        or analyst in ("sell", "strong_sell", "underperform")
    )
    high_buzz = buzz >= 30 or item.get("mentions", 0) >= 4

    if high_buzz and not bullish:
        return "AVOID"
    if high_buzz and bullish:
        return "WATCH"
    if bullish:
        return "BUY"
    if bearish:
        return "AVOID"
    return "HOLD"


def compute_street_talk_table_rows(street_talk_data):
    rows = []
    for item in street_talk_data or []:
        finance = item.get("finance", {})
        sample = item.get("sample_posts", [{}])[0]
        rows.append(
            {
                "ticker": item.get("ticker", "—"),
                "name": finance.get("name", item.get("ticker", "—")),
                "street_sentiment": _street_buzz_label(item),
                "rumor": _street_narrative(item),
                "sources": ", ".join(item.get("subreddits", [])),
                "mentions": item.get("mentions", 0),
                "engagement": item.get("engagement", 0),
                "hot_thread_title": sample.get("title", "—"),
                "hot_thread_url": sample.get("url", ""),
                "price": finance.get("price"),
                "target_price": finance.get("target_price"),
                "upside_pct": finance.get("upside_pct"),
                "pe_ratio": finance.get("pe_ratio"),
                "analyst": finance.get("analyst_recommendation") or "—",
                "change_6m": finance.get("price_change_6m_pct"),
                "action": _rumor_fundamental_action(item),
            }
        )
    return rows


def _street_talk_combined_html(street_talk_data):
    rows = compute_street_talk_table_rows(street_talk_data)
    if not rows:
        return (
            '<p style="color:#5f6368;margin:0;padding:16px;background:#fff;'
            'border:1px solid #e8eaed;border-radius:8px;">'
            "No street talk data available today.</p>"
        )

    table_rows = []
    for index, row in enumerate(rows):
        bg = "#ffffff" if index % 2 == 0 else "#fafafa"
        price = row["price"]
        target = row["target_price"]
        upside = row["upside_pct"]
        pe = row["pe_ratio"]

        price_text = f"{price:.2f}" if isinstance(price, (int, float)) else "—"
        target_text = f"{target:.2f}" if isinstance(target, (int, float)) else "—"
        if isinstance(upside, (int, float)):
            upside_text = f"{upside:+.2f}%"
            upside_color = "#0f9d58" if upside > 0 else "#c5221f" if upside < 0 else "#5f6368"
        else:
            upside_text = "—"
            upside_color = "#9aa0a6"
        pe_text = f"{pe:.1f}" if isinstance(pe, (int, float)) else "—"
        change_6m = row["change_6m"]
        change_text = f"{change_6m:+.1f}%" if isinstance(change_6m, (int, float)) else "—"

        if row["hot_thread_url"]:
            hot_thread = (
                f'<a href="{html.escape(row["hot_thread_url"])}" '
                f'style="color:#1a73e8;text-decoration:none;">'
                f'{html.escape(row["hot_thread_title"][:90])}</a>'
            )
        else:
            hot_thread = html.escape(row["hot_thread_title"][:90])

        table_rows.append(
            f'<tr style="background:{bg};">'
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">'
            f'<div style="font-weight:700;color:#202124;">{html.escape(row["ticker"])}</div>'
            f'<div style="color:#5f6368;font-size:12px;margin-top:2px;">{html.escape(row["name"])}</div>'
            f"</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">'
            f'<div style="font-weight:600;color:#202124;font-size:13px;">{html.escape(row["street_sentiment"])}</div>'
            f'<div style="color:#5f6368;font-size:12px;margin-top:4px;">'
            f'{row["mentions"]} mentions · {row["engagement"]} score</div>'
            f'<div style="color:#9aa0a6;font-size:11px;margin-top:4px;">{html.escape(row["sources"])}</div>'
            f"</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;color:#3c4043;font-size:12px;line-height:1.5;">'
            f'<div style="font-style:italic;margin-bottom:6px;">"{html.escape(row["rumor"])}"</div>'
            f"{hot_thread}</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;font-size:13px;">'
            f"{price_text} → <strong>{target_text}</strong></td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;color:{upside_color};font-weight:600;">'
            f"{upside_text}</td>"
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;font-size:12px;">{pe_text}</td>'
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;text-transform:capitalize;font-size:12px;">'
            f'{html.escape(str(row["analyst"]))}</td>'
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;font-size:12px;">{change_text}</td>'
            f'<td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">'
            f'{_street_action_badge_html(row["action"])}</td>'
            f"</tr>"
        )

    return f"""
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;background:#fff;border:1px solid #e8eaed;border-radius:8px;overflow:hidden;margin-bottom:16px;">
  <thead>
    <tr style="background:#f8f9fa;text-align:left;">
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Ticker</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Buzz</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Rumor / Hot thread</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Price → Target</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Upside</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">P/E</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Analyst</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">6M</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Action</th>
    </tr>
  </thead>
  <tbody>{"".join(table_rows)}</tbody>
</table>
"""


def _street_talk_combined_text(street_talk_data):
    rows = compute_street_talk_table_rows(street_talk_data)
    lines = [
        "WHAT THE STREETS TALK ABOUT: RUMORS VS FUNDAMENTALS",
        "Top 10 tickers from Reddit and Motley Fool cross-checked with Yahoo Finance",
        "",
        f"{'Ticker':<8} {'Buzz':<14} {'Action':<8} {'Upside':>8} {'P/E':>6} Analyst",
        "-" * 90,
    ]
    for row in rows:
        upside = row["upside_pct"]
        upside_text = f"{upside:+.1f}%" if isinstance(upside, (int, float)) else "—"
        pe = row["pe_ratio"]
        pe_text = f"{pe:.1f}" if isinstance(pe, (int, float)) else "—"
        lines.append(
            f"{row['ticker']:<8} {row['street_sentiment']:<14} {row['action']:<8} "
            f"{upside_text:>8} {pe_text:>6} {row['analyst']}"
        )
        lines.append(
            f"  Buzz: {row['mentions']} mentions / {row['engagement']} score · {row['sources']}"
        )
        lines.append(f"  Rumor: {row['rumor'][:85]}")
        price = row["price"]
        target = row["target_price"]
        price_text = f"{price:.2f}" if isinstance(price, (int, float)) else "—"
        target_text = f"{target:.2f}" if isinstance(target, (int, float)) else "—"
        lines.append(f"  Yahoo: {price_text} → {target_text}")
        if row["hot_thread_url"]:
            lines.append(f"  Thread: {row['hot_thread_title'][:85]}")
            lines.append(f"  Link: {row['hot_thread_url']}")
    if not rows:
        lines.append("\nNo street talk data available today.")
    return "\n".join(lines)


def _change_row_html(rec, previous):
    return f"""
<tr>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">
    <div style="font-weight:600;color:#202124;">{html.escape(rec['company'])}</div>
    <div style="color:#5f6368;font-size:12px;margin-top:2px;">{_source_links_html(rec)} · {html.escape(rec['date'])}</div>
  </td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;color:#9aa0a6;font-size:13px;text-decoration:line-through;">
    {html.escape(previous or "—")}
  </td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;font-size:18px;color:#5f6368;">→</td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{_recommendation_html(rec['recommendation'])}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #e8eaed;">{_signal_badge_html(rec['signal'])}</td>
</tr>
"""


def _strip_markdown_tables(text):
    """Remove markdown table rows from AI output."""
    if not text:
        return text

    cleaned = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[-:\s|]+\|$", stripped):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
            if len(cells) >= 2:
                cleaned.append(f"- {cells[0]}: {', '.join(cells[1:])}")
            elif cells:
                cleaned.append(f"- {cells[0]}")
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _markdown_to_html(text):
    """Lightweight markdown -> HTML for AI summaries (headings, lists, bold)."""
    if not text:
        return '<p style="color:#5f6368;">No summary available.</p>'

    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<![\*\w])\*(?!\*)([^*\n]+?)\*(?!\*)", r"<em>\1</em>", escaped)

    out = []
    in_list = False
    for raw_line in escaped.split("\n"):
        line = raw_line.rstrip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        numbered = re.match(r"^\s*\d+\.\s+(.*)$", line)

        if heading:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = min(len(heading.group(1)) + 2, 6)
            out.append(
                f'<h{level} style="color:#202124;margin:18px 0 8px;font-size:15px;">'
                f"{heading.group(2)}</h{level}>"
            )
            continue

        if bullet or numbered:
            if not in_list:
                out.append('<ul style="margin:8px 0 8px 20px;padding:0;color:#3c4043;">')
                in_list = True
            text_line = (bullet or numbered).group(1)
            out.append(
                f'<li style="margin-bottom:4px;line-height:1.55;">{text_line}</li>'
            )
            continue

        if in_list:
            out.append("</ul>")
            in_list = False

        if line.strip():
            out.append(
                f'<p style="margin:8px 0;line-height:1.6;color:#3c4043;">{line}</p>'
            )

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def _section_header_html(title, subtitle=None):
    sub = (
        f'<div style="color:#5f6368;font-size:13px;margin-top:2px;">{html.escape(subtitle)}</div>'
        if subtitle
        else ""
    )
    return f"""
<div style="margin:32px 0 12px;">
  <h2 style="color:#202124;margin:0;font-size:18px;font-weight:600;">{html.escape(title)}</h2>
  {sub}
</div>
"""


def build_email_html(
    portfolio_hits,
    investing_portfolio_hits,
    market_top,
    changes,
    previous_state,
    ai_market_summary,
    ai_portfolio_summary,
    street_talk_data=None,
    street_talk_summary=None,
    japa_joke=None,
):
    timestamp = datetime.now().strftime("%A, %d %B %Y · %H:%M")

    market_only = market_top

    buy_count = sum(1 for r in portfolio_hits if r["signal"] == "BUY")
    hold_count = sum(1 for r in portfolio_hits if r["signal"] == "HOLD")
    reduce_count = sum(1 for r in portfolio_hits if r["signal"] == "REDUCE")

    portfolio_rows = "".join(
        _portfolio_row_html(rec, i) for i, rec in enumerate(portfolio_hits)
    ) or (
        '<tr><td colspan="7" style="padding:24px;text-align:center;color:#5f6368;">'
        "No portfolio recommendations in the last 30 days.</td></tr>"
    )

    investing_rows = "".join(
        _portfolio_row_html(rec, i) for i, rec in enumerate(investing_portfolio_hits)
    ) or (
        '<tr><td colspan="7" style="padding:24px;text-align:center;color:#5f6368;">'
        "No Investing.com consensus data for portfolio holdings.</td></tr>"
    )

    market_rows = "".join(
        _market_row_html(rec, i) for i, rec in enumerate(market_only)
    ) or (
        '<tr><td colspan="6" style="padding:24px;text-align:center;color:#5f6368;">'
        "No additional market picks.</td></tr>"
    )

    street_talk_block = f"""
        {_section_header_html(
            "What the Streets talk about: rumors and gossips",
            "Top 10 tickers from Reddit and Motley Fool — social buzz vs Yahoo Finance fundamentals",
        )}
        {_street_talk_combined_html(street_talk_data)}

        {_section_header_html("Street talk analysis")}
        <div style="background:#fff;border:1px solid #e8eaed;border-radius:8px;padding:18px 22px;font-size:14px;">
          {_markdown_to_html(street_talk_summary)}
        </div>
"""

    if changes:
        change_rows = "".join(
            _change_row_html(rec, previous_state.get(portfolio_state_key(rec)))
            for rec in changes
        )
        changes_block = f"""
{_section_header_html("Changes since last run", f"{len(changes)} recommendation(s) changed")}
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;background:#fff;border:1px solid #e8eaed;border-radius:8px;overflow:hidden;">
  <thead>
    <tr style="background:#f8f9fa;text-align:left;">
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Company</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Was</th>
      <th style="padding:10px 16px;"></th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Now</th>
      <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Signal</th>
    </tr>
  </thead>
  <tbody>{change_rows}</tbody>
</table>
"""
    else:
        changes_block = (
            f'{_section_header_html("Changes since last run")}'
            '<p style="color:#5f6368;margin:0;padding:16px;background:#fff;'
            'border:1px solid #e8eaed;border-radius:8px;">'
            "No recommendation changes since the last run.</p>"
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f3f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#202124;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f1f3f4;">
  <tr><td align="center" style="padding:24px 12px;">
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:880px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(60,64,67,0.12);">
      <tr><td style="background:linear-gradient(135deg,#1a73e8 0%,#0f9d58 100%);padding:28px 32px;color:#ffffff;">
        <div style="font-size:13px;opacity:0.9;letter-spacing:1.5px;text-transform:uppercase;">GPW Daily Analysis</div>
        <div style="font-size:24px;font-weight:600;margin-top:6px;">Analyst Recommendations</div>
        <div style="font-size:13px;opacity:0.9;margin-top:4px;">{html.escape(timestamp)}</div>
      </td></tr>

      <tr><td style="padding:24px 32px;background:#fafafa;border-bottom:1px solid #e8eaed;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr>
            <td width="33%" align="center" style="padding:8px;">
              <div style="font-size:24px;font-weight:700;color:#0f9d58;">{buy_count}</div>
              <div style="font-size:11px;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Buy</div>
            </td>
            <td width="33%" align="center" style="padding:8px;border-left:1px solid #e8eaed;border-right:1px solid #e8eaed;">
              <div style="font-size:24px;font-weight:700;color:#b06000;">{hold_count}</div>
              <div style="font-size:11px;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Hold</div>
            </td>
            <td width="33%" align="center" style="padding:8px;">
              <div style="font-size:24px;font-weight:700;color:#c5221f;">{reduce_count}</div>
              <div style="font-size:11px;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Reduce</div>
            </td>
          </tr>
        </table>
      </td></tr>

      <tr><td style="padding:8px 32px 32px;">
        {_section_header_html("Your portfolio", "Sorted by company name · identical target prices merged across venues")}
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;background:#fff;border:1px solid #e8eaed;border-radius:8px;overflow:hidden;">
          <thead>
            <tr style="background:#f8f9fa;text-align:left;">
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Company</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Recommendation</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Signal</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Score</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Price → Target</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Upside</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Date</th>
            </tr>
          </thead>
          <tbody>{portfolio_rows}</tbody>
        </table>

        {_section_header_html(
            "Investing.com — analyst consensus",
            "Based on analyst sentiment and signal analysis from the previous day (Investing.com consensus estimates).",
        )}
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;background:#fff;border:1px solid #e8eaed;border-radius:8px;overflow:hidden;">
          <thead>
            <tr style="background:#f8f9fa;text-align:left;">
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Company</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Recommendation</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Signal</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Score</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Price → Target</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Upside</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Date</th>
            </tr>
          </thead>
          <tbody>{investing_rows}</tbody>
        </table>

        {changes_block}

        {_section_header_html("AI portfolio summary")}
        {_portfolio_actions_html(portfolio_hits)}
        <div style="background:#fff;border:1px solid #e8eaed;border-radius:8px;padding:18px 22px;font-size:14px;">
          {_markdown_to_html(ai_portfolio_summary)}
        </div>

        {_section_header_html("Top market picks", "Non-portfolio stocks sorted by recommendation date")}
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;background:#fff;border:1px solid #e8eaed;border-radius:8px;overflow:hidden;">
          <thead>
            <tr style="background:#f8f9fa;text-align:left;">
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Company</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Recommendation</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Signal</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Score</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Upside</th>
              <th style="padding:10px 16px;font-size:12px;font-weight:600;color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;">Date</th>
            </tr>
          </thead>
          <tbody>{market_rows}</tbody>
        </table>

        {_section_header_html("AI market summary")}
        <div style="background:#fff;border:1px solid #e8eaed;border-radius:8px;padding:18px 22px;font-size:14px;">
          {_markdown_to_html(_strip_markdown_tables(ai_market_summary))}
        </div>

        {street_talk_block}

        {_section_header_html("Japa")}
        <div style="background:#fff;border:1px solid #e8eaed;border-radius:8px;padding:18px 22px;font-size:14px;line-height:1.6;color:#3c4043;">
          {html.escape(japa_joke or get_japa_joke())}
        </div>
      </td></tr>

      <tr><td style="padding:18px 32px;background:#f8f9fa;border-top:1px solid #e8eaed;color:#9aa0a6;font-size:11px;text-align:center;">
        Sources: BiznesRadar · Strefa Inwestorów · Bankier · Investing.com · Motley Fool · Reddit · Yahoo Finance. GPW recommendations newer than 30 days.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def build_email_text(
    portfolio_hits,
    investing_portfolio_hits,
    market_top,
    changes,
    previous_state,
    ai_market_summary,
    ai_portfolio_summary,
    street_talk_data=None,
    street_talk_summary=None,
    japa_joke=None,
):
    """Plain-text fallback for clients that don't render HTML."""
    market_only = market_top

    lines = [
        "GPW DAILY ANALYSIS",
        f"Generated: {datetime.now():%A, %d %B %Y · %H:%M}",
        "",
        "=" * 60,
        f"YOUR PORTFOLIO ({len(portfolio_hits)} holdings)",
        "=" * 60,
    ]
    for rec in portfolio_hits:
        lines.append(
            f"\n• {rec['company']} — {rec['source']}"
        )
        lines.append(f"  Source: {_source_links_text(rec)}")
        lines.append(
            f"  {rec['recommendation']} [{rec['signal']}]  {rec['score']}/10  "
            f"upside {upside_percent(rec):+.2f}%  ·  {rec['date']}"
        )

    lines += [
        "",
        "=" * 60,
        "INVESTING.COM — ANALYST CONSENSUS",
        "Based on analyst sentiment and signal analysis from the previous day.",
        "=" * 60,
    ]
    if investing_portfolio_hits:
        for rec in investing_portfolio_hits:
            lines.append(f"\n• {rec['company']}")
            lines.append(f"  Source: {_source_links_text(rec)}")
            lines.append(
                f"  {rec['recommendation']} [{rec['signal']}]  {rec['score']}/10  "
                f"upside {upside_percent(rec):+.2f}%  ·  {rec['date']}"
            )
    else:
        lines.append("\nNo Investing.com consensus data for portfolio holdings.")

    lines += ["", "=" * 60, "CHANGES SINCE LAST RUN", "=" * 60]
    if changes:
        for rec in changes:
            old = previous_state.get(portfolio_state_key(rec), "—")
            lines.append(
                f"\n• {rec['company']}: {old} → {rec['recommendation']} [{rec['signal']}]"
            )
            lines.append(f"  Source: {_source_links_text(rec)} · {rec['date']}")
    else:
        lines.append("\nNo recommendation changes since the last run.")

    lines += [
        "",
        "=" * 60,
        "AI PORTFOLIO SUMMARY",
        "=" * 60,
        "",
        _portfolio_actions_text(portfolio_hits),
        "",
        ai_portfolio_summary or "",
    ]

    lines += ["", "=" * 60, "TOP MARKET PICKS (NON-PORTFOLIO)", "=" * 60]
    for rec in market_only:
        lines.append(
            f"\n• {rec['company']} — {rec['recommendation']} [{rec['signal']}]  "
            f"{rec['score']}/10  upside {upside_percent(rec):+.2f}%"
        )
        lines.append(f"  Source: {_source_links_text(rec)} · {rec['date']}")

    lines += [
        "",
        "=" * 60,
        "AI MARKET SUMMARY",
        "=" * 60,
        "",
        _strip_markdown_tables(ai_market_summary) or "",
    ]

    lines += [
        "",
        "=" * 60,
        _street_talk_combined_text(street_talk_data),
        "",
        "=" * 60,
        "STREET TALK ANALYSIS",
        "=" * 60,
        "",
        street_talk_summary or "",
    ]

    lines += ["", "=" * 60, "JAPA", "=" * 60, "", japa_joke or get_japa_joke()]

    return "\n".join(lines)


def send_email(subject, html_body, text_body):
    if not EMAIL_PASSWORD:
        raise ValueError("EMAIL_PASSWORD is empty")
    if not EMAIL_SENDER:
        raise ValueError("EMAIL_SENDER is empty")

    recipients = [
        addr
        for addr in (
            EMAIL_RECEIVER,
            "grzegorz.ras@onet.eu",
            "Sebastian.ozdoba@gmail.com",
        )
        if addr
    ]
    if not recipients:
        raise ValueError("No email recipients configured")

    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_SENDER
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=60) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        refused = server.send_message(msg, to_addrs=recipients)

    if refused:
        raise smtplib.SMTPRecipientsRefused(refused)

    print(f"Email sent to: {', '.join(recipients)}")
    return recipients




# =============================================================================
# Main
# =============================================================================

def main():
    previous_state = load_previous_state()

    biznesradar = scrape_biznesradar()
    strefa = scrape_strefa_inwestorow()
    bankier = scrape_bankier()
    investing = scrape_investing_com()
    motley_fool = scrape_motley_fool_top_stocks()
    recommendations = biznesradar + strefa + bankier + investing + motley_fool
    gpw_recommendations = exclude_source(recommendations, "Investing.com")
    print(
        f"Scraped {len(biznesradar)} from BiznesRadar, "
        f"{len(strefa)} from Strefa Inwestorów, "
        f"{len(bankier)} from Bankier, "
        f"{len(investing)} from Investing.com, "
        f"{len(motley_fool)} from Motley Fool ({len(recommendations)} total)"
    )

    raw_portfolio_hits = ensure_extra_portfolio_recommendations(
        filter_portfolio_hits(gpw_recommendations)
    )
    investing_portfolio_hits = build_investing_portfolio_hits(investing)
    per_venue_portfolio = dedupe_by_stock_and_source(raw_portfolio_hits)
    per_venue_investing = dedupe_by_stock_and_source(investing_portfolio_hits)
    print_portfolio_matches(per_venue_portfolio)

    changes = detect_changes(per_venue_portfolio, previous_state)
    save_current_state(per_venue_portfolio + per_venue_investing)

    portfolio_hits = expand_portfolio_by_venue(raw_portfolio_hits)

    market_top = get_market_picks(gpw_recommendations, portfolio_hits, limit=10)
    ai_market_summary = generate_ai_summary(gpw_recommendations)
    ai_portfolio_summary = generate_ai_summary(portfolio_hits, portfolio_only=True)

    reddit_token = get_reddit_access_token()
    reddit_posts = scrape_reddit_investment_subs(token=reddit_token)
    fool_posts = scrape_motley_fool_trending()
    street_talk_data = build_street_talk_dataset(
        reddit_posts,
        fool_posts=fool_posts,
        token=reddit_token,
    )
    street_talk_summary = generate_street_talk_analysis(street_talk_data)
    japa_joke = get_japa_joke()
    print(
        f"Street talk: {len(street_talk_data)} hot tickers from "
        f"Reddit ({len(reddit_posts)} posts) and Motley Fool ({len(fool_posts)} headlines)"
    )

    html_body = build_email_html(
        portfolio_hits,
        investing_portfolio_hits,
        market_top,
        changes,
        previous_state,
        ai_market_summary,
        ai_portfolio_summary,
        street_talk_data,
        street_talk_summary,
        japa_joke,
    )
    text_body = build_email_text(
        portfolio_hits,
        investing_portfolio_hits,
        market_top,
        changes,
        previous_state,
        ai_market_summary,
        ai_portfolio_summary,
        street_talk_data,
        street_talk_summary,
        japa_joke,
    )
    send_email("GPW Daily Analyst Recommendations", html_body, text_body)
    print("Email sent successfully.")


if __name__ == "__main__":
    main()
