"""
Core valuation engine: catalog loading, live market scraping, and AI-assisted appraisal.
"""
import json
import logging
import os
import re

import pandas as pd
import requests
import streamlit as st
from apify_client import ApifyClient
from openai import OpenAI

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")
APIFY_TIMEOUT_SECS = 60
FALLBACK_RETAIL_CAD = 45_000
FALLBACK_USD_TO_CAD = 1.36  # used only if the live FX lookup fails


def load_collector_catalog():
    """Reads the external catalog.json flat array. Returns [] on any failure."""
    try:
        with open(CATALOG_PATH, "r") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load catalog.json: %s", e)
        return []


def get_catalog_makes():
    """Returns the alphabetically sorted master brand list for the selectbox."""
    return sorted(load_collector_catalog())


@st.cache_data(ttl=3600)
def get_usd_to_cad_rate():
    """Fetches a live USD->CAD rate, cached for an hour. Falls back to a static rate on failure."""
    try:
        resp = requests.get("https://api.exchangerate.host/latest", params={"base": "USD", "symbols": "CAD"}, timeout=5)
        resp.raise_for_status()
        rate = resp.json()["rates"]["CAD"]
        return float(rate)
    except Exception as e:
        logger.warning("Live FX lookup failed, using static fallback rate: %s", e)
        return FALLBACK_USD_TO_CAD


@st.cache_data(ttl=1800, show_spinner=False)
def scrape_live_market_data(make, model, year):
    """
    Queries specialty auction rooms via Apify for completed/active listings.
    Cached for 30 minutes per (make, model, year) to avoid re-running paid scraper jobs
    on every click.
    """
    listings = []
    apify_token = st.secrets.get("APIFY_TOKEN")
    if not apify_token:
        logger.warning("APIFY_TOKEN missing; skipping live market scrape.")
        return pd.DataFrame(columns=["Source", "Title", "Price (USD)", "Odometer", "Status"])

    apify_client = ApifyClient(apify_token)
    search_string = f"{make} {model}".strip()

    # --- ROOM 1: BRING A TRAILER ---
    try:
        bat_run = apify_client.actor("silentflow/bringatrailer-scraper").call(
            run_input={"searches": [search_string], "maxItems": 15},
            timeout_secs=APIFY_TIMEOUT_SECS,
        )
        for item in apify_client.dataset(bat_run["defaultDatasetId"]).iterate_items():
            raw_price = item.get("price", 0)
            mileage = item.get("mileage") or item.get("odometer", 0)
            listings.append({
                "Source": "Bring a Trailer",
                "Title": item.get("title") or f"{make} {model}",
                "Price (USD)": int(raw_price) if raw_price else 0,
                "Odometer": f"{int(mileage):,} mi" if mileage else "N/A",
                "Status": str(item.get("status", "Closed")).capitalize(),
            })
    except Exception as e:
        logger.error("Bring a Trailer scrape failed for '%s': %s", search_string, e)

    # --- ROOM 2: CARS & BIDS ---
    try:
        cb_run = apify_client.actor("lulzasaur/carsandbids-scraper").call(
            run_input={"searchQueries": [search_string], "status": "closed", "maxResults": 10},
            timeout_secs=APIFY_TIMEOUT_SECS,
        )
        for item in apify_client.dataset(cb_run["defaultDatasetId"]).iterate_items():
            raw_price = item.get("price") or item.get("currentBid") or 0
            clean_price = re.sub(r"[^\d.]", "", str(raw_price)) if raw_price else "0"
            mileage = item.get("mileage") or item.get("odometer", 0)
            listings.append({
                "Source": "Cars & Bids",
                "Title": item.get("title") or f"{make} {model}",
                "Price (USD)": int(float(clean_price)) if clean_price else 0,
                "Odometer": f"{int(mileage):,} mi" if mileage else "N/A",
                "Status": "Closed",
            })
    except Exception as e:
        logger.error("Cars & Bids scrape failed for '%s': %s", search_string, e)

    if not listings:
        return pd.DataFrame(columns=["Source", "Title", "Price (USD)", "Odometer", "Status"])
    return pd.DataFrame(listings)


