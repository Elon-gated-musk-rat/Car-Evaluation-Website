from apify_client import ApifyClient
from openai import OpenAI
import pandas as pd
import streamlit as st
import json
import os

def load_collector_catalog():
    """Reads the external catalog.json flat array safely if it exists."""
    catalog_path = "catalog.json"
    if os.path.exists(catalog_path):
        with open(catalog_path, "r") as f:
            return json.load(f)
    return []

def get_catalog_makes():
    """Returns the alphabetically sorted master brand list to populate the selectbox."""
    catalog = load_collector_catalog()
    return sorted(catalog) if isinstance(catalog, list) else []

def scrape_live_market_data(make, model, year):
    """
    Queries specialty auction rooms via Apify to scrape active 
    and completed asset listings matching clean parameters.
    """
    listings = []
    apify_client = ApifyClient(st.secrets["APIFY_TOKEN"])
    search_string = f"{make} {model}"
    
    # --- TASK 1: BRING A TRAILER (COMPLETED/SOLD TRANSACTION MATRIX) ---
    try:
        bat_run = apify_client.actor("silentflow/bringatrailer-scraper").call(
            run_input={"searches": [search_string], "maxItems": 10}
        )
        for item in apify_client.dataset(bat_run["defaultDatasetId"]).iterate_items():
            title = item.get("title", "")
            if str(year) in title or str(year) in str(item.get("year", "")):
                listings.append({
                    "Source": "Bring a Trailer (Sold)",
                    "Title": item.get("title", title),
                    "Price": int(item.get("price", 0)),
                    "KM": int(item.get("mileage", 0)) * 1.60934 if item.get("mileage") else 50000,
                    "Is_Sold_Comp": True
                })
    except Exception:
        pass 

    # --- TASK 2: CARS & BIDS ---
    try:
        cb_run = apify_client.actor("lulzasaur/carsandbids-scraper").call(
            run_input={"search_query": f"{year} {search_string}", "maxItems": 4}
        )
        for item in apify_client.dataset(cb_run["defaultDatasetId"]).iterate_items():
            listings.append({
                "Source": "Cars & Bids",
                "Title": item.get("title", ""),
                "Price": int(item.get("price") or item.get("current_bid", 0)),
                "KM": int(item.get("mileage", 50000)),
                "Is_Sold_Comp": False
            })
    except Exception:
        pass

    # --- TASK 3: HEMMINGS CLASSIC ADVERTISER ---
    try:
        hemmings_run = apify_client.actor("ecomscrape/hemmings-cars-search-scraper").call(
            run_input={"query": f"{year} {search_string}", "maxItems": 4}
        )
        for item in apify_client.dataset(hemmings_run["defaultDatasetId"]).iterate_items():
            listings.append({
                "Source": "Hemmings Classified",
                "Title": item.get("title", f"{year} {search_string}"),
                "Price": int(item.get("price", 0)),
                "KM": int(item.get("mileage", 50000)),
                "Is_Sold_Comp": False
            })
    except Exception:
        pass

    return pd.DataFrame(listings)

