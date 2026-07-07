import streamlit as st
import valuation_engine as ve

st.set_page_config(page_title="Collector Car Appraisal Engine", layout="wide")

st.title("Collector & Classic Car Evaluation Engine")
st.subheader("Powered by Live Auction Sold History Matrix")

# --- SIDEBAR: GUIDANCE SYSTEM ---
with st.sidebar:
    st.header("Search Best Practices")
    st.markdown("""
    To get the most accurate matches from premium enthusiast databases, combine our verified brand names with classic chassis labels:
    
    * **Mercedes-Benz:** Type your generation or sub-model (e.g., *G500 W463*, *G55 AMG*, *E55*)
    * **Porsche:** Use generation codes for precision (e.g., *997 Turbo*, *993 Carrera*, *964*)
    * **BMW:** Use structural chassis designations (e.g., *E30 M3*, *E46 M3*, *E39 M5*)
    * **American Muscle:** Keep it simple with classic nameplates (e.g., *Corvette C2*, *Mustang Fastback*)
    """)

# --- DATA INPUT PIPELINE ---
col1, col2, col3 = st.columns(3)

with col1:
    # Dynamically loads the massive alphabetized brand array from catalog.json
    # Streamlit natively allows users to either click-and-scroll OR type to instantly filter keys
    brand_options = ve.get_catalog_makes()
    selected_make = st.selectbox(
        "Vehicle Make", 
        options=brand_options, 
        index=brand_options.index("Mercedes-Benz") if "Mercedes-Benz" in brand_options else 0,
        help="Scroll through the verified brand index or type to search instantly."
    )

with col2:
    # Left unconstrained so enthusiasts can type highly specific sub-models or custom modifications
    selected_model = st.text_input(
        "Vehicle Model / Chassis Code", 
        placeholder="e.g., G500 W463, M3 E46, 911 Turbo"
    ).strip()

with col3:
    selected_year = st.number_input("Model Year", min_value=1900, max_value=2026, value=2002)

# --- USER CONDITION DEFINITIONS ---
col4, col5 = st.columns(2)
with col4:
    condition = st.selectbox(
        "Condition Scale", 
        ["Concours (Condition 1)", "Excellent (Condition 2)", "Good (Condition 3)", "Fair (Condition 4)"]
    )
with col5:
    provenance = st.selectbox(
        "Provenance / Documentation",
        ["All Original Numbers-Matching", "Period-Correct Restored", "Older Restoration", "Modified / Resto-mod", "Prior Accident History"]
    )

kilometers = st.number_input("Odometer Reading (KM)", min_value=0, value=50000)

if st.button("Generate Master Collector Appraisal"):
    if not selected_model:
        st.error("Please provide a vehicle Model or Chassis designation to query historical database pools.")
    else:
        with st.spinner(f"Scraping active and completed transaction maps for {selected_year} {selected_make} {selected_model}..."):
            cash_offer, retail_avg, df_market = ve.generate_valuation(
                selected_year, selected_make, selected_model, kilometers, condition, provenance
            )
            
            st.success("Appraisal Complete!")
            
            # Display Core Financial Matrices
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Fair Collector Retail Value (CAD)", f"${retail_avg:,}")
            with m2:
                st.metric("Dynamic Dealer Buyout Offer (CAD)", f"${cash_offer:,}")
                
            st.info(st.session_state.ai_rationale)
            
            st.subheader("Live Market Aggregation Pool")
            st.dataframe(df_market)