def _ai_normalize_query(make, model):
    """Asks the LLM to normalize make/model into clean auction-searchable keywords."""
    openai_key = st.secrets.get("OPENAI_API_KEY")
    if not openai_key:
        return make, model

    client = OpenAI(api_key=openai_key)
    prompt = f"""You are an automotive data parser. Normalize the following vehicle make and
model into a clean, searchable keyword string for a collector car auction house like
Bring a Trailer.
INPUT MAKE: {make}
INPUT MODEL: {model}
Return ONLY a minified JSON object with exactly these two keys:
{{"search_make": "Cleaned Make", "search_model": "Cleaned Model"}}"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(res.choices[0].message.content)
        return parsed.get("search_make", make), parsed.get("search_model", model)
    except Exception as e:
        logger.warning("AI query normalization failed, using raw input: %s", e)
        return make, model


def _ai_appraise(year, make, model, kilometers, condition, provenance, data_anchor_payload, listings_json):
    """Asks the LLM for a structured appraisal. Returns None on failure so caller can fall back."""
    openai_key = st.secrets.get("OPENAI_API_KEY")
    if not openai_key:
        return None

    client = OpenAI(api_key=openai_key)
    prompt = f"""You are a professional classic and collector vehicle appraiser specializing in
the Canadian market (pricing in CAD).
Evaluate this vehicle: {year} {make} {model}, {kilometers:,} km, Condition: {condition},
Provenance/History: {provenance}.
Context: {data_anchor_payload}
Comparable listings (JSON): {listings_json}
Return ONLY a JSON object with keys: "retail_average", "cash_offer", "ai_rationale"."""
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        logger.error("AI appraisal failed: %s", e)
        return None


def generate_valuation(year, make, model, kilometers, condition, provenance):
    """Calculates a valuation using scraped market data (when available) plus AI appraisal,
    falling back to local heuristics if either the scrapers or the LLM are unavailable.
    Returns (cash_offer, retail_average, df_market)."""
    search_make, search_model = _ai_normalize_query(make, model)
    df_market = scrape_live_market_data(search_make, search_model, year)

    valid_prices = df_market[df_market["Price (USD)"] > 0]["Price (USD)"] if not df_market.empty else pd.Series(dtype=float)
    has_live_data = len(valid_prices) >= 1

    fx_rate = get_usd_to_cad_rate()

    if has_live_data:
        bat_average_price = int(valid_prices.mean() * fx_rate)
        data_anchor_payload = f"Live Market Aggregate Base: ${bat_average_price:,} CAD based on {len(valid_prices)} matches (FX rate {fx_rate:.4f})."
    else:
        bat_average_price = 0
        data_anchor_payload = "No live pricing data retrieved from scrapers. Relying on historical baseline frameworks."

    listings_json = df_market.to_json(orient="records") if has_live_data else "[]"

    ai_result = _ai_appraise(year, make, model, kilometers, condition, provenance, data_anchor_payload, listings_json)
    if ai_result:
        retail_average = int(ai_result.get("retail_average") or (bat_average_price or FALLBACK_RETAIL_CAD))
        cash_offer = int(ai_result.get("cash_offer") or (retail_average * 0.85))
        st.session_state.ai_rationale = str(ai_result.get("ai_rationale", "Appraisal successfully compiled."))
        return cash_offer, retail_average, df_market

    retail_average = bat_average_price if bat_average_price > 0 else FALLBACK_RETAIL_CAD
    cash_offer = int(retail_average * 0.85)
    st.session_state.ai_rationale = (
        "AI appraisal unavailable — using live scraped market average."
        if has_live_data else
        "AI appraisal and live market data both unavailable — using default baseline pricing."
    )
    return cash_offer, retail_average, df_market
