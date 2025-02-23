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

api_keys = requests.get(url, auth=HTTPBasicAuth(username, api_keys_pass)).json()

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


def upload_video(bucket_name: str, title: str, description: str) -> str:
    """
    Fetches latest uploaded screening and uploads it to the analysis service.
    """
    data = {
        "title": title,
        "description": description,
        "video_url": "",
        "start_millis": "",
        "end_millis": "",
        "callback_url": CALLBACK_URL
    }
    # Fetch file from bucket
    screenings_bucket = supabase.storage.from_(bucket_name)
    latest_screening = max(screenings_bucket.list(), key=lambda x: x['created_at'])
    latest_screening_name = latest_screening['name']
    latest_screening_file = screenings_bucket.download(latest_screening_name)
    # Upload to analysis service
    try:
        files = {
            "video": (latest_screening_name, latest_screening_file, "video/webm")
        }
        response = requests.post(URL_PREFIX, headers={"X-API-Key": IMENTIV_API_KEY}, data=data, files=files)
        response.raise_for_status()
        video_id = response.json()["id"]
        print(f"✅ Video uploaded successfully! Video ID: {video_id}")
        return video_id
    except Exception as e:
        print(f"❌ Video upload failed: {e}")
        raise

def poll_video_status(video_id):
    while True:
        response = requests.get(url=f"{URL_PREFIX}/{video_id}", headers={"X-API-Key": IMENTIV_API_KEY})
        if response.json().get('status') == 'completed':
            return response.json()
        else:
            print("Still processing. Retrying in 20 seconds.")
            print(response.json())
        time.sleep(180)

def fetch_personality_report(video_id, max_retries=30):
    # Request personality report
    request_url = f"{URL_PREFIX}/{video_id}/personality/request"
    request_headers = {"accept": "application/json", "X-API-Key": IMENTIV_API_KEY, "Content-Type": "application/x-www-form-urlencoded"}
    request_data = {"callback_url": CALLBACK_URL}
    response = requests.post(request_url, headers=request_headers, data=request_data)
    time.sleep(5)
    # Poll for the report status
    poll_url = f"{URL_PREFIX}/{video_id}/personality/"
    poll_headers = {"accept": "application/json", "X-API-Key": IMENTIV_API_KEY}
    retries = 0
    while retries < max_retries:
        response = requests.get(poll_url, headers=poll_headers)
        if response.status_code == 200 and response.json().get('status') == 'completed':
            return response.json()
        retries += 1
        time.sleep(20)

def convert_audio_emotions_line_to_dict(video_id:str,line):
    # no testing, we yolo
    return {
        "video_id": video_id,
        "Index": line[0],
        "start_time": line[1],
        "end_time": line[2],
        "speaker": line[3],
        "angry": line[4],
        "boredom": line[5],
        "disgust": line[6],
        "fear": line[7],
        "happy": line[8],
        "neutral": line[9],
        "sad": line[10],
        "surprise": line[11]
    }
    
def convert_video_emotions_line_to_dict(video_id:str,line):
    # no testing, we yolo
    return {
        "video_id": video_id,
        "video_time": line[0],
        "face_id": line[1],
        "face_name": line[2],
        "frame_index": line[3],
        "angry": line[4],
        "contempt": line[5],
        "disgust": line[6],
        "fear": line[7],
        "happy": line[8],
        "neutral": line[9],
        "sad": line[10],
        "surprise": line[11],
        "dominant_emotion": line[12],
        "arousal": line[13],
        "valence": line[14],
        "intensity": line[15]
    }

def fetch_report_file(video_id, max_retries=30):
    # Generate report file
    generate_url = f"{URL_PREFIX}/{video_id}/report/"
    headers = {
        "accept": "application/json",
        "X-API-Key": IMENTIV_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"callback_url": CALLBACK_URL}
    requests.post(generate_url, headers=headers, data=data)

    # Poll for the report file
    poll_url = f"{URL_PREFIX}/{video_id}/report/"
    retries = 0
    while retries < max_retries:
        response = requests.get(poll_url, headers=headers)
        if response.status_code == 200 and 'application/zip' in response.headers.get('Content-Type', ''):
            # Read the ZIP file in memory
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                # Process audio_emotions CSV
                audio_csv_name = f"audio_emotions_{video_id}.csv"
                with zip_ref.open(audio_csv_name) as audio_csv_file:
                    audio_reader = csv.reader(io.TextIOWrapper(audio_csv_file))
                    next(audio_reader)  # Skip the header row
                    audio_rows_to_insert = []
                    for line in audio_reader:
                        audio_rows_to_insert.append({
                            "video_id": video_id,
                            "Index": line[0],
                            "start_time": line[1],
                            "end_time": line[2],
                            "speaker": line[3],
                            "angry": line[4],
                            "boredom": line[5],
                            "disgust": line[6],
                            "fear": line[7],
                            "happy": line[8],
                            "neutral": line[9],
                            "sad": line[10],
                            "surprise": line[11]
                        })
                    # Insert audio emotions into Supabase
                    supabase.table("audio_emotions").insert(audio_rows_to_insert).execute()

                # Process video_analysis CSV
                video_csv_name = f"video_{video_id}_analysis.csv"
                with zip_ref.open(video_csv_name) as video_csv_file:
                    video_reader = csv.reader(io.TextIOWrapper(video_csv_file))
                    next(video_reader)  # Skip the header row
                    video_rows_to_insert = []
                    for line in video_reader:
                        video_rows_to_insert.append({
                            "video_id": video_id,
                            "video_time": line[0],
                            "face_id": line[1],
                            "face_name": line[2],
                            "frame_index": line[3],
                            "angry": line[4],
                            "contempt": line[5],
                            "disgust": line[6],
                            "fear": line[7],
                            "happy": line[8],
                            "neutral": line[9],
                            "sad": line[10],
                            "surprise": line[11],
                            "dominant_emotion": line[12],
                            "arousal": line[13],
                            "valence": line[14],
                            "intensity": line[15]
                        })
                    # Insert video analysis into Supabase
                    supabase.table("video_emotions").insert(video_rows_to_insert).execute()

                return "All CSV files processed and inserted into Supabase."
        retries += 1
        print(f"Retries count: {retries}")
        time.sleep(180)
    raise Exception("Max retries reached. Report file not available.")

def sklonujzioma_app():
    # Upload screening video to supabase
    video_id = upload_video('screening', "Latest Screening", "Interview with AI Casting Assistant.")
    # Wait once its uploaded
    poll_video_status(video_id)
    # Generate report on personality traits of the talent
    personality_report = fetch_personality_report(video_id)
    # Fetch detailed analysis of the screening
    fetch_report_file(video_id)