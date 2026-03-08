import os
import requests
import streamlit as st

URBS_BASE_URL = "https://api.urbs.fr"
URBS_ATTRIBUTES = "chauffageurbs,energieurbs,jannatmin,dpeurbs"


def _get_urbs_key():
    return st.secrets.get("URBS_API_KEY", os.environ.get("URBS_API_KEY", ""))


def urbs_geocode(address):
    """Geocode an address via URBS and return the best IMOPE id, or None."""
    key = _get_urbs_key()
    if not key:
        return None
    try:
        resp = requests.get(
            f"{URBS_BASE_URL}/geocoder/search",
            params={"key": key, "value": address},
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if isinstance(results, list) and results:
                return results[0].get("id")
    except Exception as e:
        print(f"URBS geocode error: {e}")
    return None


def urbs_get_attributes(imope_id):
    """Fetch building attributes from URBS dashboard for a given IMOPE id."""
    key = _get_urbs_key()
    if not key or not imope_id:
        return None
    try:
        resp = requests.get(
            f"{URBS_BASE_URL}/dashboard",
            params={"key": key, "id": imope_id, "attributes": URBS_ATTRIBUTES},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            entry = data.get(imope_id, {})
            attrs = entry.get("attributes", {})

            chauffage = (attrs.get("chauffageurbs") or {}).get("value", "")
            energie = (attrs.get("energieurbs") or {}).get("value", "")
            annee = (attrs.get("jannatmin") or {}).get("value", "")

            dpe_raw = (attrs.get("dpeurbs") or {}).get("value", {})
            if isinstance(dpe_raw, dict):
                dpe = dpe_raw.get("dpe", "")
                ges = dpe_raw.get("ges", "")
            else:
                dpe = str(dpe_raw) if dpe_raw else ""
                ges = ""

            return {
                "chauffage": chauffage or "",
                "energie": energie or "",
                "annee": int(annee) if annee else None,
                "dpe": dpe,
                "ges": ges,
            }
    except Exception as e:
        print(f"URBS dashboard error: {e}")
    return None


def urbs_enrich_address(address):
    """Full pipeline: geocode then fetch attributes. Uses session cache."""
    cache_key = f"urbs_{address}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    imope_id = urbs_geocode(address)
    if not imope_id:
        st.session_state[cache_key] = None
        return None

    result = urbs_get_attributes(imope_id)
    st.session_state[cache_key] = result
    return result
