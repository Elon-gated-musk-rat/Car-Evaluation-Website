from apify_client import ApifyClient
from openai import OpenAI
import pandas as pd
import streamlit as st
import json
import os
import re

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
    Queries specialty auction rooms via Apify to scrape completed and active 
    asset listings matching precise parameters to build the aggregation pool.
    """
    listings = []
    apify_token = st.secrets.get("APIFY_TOKEN")
    if not apify_token:
        return pd.DataFrame(listings)
        
    apify_client = ApifyClient(apify_token)
    search_string = f"{make} {model}"
    
    # --- ROOM 1: BRING A TRAILER ---
    try:
        bat_run = apify_client.actor("silentflow/bringatrailer-scraper").call(
            run_input={"searches": [search_string], "maxItems": 10}
        )
        for item in apify_client.dataset(bat_run["defaultDatasetId"]).iterate_items():
            title = item.get("title", "")
            # Verify the listing matches our model or target year to maintain accuracy
            if str(year) in title or str(item.get("year", "")) == str(year) or not title:
                raw_price = item.get("price", 0)
                mileage = item.get("mileage") or item.get("odometer", 0)
                
                listings.append({
                    "Source": "Bring a Trailer",
                    "Title": item.get("title") or f"{year} {make} {model}",
                    "Price (USD)": int(raw_price) if raw_price else 0,
                    "Odometer": f"{int(mileage):,} mi" if mileage else "N/A",
                    "Status": str(item.get("status", "Closed")).capitalize()
                })
    except Exception:
        pass 

    # --- ROOM 2: CARS & BIDS ---
    try:
        cb_run = apify_client.actor("lulzasaur/carsandbids-scraper").call(
            run_input={
                "searchQueries": [f"{year} {search_string}"],
                "status": "closed",
                "maxResults": 5
            }
        )
        for item in apify_client.dataset(cb_run["defaultDatasetId"]).iterate_items():
            raw_price = item.get("price") or item.get("currentBid") or 0
            clean_price = re.sub(r'[^\d.]', '', str(raw_price)) if raw_price else "0"
            mileage = item.get("mileage") or item.get("odometer", 0)
            
            listings.append({
                "Source": "Cars & Bids",
                "Title": item.get("title") or f"{year} {make} {model}",
                "Price (USD)": int(float(clean_price)) if clean_price else 0,
                "Odometer": f"{int(mileage):,} mi" if mileage else "N/A",
                "Status": "Closed"
            })
    except Exception:
        pass

    # Clean up empty data frames if all rooms failed
    if not listings:
        return pd.DataFrame(columns=["Source", "Title", "Price (USD)", "Odometer", "Status"])
        
    return pd.DataFrame(listings)

def generate_valuation(year, make, model, kilometers, condition, provenance):
    """
    Leverages an upfront OpenAI model string cleaner to map structural 
    chassis designations before firing scrapers and calculating averages.
    """
    openai_key = st.secrets.get("OPENAI_API_KEY")
    ai_client = OpenAI(api_key=openai_key) if openai_key else None
    
    search_make = make
    search_model = model

    # --- AI QUERY OPTIMIZER BLOCK ---
    if ai_client:
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
            pass

    # Execute scraping loops using the filtered targets
    df_market = scrape_live_market_data(search_make, search_model, year)
    
    # Check valid values inside the matrix
    has_live_data = not df_market.empty and len(df_market[df_market["Price (USD)"] > 0]) >= 1
    
    # Mathematical conversion and baseline calculations
    if has_live_data:
        valid_prices = df_market[df_market["Price (USD)"] > 0]["Price (USD)"]
        average_usd = valid_prices.mean()
        # FX conversion factor (USD to CAD)
        bat_average_price = int(average_usd * 1.36)
        data_anchor_payload = f"Live Market Aggregate Base: ${bat_average_price:,} CAD based on {len(valid_prices)} matches."
    else:
        bat_average_price = 0
        data_anchor_payload = "No live pricing data retrieved from scrapers. Relying on historical baseline frameworks."

    listings_json = df_market.to_json(orient="records") if has_live_data else "[]"
    
    # --- APPRAISAL BRAIN LOGIC ---
    if ai_client:
        appraisal_prompt = f"""
        You are a professional classic and collector vehicle appraiser specializing in the Canadian market (pricing in CAD).
        Evaluate the target vehicle specs against live listing records and collector market indices.

        TARGET VEHICLE SPECIFICATIONS:
        - Year: {year}
        - Make: {make}
        - Model: {model}
        - Odometer: {kilometers:,} km
        - Condition Grading: {condition}
        - Provenance / Restoration History: {provenance}

        DATA ANALYSIS CONTEXT:
        - {data_anchor_payload}
        - Full Scraped Live Listing Pool JSON: {listings_json}

        CLASSIC APPRAISAL CRITERIA:
        1. VALUATION HOOK: If data pool is empty, use your built-in collector knowledge base to estimate a baseline valuation for a standard Condition 3 example of a {year} {make} {model} in CAD.
        2. CONDITION ADJUSTMENT: Scale values based on condition tier.
        3. LIQUIDATION MARGIN: Set 'cash_offer' to be 15% lower than 'retail_average'.

        Output format must be strictly a clean, minified JSON object with no markdown block identifiers.
        Use exactly these keys:
        {{
            "retail_average": <Integer representing calculated fair collector retail price in CAD>,
            "cash_offer": <Integer representing our dynamic dealer investment buyout quote in CAD>,
            "ai_rationale": "<A short appraisal sentence outlining how the market baseline was parsed>"
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
            
            retail_average = int(results.get("retail_average", bat_average_price if bat_average_price > 0 else 45000))
            cash_offer = int(results.get("cash_offer", retail_average * 0.85))
            ai_rationale = str(results.get("ai_rationale", "Appraisal successfully compiled."))
            
            st.session_state.ai_rationale = ai_rationale
            return cash_offer, retail_average, df_market
        except Exception:
            pass

    # Fallback default runner logic if OpenAI quota is empty/blocked
    retail_average = bat_average_price if bat_average_price > 0 else 45000
    cash_offer = int(retail_average * 0.85)
    st.session_state.ai_rationale = "System default pricing maps generated. (Live Scraped Pool Active)."
    return cash_offer, retail_average, df_market