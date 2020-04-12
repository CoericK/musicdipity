import datetime
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

from twilio.twiml.messaging_response import MessagingResponse

from musicdipity.exceptions import MusicdipityAuthError
from musicdipity.spotify_utils import (get_sp_oauth, get_user_sp, get_user, get_existing_user_access_token,
                                       get_user_last_day_played, get_and_update_user_currently_playing,
                                       get_user_for_phone_number, enqueue_song_game_for_users,
                                       SCOPE)
from musicdipity.utils import humanize_ts

load_dotenv()

app = Flask(__name__)

app.config['REDIS_URL'] = os.getenv("REDIS_URL")

redis_client = FlaskRedis(app, decode_responses=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("You must set a SECRET_KEY in .env")

app.secret_key = SECRET_KEY

##############################################################################################
# Register Template Filters
##############################################################################################

app.jinja_env.filters['humanize'] = humanize_ts


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
        sp = get_user_sp(username)
    except MusicdipityAuthError as e:
        print("Issue with token, let's reset and try again...")
        print(e)
        del session['username']
        return redirect('/oauth/')

    try:
        user = get_user(username)
    except spotipy.client.SpotifyException:
        del session['username']
        return redirect('/oauth/')
    
    recently_played = get_user_last_day_played(username)

    currently_playing = get_and_update_user_currently_playing(username)
    return render_template("welcome.html", user=user, recently_played=recently_played, currently_playing=currently_playing)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/images/favicon'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/text-reply/', methods=["POST"])
def text_reply():
    sender = request.values.get('From')
    body = request.values.get('Body')
    print("Got a text from sender: {}!".format(sender))
    print(body)

    resp = MessagingResponse()
    print("let the games begin!")
    print(sender)
    user = get_user_for_phone_number(sender)
    print(user)
    if not user:
        resp.message("Sorry, there's not an active game afoot! Please wait till we text you!")
        return str(resp)
    game = redis_client.get("game:{}".format(user))
    if not game:
        resp.message("Sorry, there's not an active game afoot! Please wait till we text you!")
        return str(resp)
    print(game)
    other_user, artist_id = game.split('||', 1)
    print(other_user)
    print(artist_id)
    # TODO move this to a task
    other_user_info = get_user(user)
    if body.upper().strip() == 'Y':
        resp.message("{} accepts your challenge. IT IS ON TILL THE BREAK OF DAWN. I will play the same song from both your Spotifys starting at the same time. Make sure your volume is on and NOT PEEKING AT THE TRACK NAME (Honor Code)! First person to text the correct answer to me wins!".format(other_user_info['display_name']))
        resp.message("Okay, in 5...4...3....2...1... GO! 🎬")
        enqueue_song_game_for_users(user, other_user, artist_id)
    else:
        resp.message("Some good news and some bad news. The good news is: THAT'S CORRECT! The bad news...{} beat you to the punch!".format(other_user_info['display_name']))
    return str(resp)
    # is user part of an ongoing game?
    # get the game and make sure it's not over

    # start game

    # check answer
        # correct answer
        # incorrect answer
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
