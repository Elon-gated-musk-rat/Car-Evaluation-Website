import streamlit as st
from valuation_engine import generate_valuation
from database_worker import upload_lead

st.set_page_config(page_title="Instant Vehicle Valuation", page_icon="🚗")

if "step" not in st.session_state:
    st.session_state.step = 1

if st.session_state.step == 1:
    st.title("🚗 Get an Instant Offer for Your Car")
    
    col1, col2 = st.columns(2)
    with col1:
        year = st.selectbox("Year", list(range(2026, 2012, -1)))
        make = st.selectbox("Make", ["Honda", "Toyota", "Ford", "BMW", "Other"])
    with col2:
        model = st.text_input("Model Name", value="Civic")
        kilometers = st.number_input("Odometer (km)", min_value=0, max_value=500000, value=65000)
        
    condition = st.selectbox("Vehicle Condition", ["Excellent (No visible wear)", "Good (Minor scratches)", "Fair (Needs body work)", "Poor (Damaged)"])
    accidents = st.radio("Accident History?", ["No", "Yes (1 Minor)", "Yes (Severe / Multiple)"])
    
    if st.button("Calculate Current Valuation ➡️", use_container_width=True):
        with st.spinner("Analyzing live regional market conditions..."):
            offer, retail, df_comps = generate_valuation(year, make, model, kilometers, condition, accidents)
            st.session_state.results = {"offer": offer, "retail": retail, "df": df_comps}
            st.session_state.car_specs = {"year": year, "make": make, "model": model, "kilometers": kilometers, "condition": condition, "accidents": accidents}
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    res = st.session_state.results
    specs = st.session_state.car_specs
    
    st.title("📊 Your Market Evaluation")
    
    c1, c2 = st.columns(2)
    c1.metric("Direct Instant Cash Offer", f"${res['offer']:,} CAD")
    c2.metric("Average Retail Market Value", f"${res['retail']:,} CAD")
    
    with st.expander("🔎 View Local Market Reference Listings Used"):
        st.dataframe(res['df'], use_container_width=True, hide_index=True)
        
    st.markdown("---")
    st.subheader("Lock in this price & book a driveway vehicle pickup")
    
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
                st.error("Please fill out all contact fields.")
                
    if st.button("⬅️ Run Another Valuation"):
        st.session_state.step = 1
        st.rerun()

elif st.session_state.step == 3:
    st.balloons()
    st.success("🎉 Lead Successfully Transmitted to Cloud Systems!")
    if st.button("Process New Car Portfolio Calculation"):
        st.session_state.step = 1
        st.rerun()