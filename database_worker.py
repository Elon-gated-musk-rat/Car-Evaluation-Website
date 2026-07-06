import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase_client() -> Client:
    """Safely connects to your cloud database using st.secrets configuration."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def upload_lead(car_specs, contact_info, final_offer):
    """Pushes a full data package to the cloud PostgreSQL database."""
    db = get_supabase_client()
    payload = {
        "year": int(car_specs["year"]),
        "make": str(car_specs["make"]),
        "model": str(car_specs["model"]),
        "kilometers": int(car_specs["kilometers"]),
        "condition": str(car_specs["condition"]),
        "accidents": str(car_specs["accidents"]),
        "estimated_value": float(final_offer),
        "client_name": str(contact_info["name"]),
        "client_email": str(contact_info["email"]),
        "client_phone": str(contact_info["phone"])
    }
    try:
        db.table("car_leads").insert(payload).execute()
        return True
    except Exception as e:
        st.error(f"Database sync failed: {e}")
        return False