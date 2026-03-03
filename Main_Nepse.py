
import streamlit as st
import requests
import os

# Safely handle colab-only imports
try:
    from google.colab import userdata
except ImportError:
    userdata = None

st.title("🛠️ Final Connection Diagnostic")

st.subheader("1. Environment Variables Check")

try:
    # Try Streamlit secrets, then OS environment variables, then Colab secrets if available
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    
    if not url or not key and userdata:
        try:
            url = url or userdata.get("SUPABASE_URL")
            key = key or userdata.get("SUPABASE_KEY")
        except:
            pass
            
    st.write(f"Supabase URL found: {bool(url)}")
    st.write(f"Supabase Key found: {bool(key)}")
except Exception as e:
    st.error(f"Error accessing secrets: {e}")

st.subheader("2. Raw REST API Test")
if url and key:
    test_url = f"{url.rstrip('/')}/rest/v1/app_Files?select=*&limit=1"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(test_url, headers=headers)
        st.write(f"Response Code: {response.status_code}")
        if response.status_code == 200:
            st.success("Connection Successful! Table 'app_Files' is reachable.")
            st.json(response.json())
        else:
            st.error(f"Connection Failed: {response.text}")
    except Exception as e:
        st.error(f"Request Error: {e}")
else:
    st.warning("Missing credentials to perform diagnostic test.")
