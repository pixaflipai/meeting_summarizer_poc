# create_bot.py
import os, json, sys, requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RECALLAI_API_KEY")
REGION  = os.getenv("RECALLAI_REGION", "us-west-2")
assert API_KEY, "Set RECALLAI_API_KEY in .env"

BASE = f"https://{REGION}.recall.ai/api/v1"
HDRS = {"Authorization": f"Token {API_KEY}", "Content-Type": "application/json"}

def main():
    if len(sys.argv) < 2:
        print("Usage: python create_bot.py <google_meet_url>")
        sys.exit(2)
    meet_url = sys.argv[1]

    payload = {
        "meeting_url": meet_url,
        "bot_name": "SummarizerBot",
        "recording_config": {
            "transcript": { "provider": { "meeting_captions": {} } }
        },
        "start_recording_on": "participant_join"
    }
    r = requests.post(f"{BASE}/bot/", headers=HDRS, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    bot = r.json()
    print("BOT_ID:", bot.get("id"))

if __name__ == "__main__":
    main()