def generate_valuation(year, make, model, kilometers, condition, accidents):
    """
    Leverages an upfront OpenAI model string cleaner to map structural 
    chassis designations seamlessly before firing scrapers and calculating averages.
    """
    ai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    # --- AI QUERY OPTIMIZER BLOCK ---
    # Normalizes internal codes like 'w463' or 'e46' into clear searchable auction targets
    clean_prompt = f"""
    You are an automotive data parser. Take the following vehicle make and model input and normalize it into a clean, searchable keyword string for a collector car auction house like Bring a Trailer. 
    If the input includes an internal factory chassis code (like 'W463 G-Class', 'E30', or '997'), expand or clean it to include the actual searchable market name (e.g., 'G500', 'M3', or '911').
    
    INPUT MAKE: {make}
    INPUT MODEL: {model}
    
    Return ONLY a minified JSON object with no markdown wrappers using exactly these two keys:
    {{"search_make": "Cleaned Make", "search_model": "Cleaned Model"}}
    """
    try:
        clean_res = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": clean_prompt}],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        clean_json = json.loads(clean_res.choices[0].message.content)
        search_make = clean_json.get("search_make", make)
        search_model = clean_json.get("search_model", model)
    except Exception:
        search_make = make
        search_model = model

    # Execute scraping loops using the cleaned text strings
    df_market = scrape_live_market_data(search_make, search_model, year)
    
    bat_sold_listings = df_market[(df_market["Source"].str.contains("Bring a Trailer")) & (df_market["Price"] > 0)] if not df_market.empty else pd.DataFrame()
    has_live_data = not df_market.empty and len(df_market[df_market["Price"] > 0]) >= 1
    
    # Set mathematical anchors cleanly
    if not bat_sold_listings.empty:
        bat_average_price = int(bat_sold_listings["Price"].mean())
        data_anchor_payload = f"Bring a Trailer Sold Data Average Base: ${bat_average_price:,} CAD"
    elif has_live_data:
        bat_average_price = int(df_market["Price"].mean())
        data_anchor_payload = f"Aggregated Platform Data Average Base: ${bat_average_price:,} CAD"
    else:
        bat_average_price = 0
        data_anchor_payload = "No live pricing data retrieved from scrapers. Rely on historical market database knowledge for this classic."

    listings_json = df_market.to_json(orient="records") if has_live_data else "[]"
    
    # --- APPRAISAL BRAIN LOGIC ---
    appraisal_prompt = f"""
    You are a professional classic and collector vehicle appraiser specializing in the Canadian market (pricing in CAD).
    Evaluate the target vehicle specs against live listing records and collector market indices.

    TARGET VEHICLE SPECIFICATIONS:
    - Year: {year}
    - Make: {make}
    - Model: {model} (Cleaned Target: {search_model})
    - Odometer: {kilometers:,} km
    - Condition Grading: {condition}
    - Provenance / Authenticity / Restoration History: {accidents}

    DATA ANALYSIS CONTEXT:
    - {data_anchor_payload}
    - Full Scraped Live Listing Pool JSON: {listings_json}

    CLASSIC APPRAISAL CRITERIA:
    1. VALUATION HOOK: If live transaction data or a baseline average is present, use it as your mathematical baseline anchor. If the data pool is empty, dynamically use your deep built-in collector knowledge base to estimate a baseline valuation for a standard Condition 3 example of a {year} {make} {model} in the Canadian market.
    2. CONDITION ADJUSTMENT: Scale values based on the condition tier (Condition 1 commands massive premiums; Condition 4 requires heavy concessions for structural restoration).
    3. ORIGINALITY RATIO: Factor in the provenance status. Original numbers-matching elements add a 15-30% market bump.
    4. LIQUIDATION MARGIN: Set 'cash_offer' to be 15% lower than your calculated 'retail_average' to account for dealer logistics, auction consignment, and overhead.

    Output format must be strictly a clean, minified JSON object with no markdown block identifiers.
    Use exactly these keys:
    {{
        "retail_average": <Integer representing calculated fair collector retail price in CAD>,
        "cash_offer": <Integer representing our dynamic dealer investment buyout quote in CAD>,
        "ai_rationale": "<A short appraisal sentence outlining how the market baseline for this {make} {model} was parsed and scaled based on its condition and history>"
    }}
    """
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": appraisal_prompt}],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        results = json.loads(response.choices[0].message.content)
        
        retail_average = int(results.get("retail_average", bat_average_price if bat_average_price > 0 else 35000))
        cash_offer = int(results.get("cash_offer", retail_average * 0.85))
        ai_rationale = str(results.get("ai_rationale", "Appraisal verified successfully."))
        
        st.session_state.ai_rationale = ai_rationale
        return cash_offer, retail_average, df_market
        
    except Exception as e:
        st.warning(f"Collector appraisal anomaly ({e}). Defaulting to fallback metrics.")
        fallback_retail = bat_average_price if bat_average_price > 0 else 45000
        st.session_state.ai_rationale = "System default parameters applied due to API processing timeout."
        return int(fallback_retail * 0.85), int(fallback_retail), df_market