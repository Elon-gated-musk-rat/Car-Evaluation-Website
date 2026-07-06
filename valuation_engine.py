from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import re

def scrape_live_market_data(make, model, year):
    """Launches a headless browser mimicking human browsing behavior to gather market comps."""
    listings = []
    # Kijiji target classifieds string structure for Ontario
    target_url = f"https://www.kijiji.ca/b-cars-trucks/ontario/{make}-{model}-{year}/k0c174l9004"
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = context.new_page()
            page.goto(target_url, timeout=45000)
            page.wait_for_load_state("networkidle")
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            # Look for card structures matching standard web listings
            cards = soup.find_all(attrs={"data-testid": re.compile(r"ad-card|listing-card")})
            
            for card in cards[:5]: # Take top 5 closest regional items
                try:
                    price_txt = card.find(attrs={"data-testid": "ad-price"}).text
                    price_val = int(re.sub(r'[^\d]', '', price_txt))
                    
                    km_txt = card.find(text=re.compile(r'km|kilometres', re.IGNORECASE))
                    km_val = int(re.sub(r'[^\d]', '', km_txt)) if km_txt else 75000
                    
                    listings.append({"Source": "Kijiji Autos", "Title": f"{year} {make} {model}", "KM": km_val, "Price": price_val})
                except Exception:
                    continue
            browser.close()
        except Exception:
            pass # Fallback to synthetic logic if the scraping block fails or times out
            
    # Fallback simulation logic if scraper is blocked or returns empty arrays
    if not listings:
        base_anchor = {"Honda": 22000, "Toyota": 24000, "Ford": 19000, "BMW": 32000}.get(make, 18000)
        simulated_retail = base_anchor * max(1 - ((2026 - year) * 0.08), 0.2)
        for i in range(4):
            listings.append({"Source": "Market Mock Engine", "Title": f"{year} {make} {model}", "KM": 65000 + (i*5000), "Price": int(simulated_retail + (i * 450))})
            
    return pd.DataFrame(listings)

def generate_valuation(year, make, model, kilometers, condition, accidents):
    """Processes scraped retail figures down to a specific custom consumer trade-in quote."""
    df_market = scrape_live_market_data(make, model, year)
    retail_average = int(df_market["Price"].mean())
    
    adjusted_value = retail_average
    
    # Mileage depreciation metrics
    age = max(2026 - year, 1)
    expected_km = age * 20000
    if kilometers > expected_km:
        adjusted_value -= ((kilometers - expected_km) * 0.12)
        
    # Condition multiplier
    modifiers = {"Excellent (No visible wear)": 1.0, "Good (Minor scratches)": 0.90, "Fair (Needs body work)": 0.75, "Poor (Damaged)": 0.55}
    adjusted_value *= modifiers.get(condition, 0.90)
    
    # Accident deductions
    if accidents == "Yes (1 Minor)": adjusted_value -= 1500
    elif accidents == "Yes (Severe / Multiple)": adjusted_value -= 4500
    
    # Platforms like CarDoor take a percentage margin for risk, inspection, and profit
    cash_offer = int(adjusted_value * 0.84)
    return max(cash_offer, 500), retail_average, df_market