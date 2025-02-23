import requests
from requests.auth import HTTPBasicAuth
import os
import time
import zipfile
import csv
import io
from supabase.lib.client_options import ClientOptions

# API URL
url = "https://11labs-hackathon-tokens.vercel.app/api/tokens"
api_keys_pass = os.environ.get('API_KEYS_PASS')

# Add to secrets as well
username = "sklonujzioma"

def get_keys():
    return requests.get(url, auth=HTTPBasicAuth(username, api_keys_pass)).json()
api_keys = get_keys()

# Constants
SUPABASE_SERVICE_KEY = api_keys.get('supabaseServiceKey')
SUPABASE_URL = api_keys.get('supabaseUrl')
IMENTIV_API_KEY = api_keys.get('imentiv')
ELEVENLABS_API_KEY = api_keys.get('elevenLabs')
# add these later
CALLBACK_URL = "https://silly-doctor-72.webhook.cool" 
URL_PREFIX = "https://api.imentiv.ai/v1/videos"
# Define global headers
HEADERS = {
    "accept": "application/json",
    "X-API-Key": IMENTIV_API_KEY
}
     

from supabase import create_client, Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

