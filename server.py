from collections import defaultdict
import json
import os
import sys

from flask import (
    Flask,
    redirect,
    request,
    render_template,
    send_from_directory,
    session,
)
from flask_redis import FlaskRedis

import spotipy
from spotipy import (
    is_token_expired,
    SpotifyOAuth,

)

import spotipy.util as util

# See .env.example for required environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

app.config['REDIS_URL'] = os.getenv("REDIS_URL")

redis_client = FlaskRedis(app, decode_responses=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("You must set a SECRET_KEY in .env")

app.secret_key = SECRET_KEY

SCOPE = "user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state"


class MusicdipityAuthError(Exception):
    pass

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


def get_existing_user_access_token(username):
    """Fetch token from Redis for existing user.

    If the access token is not yet expired, we'll return that.
    If it is, we'll refresh the token, update the access token and return that.
    """
    token_info_json = redis_client.get("token:{}".format(username))
    if not token_info_json:
        raise MusicdipityAuthError("Tried to get token for unknown user {}".format(username))
    try:
        token_info = json.loads(token_info_json)
    except:
        raise MusicdipityAuthError("Badly formatted token for user {}".format(username))
    if is_token_expired(token_info):
        sp_oauth = get_sp_oauth()
        token_info = sp_oauth.refresh_access_token(
            token_info["refresh_token"]
        )
        print("Refreshed user access token")
        token_json = json.dumps(token_info)
        redis_client.set("token:{}".format(username), token_json)

    return token_info["access_token"]


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
    # TODO (2020-04-11) Deprecation warning: we won't be able to get this as a dict soon)
    # https://github.com/plamere/spotipy/blob/master/spotipy/oauth2.py#L133
    token_info = sp_oauth.get_access_token(code, check_cache=False)
    token_json = json.dumps(token_info)
    token = token_info['access_token']
    sp = spotipy.Spotify(auth=token)
    user = sp.current_user()
    username = user['id']
    if username:
        redis_client.set("token:{}".format(username), token_json)
        session['username'] = username
    else:
        raise Exception
    return redirect("/welcome/")
    

@app.route("/welcome/", methods=["GET"])
def welcome():
    if 'username' not in session:
        redirect('/index/')
    username = session.get('username')
    try:
        token = get_existing_user_access_token(username)
    except MusicdipityAuthError as e:
        print("Issue with token, let's reset and try again...")
        print(e)
        redis_client.delete("token:{}".format(username))
        del session['username']
        redirect('/oauth/')
    sp = spotipy.Spotify(auth=token)
    try:
        user = sp.current_user()
    except spotipy.client.SpotifyException:
        del session['username']
        return redirect('/oauth/')
    recently_played = sp.current_user_recently_played(limit=50)
    recently_played_list = ["{} - {}: {}".format(item["track"]["artists"][0]["name"], item["track"]["name"], item["played_at"]) for item in recently_played["items"]]
    return render_template("welcome.html", user=user, recently_played=recently_played_list)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/images/favicon'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')
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
