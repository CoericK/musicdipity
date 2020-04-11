from collections import defaultdict
import os
import sys

from flask import (
    Flask,
    redirect,
    request,
    render_template,
    session,
)
from flask_redis import FlaskRedis

import spotipy
from spotipy import (
    SpotifyOAuth,
)

import spotipy.util as util

# See .env.example for required environment variables
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

REDIS_URL = os.getenv("REDIS_URL")
redis_client = FlaskRedis(app, decode_responses=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("You must set a SECRET_KEY in .env")

app.secret_key = SECRET_KEY

SCOPE = "user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state"


def get_sp_oauth():
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        raise ValueError("You must set SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI")

    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE
    )
    return sp_oauth

@app.route("/", methods=["GET"])
def index():
    return render_template('index.html')


@app.route("/oauth/", methods=["GET"])
def oauth():
    if 'username' in session:
        return redirect('/welcome/')
    sp_oauth = get_sp_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)
    

@app.route("/callback/", methods=["GET"])
def oauth_callback():
    code = request.values.get("code")
    sp_oauth = get_sp_oauth()
    token_info = sp_oauth.get_access_token(code, check_cache=False)
    token = token_info['access_token']
    sp = spotipy.Spotify(auth=token)
    user = sp.current_user()
    username = user['id']
    redis_client.set("token:{}".format(username), token)
    session['username'] = username
    return redirect("/welcome/")
    

@app.route("/welcome/", methods=["GET"])
def welcome():
    if 'username' not in session:
        redirect('/index/')
    username = session.get('username')
    token = str(redis_client.get("token:{}".format(username)))
    sp = spotipy.Spotify(auth=token)
    print(token)
    recently_played = sp.current_user_recently_played(limit=50)
    return "<br/>".join(["{} - {}: {}".format(item["track"]["artists"][0]["name"], item["track"]["name"], item["played_at"]) for item in recently_played["items"]])


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
