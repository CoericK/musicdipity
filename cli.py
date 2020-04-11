import sys

import spotipy
import spotipy.util as util

# See .env.example for required environment variables
from dotenv import load_dotenv

load_dotenv()

SCOPE = "user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state"


def get_auth_prompt_and_recent_tracks():
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        print("Usage: %s username" % (sys.argv[0],))
        sys.exit()

    token = util.prompt_for_user_token(username, SCOPE)
    print(token)
    if token:
        sp = spotipy.Spotify(auth=token)
        print(sp.current_user())
        results = sp.current_user_recently_played(limit=50)
        for item in results["items"]:
            track = item["track"]
            print(track["name"] + " - " + track["artists"][0]["name"])
    else:
        print("Can't get token for", username)


get_auth_prompt_and_recent_tracks()