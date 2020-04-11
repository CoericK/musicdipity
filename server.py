from collections import defaultdict
import os
import sys

from flask import (
    Flask,
    redirect,
    request,
    render_template,
)

import spotipy
from spotipy import (
    SpotifyOAuth,
)

import spotipy.util as util

# See .env.example for required environment variables
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SCOPE = "user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state"


@app.route("/", methods=["GET"])
def index():
    return render_template('index.html')


@app.route("/oauth/", methods=["GET"])
def oauth():
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)
    


@app.route("/callback/", methods=["GET"])
def oauth_callback():
    code = request.values.get("code")
    token_info = sp_oauth.get_access_token(code)
    print(token_info['access_token'])

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
        results = sp.current_user_recently_played(limit=50)
        for item in results["items"]:
            track = item["track"]
            print(track["name"] + " - " + track["artists"][0]["name"])
    else:
        print("Can't get token for", username)


# get_auth_prompt_and_recent_tracks()

# RICKY_TOKEN = os.environ['RICKY_TOKEN']
# DAVID_TOKEN = os.environ['DAVID_TOKEN']

# TOKENS = {
#     'rickyyean': RICKY_TOKEN,
#     'dtran320': DAVID_TOKEN,
# }

# user_recent_artists = {}

# for user, token in TOKENS.items():
#     sp = spotipy.Spotify(auth=token)
#     recent = sp.current_user_recently_played(limit=50)
#     user_recent_artists[user] = defaultdict(list)
#     for item in recent['items']:
#         user_recent_artists[user][item['track']['artists'][0]['name']].append(item['played_at'] + ': ' + item['track']['name'])

# overlap = set(user_recent_artists['rickyyean'].keys()) & set(user_recent_artists['dtran320'].keys())

# for artist in overlap:
#     print(user_recent_artists['rickyyean'][artist])
#     print(user_recent_artists['dtran320'][artist])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
