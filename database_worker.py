"""
Handles persisting valuation leads to Supabase.
"""
import logging
import re

import streamlit as st
from supabase import Client, create_client

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[\d\s()+\-]{7,20}$")


@st.cache_resource
def get_supabase_client() -> Client:
    """Connects to the Supabase project using st.secrets configuration."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def validate_contact(contact_info):
    """Returns a list of validation error messages (empty list means valid)."""
    errors = []
    if not contact_info.get("name", "").strip():
        errors.append("Name is required.")
    if not EMAIL_RE.match(contact_info.get("email", "").strip()):
        errors.append("Please enter a valid email address.")
    if not PHONE_RE.match(contact_info.get("phone", "").strip()):
        errors.append("Please enter a valid phone number.")
    return errors


def upload_lead(car_specs, contact_info, final_offer):
    """Pushes a validated lead package to the Supabase car_leads table.
    Returns True on success, False on validation or database failure."""
    errors = validate_contact(contact_info)
    if errors:
        for err in errors:
            st.error(err)
        return False

    db = get_supabase_client()
    payload = {
        "year": int(car_specs["year"]),
        "make": str(car_specs["make"]),
        "model": str(car_specs["model"]),
        "kilometers": int(car_specs["kilometers"]),
        "condition": str(car_specs["condition"]),
        "accidents": str(car_specs["accidents"]),
        "estimated_value": float(final_offer),
        "client_name": str(contact_info["name"]).strip(),
        "client_email": str(contact_info["email"]).strip().lower(),
        "client_phone": str(contact_info["phone"]).strip(),
    }
    try:
        # Guard against accidental duplicate submissions (same email, same day, same car).
        existing = (
            db.table("car_leads")
            .select("id")
            .eq("client_email", payload["client_email"])
            .eq("make", payload["make"])
            .eq("model", payload["model"])
            .eq("year", payload["year"])
            .execute()
        )
        if existing.data:
            st.warning("We already have a valuation request for this vehicle and email on file. Our team will be in touch.")
            return True

        db.table("car_leads").insert(payload).execute()
        return True
    except Exception as e:
        logger.error("Database sync failed: %s", e)
        st.error("We couldn't save your valuation request right now. Please try again in a moment.")
        return False
