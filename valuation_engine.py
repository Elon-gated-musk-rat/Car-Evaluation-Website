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
    Queries specialty auction rooms via Apify to scrape listings and 
    extracts contextual details like color, options, and packages.
    """
    listings = []
    apify_token = st.secrets.get("APIFY_TOKEN")
    if not apify_token:
        return pd.DataFrame(listings)
        
    apify_client = ApifyClient(apify_token)
    
    # Clean chassis markers for broad fallback searching
    clean_model = model.lower()
    clean_model = re.sub(r'\(.*?\)', '', clean_model)
    clean_model = clean_model.replace("w463", "").replace("e46", "").replace("e30", "").replace("g-class", "g").strip()
    
    search_string = f"{make} {clean_model}".strip()
    if not clean_model: 
        search_string = f"{make} {model}"

    # Common collector color mapping strings
    colors_pattern = r'(black|white|silver|grey|gray|red|blue|green|yellow|orange|brown|gold|beige)'
    # Common high-value optional packages
    options_keywords = ["chrono", "ceramic", "carbon", "amg", "m sport", "sunroof", "leather", "manual", "targa"]

    # --- ROOM 1: BRING A TRAILER ---
    try:
        bat_run = apify_client.actor("silentflow/bringatrailer-scraper").call(
            run_input={"searches": [search_string], "maxItems": 15}
        )
        for item in apify_client.dataset(bat_run["defaultDatasetId"]).iterate_items():
            title = item.get("title", "")
            raw_price = item.get("price", 0)
            mileage = item.get("mileage") or item.get("odometer", 0)
            
            # Context Parsing Engine
            combined_text = (title + " " + str(item.get("description", ""))).lower()
            color_match = re.search(colors_pattern, combined_text)
            detected_color = color_match.group(0).capitalize() if color_match else "Unspecified"
            
            found_opts = [opt.title() for opt in options_keywords if opt in combined_text]
            detected_options = ", ".join(found_opts) if found_opts else "Standard Specification"

            listings.append({
                "Source": "Bring a Trailer",
                "Title": title or f"{make} {model}",
                "Price (USD)": int(raw_price) if raw_price else 0,
                "Odometer": f"{int(mileage):,} mi" if mileage else "N/A",
                "Color": detected_color,
                "Detected Options": detected_options,
                "Status": str(item.get("status", "Closed")).capitalize()
            })
    except Exception:
        pass 

    # --- ROOM 2: CARS & BIDS ---
    try:
        cb_run = apify_client.actor("lulzasaur/carsandbids-scraper").call(
            run_input={"searchQueries": [search_string], "status": "closed", "maxResults": 10}
        )
        for item in apify_client.dataset(cb_run["defaultDatasetId"]).iterate_items():
            title = item.get("title", "")
            raw_price = item.get("price") or item.get("currentBid") or 0
            clean_price = re.sub(r'[^\d.]', '', str(raw_price)) if raw_price else "0"
            mileage = item.get("mileage") or item.get("odometer", 0)
            
            combined_text = (title + " " + str(item.get("equipment", ""))).lower()
            color_match = re.search(colors_pattern, combined_text)
            detected_color = color_match.group(0).capitalize() if color_match else "Unspecified"
            
            found_opts = [opt.title() for opt in options_keywords if opt in combined_text]
            detected_options = ", ".join(found_opts) if found_opts else "Standard Specification"

            listings.append({
                "Source": "Cars & Bids",
                "Title": title or f"{make} {model}",
                "Price (USD)": int(float(clean_price)) if clean_price else 0,
                "Odometer": f"{int(mileage):,} mi" if mileage else "N/A",
                "Color": detected_color,
                "Detected Options": detected_options,
                "Status": "Closed"
            })
    except Exception:
        pass

    if not listings:
        return pd.DataFrame(columns=["Source", "Title", "Price (USD)", "Odometer", "Color", "Detected Options", "Status"])
        
    return pd.DataFrame(listings)

def generate_valuation(year, make, model, kilometers, condition, provenance):
    """Calculates evaluation matrices using scraped data arrays or local baselines."""
    openai_key = st.secrets.get("OPENAI_API_KEY")
    ai_client = OpenAI(api_key=openai_key) if openai_key else None
    
    search_make = make
    search_model = model

    if ai_client:
        clean_prompt = f"""
        You are an automotive data parser. Take the following vehicle make and model input and normalize it into a clean keyword string.
        INPUT MAKE: {make} INPUT MODEL: {model}
        Return ONLY a minified JSON object with no markdown wrappers using exactly these two keys:
        {{"search_make": "Cleaned Make", "search_model": "Cleaned Model"}}
        """
        try:
            clean_res = ai_client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": clean_prompt}],
                temperature=0.0, response_format={"type": "json_object"}
            )
            clean_json = json.loads(clean_res.choices[0].message.content)
            search_make = clean_json.get("search_make", make)
            search_model = clean_json.get("search_model", model)
        except Exception:
            pass

    df_market = scrape_live_market_data(search_make, search_model, year)
    has_live_data = not df_market.empty and len(df_market[df_market["Price (USD)"] > 0]) >= 1
    
    if has_live_data:
        valid_prices = df_market[df_market["Price (USD)"] > 0]["Price (USD)"]
        average_usd = valid_prices.mean()
        bat_average_price = int(average_usd * 1.36) 
    else:
        bat_average_price = 0

    retail_average = bat_average_price if bat_average_price > 0 else 45000
    cash_offer = int(retail_average * 0.85)
    st.session_state.ai_rationale = "System default pricing maps generated. (Contextual Color/Option Matrix compiled)."
    return cash_offer, retail_average, df_market