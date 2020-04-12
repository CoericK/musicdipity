import json
import os
import sys
from collections import defaultdict

import spotipy
import spotipy.util as util
# See .env.example for required environment variables
from dotenv import load_dotenv
from flask import (Flask, redirect, render_template, request,
                   send_from_directory, session)
from flask_redis import FlaskRedis
from spotipy import SpotifyOAuth, is_token_expired

from musicdipity.exceptions import MusicdipityAuthError
from musicdipity.spotify_utils import (get_sp_oauth, get_existing_user_access_token)

load_dotenv()

app = Flask(__name__)

app.config['REDIS_URL'] = os.getenv("REDIS_URL")

redis_client = FlaskRedis(app, decode_responses=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("You must set a SECRET_KEY in .env")

app.secret_key = SECRET_KEY

SCOPE = "user-read-email,user-top-read,user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state,playlist-read-collaborative,playlist-modify-public"

# TODO (2020-04-11) - Refactor: Refactor project into an module with helper files


##############################################################################################
# Twilio helpers
##############################################################################################
def get_twilio_client():
    return Client(os.environ.get('TWILIO_ACCOUNT_SID'), os.environ.get('TWILIO_AUTH_TOKEN'))


def send_sms(to_number, from_number, body, media_url=None):
    """Using our caller's number and the number they called, send an SMS."""
    client = get_twilio_client()
    if media_url is None:
        media_url = []
    try:
        client.messages.create(
            body=body,
            from_=from_number,
            to=to_number,
            media_url=media_url,
        )
    except TwilioRestException as exception:
        # Check for invalid mobile number error from Twilio
        if exception.code == 21614:
            print("Uh oh, looks like this caller can't receive SMS messages.")


##############################################################################################
# Routes
##############################################################################################
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
        print("Signed up new user {}! Storing token to Redis.".format(username))
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
        del session['username']
        return redirect('/oauth/')
    sp = spotipy.Spotify(auth=token)
    try:
        user = sp.current_user()
    except spotipy.client.SpotifyException:
        del session['username']
        return redirect('/oauth/')
    recently_played = sp.current_user_recently_played(limit=50)
    recently_played_list = ["{} - {}: {}".format(item["track"]["artists"][0]["name"], item["track"]["name"], item["played_at"]) for item in recently_played["items"]]
    user_recent_artists = defaultdict(list)
    for item in recently_played['items']:
        user_recent_artists[item['track']['artists'][0]['name']].append(item['played_at'] + ': ' + item['track']['name'])

    return render_template("welcome.html", user=user, recently_played=recently_played_list)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/images/favicon'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
