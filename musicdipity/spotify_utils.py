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

from .exceptions import MusicdipityAuthError

load_dotenv()

from rq import Queue
from worker import conn

q = Queue(connection=conn)

app = Flask(__name__)

app.config['REDIS_URL'] = os.getenv("REDIS_URL")

redis_client = FlaskRedis(app, decode_responses=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("You must set a SECRET_KEY in .env")

app.secret_key = SECRET_KEY

SCOPE = "user-read-email,user-top-read,user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state,playlist-read-collaborative,playlist-modify-public"


##############################################################################################
# Spotify helpers
##############################################################################################
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


def get_datetime_from_spotify_dt_str(dt_str):
    return datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%fZ")

def get_millis_ts(dt):
    epoch = datetime.datetime.utcfromtimestamp(0)
    return int((dt - epoch).total_seconds() * 1000)

def get_datetime_from_millis_ts(millis_ts):
    timestamp = int(millis_ts) / 1000
    return datetime.datetime.fromtimestamp(timestamp)

def get_user_currently_playing(username):
    token = get_existing_user_access_token(username)
    sp = spotipy.Spotify(auth=token)
    print(sp.current_user_playing_track())

def get_user_last_day_played(username):
    token = get_existing_user_access_token(username)
    now = datetime.datetime.now()
    one_day_ago = now - datetime.timedelta(days=1)
    one_day_millis = int(get_millis_ts(one_day_ago))

    sp = spotipy.Spotify(auth=token)
    cursor = None
    items = []
    while cursor is None or cursor > one_day_millis:
        print("Cursor is ", cursor)
        result = sp.current_user_recently_played(before=cursor,limit=50)
        print("got {} results".format(len(result['items'])))
        items.extend(result['items'])

        print(result['next'])

        cursor = int(result['cursors']['before'])
        print("Updated cursor to ", cursor)

    print("Loaded {} tracks".format(len(items)))

    artist_ids = []
    artist_map = {}
    
    track_ids = []
    track_map = {}

    for item in items:
        played_at = get_millis_ts(get_datetime_from_spotify_dt_str(item['played_at']))

        track = item['track']
        artists = track['artists']

        for artist in artists:
            artist_ids.append(artist['id'])
            artist_map[artist['id']] = artist['name']

        track_ids.append(track['id'])
        track_map[track['id']] = {
            'name': track['name'],
            'artist': track['artists'][0]['name'],
        }
        if 'album' in track and 'images' in track['album'] and track['album']['images']:
            track_map[track['id']].update({
                'art': track['album']['images'][0]['url']
            })

    print(track_ids)
    print(track_map)

    print(artist_ids)
    print(artist_map)
 



##############################################################################################
# SERENDIPITY WORKERS
##############################################################################################

class MusicdipityWorkerError(Exception):
    pass

def create_musicdipity(users_arr=None):
    if users_arr is None or not isinstance(users_arr, list) or not len(users_arr) > 1:
        raise MusicdipityWorkerError("user_arrs should be a list of 2 or more usernames")
    for user in users_arr:
        print(user)

def spawn_musicdipity_tasks():
    """ Parent job to enqueue checking for musicdipities across all users."""
    result = q.enqueue(create_musicdipity, ["dtran320", "rickyyean"])
    print("Successfully enqueued task to check for musicdipity for ricky and david ")

