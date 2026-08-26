"""
BoboPresent YouTube uploader — uploads an exported video via the YouTube Data API.
Requires the user's own Google OAuth client (client_secret.json) + one-time
consent. AI can draft the title/description via the shared AIClient.
"""
import os
import sys

sys.path.insert(0, "/usr/share/bobo-office")
CLIENT_SECRET = os.path.expanduser("~/.config/bobo-office/youtube_client_secret.json")
TOKEN = os.path.expanduser("~/.config/bobo-office/youtube_token.json")


def configured() -> bool:
    return os.path.exists(CLIENT_SECRET)


def draft_metadata(topic: str) -> dict:
    """Draft title/description/tags with the local model (best-effort)."""
    try:
        from shared.ai_client import AIClient
        ai = AIClient()
        if ai.available():
            title = ai.ask("Un titlu scurt de YouTube pentru: %s" % topic).splitlines()[0][:100]
            desc = ai.ask("O descriere scurta de YouTube pentru: %s" % topic)
            return {"title": title, "description": desc, "tags": topic.split()[:8]}
    except Exception:
        pass
    return {"title": topic[:100], "description": topic, "tags": topic.split()[:8]}


def upload(video_path: str, title: str, description: str = "", tags=None,
           privacy: str = "private") -> str:
    """Upload the video. Returns the video URL or an error/instruction string."""
    if not configured():
        return ("[YouTube neconfigurat] Pune client_secret.json în %s "
                "(Google Cloud → YouTube Data API v3 → OAuth)." % CLIENT_SECRET)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        if os.path.exists(TOKEN):
            creds = Credentials.from_authorized_user_file(TOKEN, scopes)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, scopes)
            creds = flow.run_local_server(port=8766)
            open(TOKEN, "w").write(creds.to_json())
        yt = build("youtube", "v3", credentials=creds)
        body = {"snippet": {"title": title, "description": description, "tags": tags or []},
                "status": {"privacyStatus": privacy}}
        media = MediaFileUpload(video_path, resumable=True)
        resp = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        return "https://youtu.be/%s" % resp["id"]
    except Exception as e:
        return "[Upload eșuat] %s" % e
