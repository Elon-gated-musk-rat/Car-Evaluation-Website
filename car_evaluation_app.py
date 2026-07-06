import streamlit as st
from valuation_engine import generate_valuation
from database_worker import upload_lead

st.set_page_config(page_title="Instant Vehicle Valuation", page_icon="🚗", layout="centered")

# Maintain global user step progression states
if "step" not in st.session_state:
    st.session_state.step = 1

# --- STEP 1: VEHICLE CRITERIA CAPTURE ---
if st.session_state.step == 1:
    st.title("🚗 Get an Instant Offer for Your Car")
    st.write("Complete the details below to evaluate your car based on live local Ontario listings.")
    
    col1, col2 = st.columns(2)
    with col1:
        year = st.selectbox("Year", list(range(2026, 2012, -1)))
        make = st.selectbox("Make", ["Honda", "Toyota", "Ford", "BMW", "Other"])
    with col2:
        model = st.text_input("Model (e.g. Civic, Corolla)", value="Civic")
        kilometers = st.number_input("Current Odometer Reading (km)", min_value=0, max_value=500000, value=65000)
        
    condition = st.selectbox("Vehicle Condition Profile", ["Excellent (No visible wear)", "Good (Minor scratches)", "Fair (Needs body work)", "Poor (Damaged)"])
    accidents = st.radio("Has this car encountered any reported history or accidents?", ["No", "Yes (1 Minor)", "Yes (Severe / Multiple)"])
    
    if st.button("Calculate Current Valuation ➡️", use_container_width=True):
        with st.spinner("Analyzing active local marketplace classified listings..."):
            offer, retail, df_comps = generate_valuation(year, make, model, kilometers, condition, accidents)
            st.session_state.results = {"offer": offer, "retail": retail, "df": df_comps}
            st.session_state.car_specs = {"year": year, "make": make, "model": model, "kilometers": kilometers, "condition": condition, "accidents": accidents}
            st.session_state.step = 2
            st.rerun()

# --- STEP 2: METRIC COMPARISON & REGISTER INTEREST ---
elif st.session_state.step == 2:
    res = st.session_state.results
    specs = st.session_state.car_specs
    
    st.title("📊 Your Market Evaluation")
    
    c1, c2 = st.columns(2)
    c1.metric("Direct Instant Cash Offer", f"${res['offer']:,} CAD", help="Guaranteed buyout offer from our platform.")
    c2.metric("Average Estimated Retail Value", f"${res['retail']:,} CAD", help="Average consumer pricing found on active classified listings.")
    
    with st.expander("🔎 View Active Market Reference Listings Traversed"):
        st.dataframe(res['df'], use_container_width=True, hide_index=True)
        
    st.markdown("---")
    st.subheader("Lock in this price & book a driveway vehicle handover")
    
    with st.form("contact_form"):
        name = st.text_input("Your Full Name")
        email = st.text_input("Email Address")
        phone = st.text_input("Mobile Phone")
        
        if st.form_submit_button("Confirm & Save Valuation Lead", use_container_width=True):
            if name and email and phone:
                contact = {"name": name, "email": email, "phone": phone}
                if upload_lead(specs, contact, res['offer']):
                    st.session_state.step = 3
                    st.rerun()
            else:
                st.error("Please fill out all contact fields to save your offer safely.")
                
    if st.button("⬅️ Run Another Valuation"):
        st.session_state.step = 1
        st.rerun()

# --- STEP 3: PIPELINE COMPLETION SUCCESS ---
elif st.session_state.step == 3:
    st.balloons()
    st.success("🎉 Lead Successfully Transmitted to Cloud Systems!")
    st.write("An inspector will verify these data parameters and contact you to arrange instant digital payout.")
    if st.button("Process New Car Portfolio Calculation"):
        st.session_state.step = 1
        st.rerun()