import streamlit as st
import valuation_engine as ve

st.set_page_config(page_title="Collector Car Appraisal Engine", layout="wide")

st.title("Collector & Classic Car Evaluation Engine")
st.subheader("Powered by Live Auction Sold History Matrix")

# --- SIDEBAR: OPTIONS AND SPECIFICATION FILTERS ---
with st.sidebar:
    st.header("Additional Information Filters")
    st.markdown("Use these toggles to drill down into structural specifications after running your baseline query.")
    
    target_color = st.selectbox(
        "Filter by Exterior Color Family",
        ["All Colors", "Black", "White", "Silver", "Grey", "Red", "Blue", "Green", "Yellow"]
    )
    
    require_premium_packages = st.checkbox("Highlight Rarest Options (e.g., Carbon, Ceramic, Manual)")

# --- DATA INPUT PIPELINE ---
col1, col2, col3 = st.columns(3)

with col1:
    brand_options = ve.get_catalog_makes()
    selected_make = st.selectbox("Vehicle Make", options=brand_options, index=brand_options.index("Mercedes-Benz") if "Mercedes-Benz" in brand_options else 0)

with col2:
    selected_model = st.text_input("Vehicle Model / Chassis Code", placeholder="e.g., G500, M3, 911 Turbo").strip()

with col3:
    selected_year = st.number_input("Model Year", min_value=1900, max_value=2026, value=2002)

col4, col5 = st.columns(2)
with col4:
    condition = st.selectbox("Condition Scale", ["Concours (Condition 1)", "Excellent (Condition 2)", "Good (Condition 3)", "Fair (Condition 4)"])
with col5:
    provenance = st.selectbox("Provenance / Documentation", ["All Original Numbers-Matching", "Period-Correct Restored", "Older Restoration", "Modified / Resto-mod", "Prior Accident History"])

kilometers = st.number_input("Odometer Reading (KM)", min_value=0, value=50000)

if st.button("Generate Master Collector Appraisal"):
    if not selected_model:
        st.error("Please provide a vehicle Model label.")
    else:
        with st.spinner(f"Scraping asset data and mapping variant specifications..."):
            cash_offer, retail_avg, df_market = ve.generate_valuation(
                selected_year, selected_make, selected_model, kilometers, condition, provenance
            )
            
            st.success("Appraisal Mapping Completed!")
            
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Fair Collector Retail Value (CAD)", f"${retail_avg:,}")
            with m2:
                st.metric("Dynamic Dealer Buyout Offer (CAD)", f"${cash_offer:,}")
            
            st.info(st.session_state.get("ai_rationale", "Asset verification complete."))
            
            st.session_state.raw_scraped_data = df_market

# --- DYNAMIC SPECIFICATION COMPILATION PAGE WITH HYPERLINKS ---
if "raw_scraped_data" in st.session_state:
    df_filtered = st.session_state.raw_scraped_data.copy()
    
    if target_color != "All Colors":
        df_filtered = df_filtered[df_filtered["Color"] == target_color]
        
    if require_premium_packages:
        df_filtered = df_filtered[df_filtered["Detected Options"] != "Standard Specification"]

    st.markdown("---")
    st.subheader("📋 Additional Information & Build Details Page")
    
    tab1, tab2 = st.tabs(["🎯 Filtered Comparable Pool", "📊 Color Distribution Analysis"])
    
    with tab1:
        if not df_filtered.empty:
            # Render dataframe with active links utilizing st.column_config
            st.data_editor(
                df_filtered,
                column_config={
                    "Listing Link": st.column_config.LinkColumn(
                        "Listing Link",
                        help="Click to open the historical auction directly on the platform",
                        validate=r"^https://.*",
                        display_text="View Listing 🔗"
                    )
                },
                disabled=True,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("No live records match this hyper-specific Color or Equipment combo. Broaden your sidebar parameters.")
            
    with tab2:
        if not st.session_state.raw_scraped_data.empty:
            color_counts = st.session_state.raw_scraped_data["Color"].value_counts()
            st.bar_chart(color_counts)
        else:
            st.info("Insufficient variance rows to chart.")