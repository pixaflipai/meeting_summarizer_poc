import os, json, sys, requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("RECALLAI_API_KEY")
REGION  = os.getenv("RECALLAI_REGION", "us-west-2")
assert API_KEY, "Set RECALLAI_API_KEY in .env"

BASE = f"https://{REGION}.recall.ai/api/v1"
HDRS = {"Authorization": f"Token {API_KEY}", "Content-Type": "application/json"}

def req_bot(meet_url: str, project_name: str, bot_name: str = "Pixabot") -> dict:
    """
    Request a Recall bot to join the meeting.
    We embed `project_name` into bot.metadata so the webhook can save
    the transcript into transcripts_projects/<project_name>/transcripts/.
    """
    payload = {
        "meeting_url": meet_url,
        "bot_name": bot_name,
        "metadata": {"project": project_name},  # <-- critical
        "recording_config": {
            "transcript": {"provider": {"meeting_captions": {}}}
        },
        "start_recording_on": "participant_join",
    }
    r = requests.post(f"{BASE}/bot/", headers=HDRS, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json()

def main():
    """CLI entrypoint: python create_bot.py <google_meet_url> <project_name> [bot_name]"""
    if len(sys.argv) < 3:
        print("Usage: python create_bot.py <google_meet_url> <project_name> [bot_name]")
        sys.exit(2)

    meet_url = sys.argv[1]
    project  = sys.argv[2]
    bot_name = sys.argv[3] if len(sys.argv) > 3 else "Pixabot"

    bot = req_bot(meet_url, project_name=project, bot_name=bot_name)
    print("BOT_ID:", bot.get("id"))

if __name__ == "__main__":
    main()