import io
import json
from jinja2 import Template
import pandas as pd
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client
from elevenlabs import ElevenLabs
from .sklonuj_zioma import get_keys

#TODO - these two should be arguments given as input to the script
CONVERSATION_ID = "YzI93GFnFsCOo924uKlo"
VIDEO_ID = "408bef4d-0f92-4dae-aa5b-f556acaa037f"
    
KEYS = get_keys()
supabase = create_client('https://coltpedcrfibsozxvgvu.supabase.co', KEYS["supabase"])    
eleven_labs_client = ElevenLabs(api_key=KEYS["elevenLabs"])
open_ai_client = OpenAI(api_key=KEYS["openai"])

# GETTING THE CONVERSATION 
conversation = eleven_labs_client.conversational_ai.get_conversation(
    conversation_id=CONVERSATION_ID
)

response = (
    supabase
    .storage
    .from_("transcription")
    .upload(
        f"{CONVERSATION_ID}.json",
        io.BytesIO(json.dumps(conversation.dict()).encode("utf-8")).read()
    )
)

# EXTRACTING INFO FROM THE CONVERSATION
dynamic_variables = conversation.dict()['conversation_initiation_client_data']['dynamic_variables']

MOVIE_TITLE = dynamic_variables["movie_title"]
MOVIE_GENRE = dynamic_variables["movie_genre"]
SETTING = dynamic_variables["scene_setting"]
SCENE_CONTEXT = dynamic_variables["scene_context"]
CHARACTERS = dynamic_variables["characters"]
SCENE_DESCRIPTION = dynamic_variables["scene_description"]
ADDITIONONAL_INFO = dynamic_variables["additional_info"]

USER_NAME = dynamic_variables["user_name"]
SCREENPLAY_TEXT = dynamic_variables["screenplay_text"]

USER_ROLE = dynamic_variables["user_role"]
AGENT_ROLE = dynamic_variables["agent_role"]

# EXTRACTING TRANSCRIPTION FROM THE CONVERSATION
duration = conversation.dict()['metadata']['call_duration_secs']

transcript = pd.DataFrame(conversation.dict()["transcript"])[["role","message","time_in_call_secs"]]
transcript['role'] = transcript['role'].apply(lambda x: x.upper())
transcript['role'] = transcript['role'].apply(lambda x: "ACTOR" if x == "USER" else x)
transcript['time_in_call_secs_end'] = transcript['time_in_call_secs'].shift(-1).fillna(duration).astype(int)

# AUDIO
response = (
    supabase.table("audio_emotions")
    .select("*")
    .eq("video_id", VIDEO_ID)
    .execute()
)
audio_emotions = pd.DataFrame(response.data)
audio_emotions["start_time"] = audio_emotions["start_time"] / 1000
audio_emotions["end_time"] = audio_emotions["end_time"] / 1000

# VIDEO
def _timestamp_to_seconds(timestamp: str) -> float:
    hh, mm, ss, ms = map(int, timestamp.split(":"))
    return hh * 3600 + mm * 60 + ss + ms / 1000

response = (
    supabase.table("video_emotions")
    .select("*")
    .eq("video_id", VIDEO_ID)
    .execute()
)
video_emotions = pd.DataFrame(response.data)


video_emotions["video_time_in_seconds"] = video_emotions["video_time"].apply(_timestamp_to_seconds)
video_emotions = video_emotions.sort_values('video_time_in_seconds') 


emotion_columns = ['angry', 'contempt', 'disgust', 'fear', 'happy', 'neutral', 'sad', 'surprise', 'arousal', 'valence', 'intensity']

video_emotions_per_line = []
for _, line in transcript.iterrows():
    emotions_mean = (
         video_emotions
         .query(f"{line['time_in_call_secs']} <= video_time_in_seconds <= {line['time_in_call_secs_end']}")
        [emotion_columns].mean()
    )
    
    emotions = {col: emotions_mean[col] for col in emotion_columns if emotions_mean[col] > 0.1}  
    sorted_emotions = sorted(emotions, key=emotions.get, reverse=True)  
    video_emotions_per_line.append(', '.join(sorted_emotions))

# JOINING EMOTIONS TO TRANSCRIPT
# VIDEO
transcript = pd.concat([transcript,pd.DataFrame({"video_emotions":video_emotions_per_line})], axis=1)
#TODO - implement the connection by sentence
transcript = pd.concat([transcript,pd.DataFrame({"voice_emotions":video_emotions_per_line})], axis=1)

TRANSCRIPT = "\n".join([f"{line['role']}: {line['message']} (Vision: {line['video_emotions']} ; Voice: {line['voice_emotions']})" for _, line in transcript.iterrows()])

# PERSONALITY
response = (
    supabase.table("personality")
    .select("*")
    .eq("video_id", VIDEO_ID)
    .execute()
)
personality = pd.DataFrame(response.data)

personality_values = personality.drop(columns=['id','video_id']).to_dict(orient='records')[0]
PERSONALITY = f"Extraversion: {personality_values['extraversion']*100:.0f}%, Neuroticism: {personality_values['neuroticism']*100:.0f}%, Agreeableness: {personality_values['agreeableness']*100:.0f}%, Conscientiousness: {personality_values['conscientiousness']*100:.0f}%, Openness: {personality_values['openness']*100:.0f}%"

# PROMPTING FOR CRITIQUE
developer_prompt = supabase.storage.from_("utils").download("/prompt_templates/developer.txt").decode("utf-8")

user_prompt_template = supabase.storage.from_("utils").download("/prompt_templates/user.txt").decode("utf-8")
user_prompt = Template(user_prompt_template).render({
    "USER_NAME": USER_NAME,
    "USER_ROLE": USER_ROLE,
    "MOVIE_TITLE": MOVIE_TITLE,
    "MOVIE_GENRE": MOVIE_GENRE,
    "SETTING": SETTING,
    "SCENE_CONTEXT": SCENE_CONTEXT,
    "SCENE_DESCRIPTION": SCENE_DESCRIPTION,
    "CHARACTERS": CHARACTERS,
    "ADDITIONONAL_INFO": ADDITIONONAL_INFO,
    "SCRIPT" : SCREENPLAY_TEXT,
    "TRANSCRIPTION": TRANSCRIPT,
    "PERSONALITY": PERSONALITY,
})

class Critique(BaseModel):
    score: int
    feedback: str
    

completion = open_ai_client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "developer",
            "content": developer_prompt},
        {
            "role": "user",
            "content": user_prompt
        }
    ],
    response_format=Critique
)

critique = json.loads(completion.choices[0].message.content)
response = (
    supabase
    .table("critique")
    .insert({
        'video_id' : VIDEO_ID,
        'conversation_id': CONVERSATION_ID,
        'score': critique['score'],
        'feedback': critique['feedback']
    })
    .execute()
)


