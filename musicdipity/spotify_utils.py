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
from spotipy import SpotifyOAuth, is_token_expired, SpotifyClientCredentials

from .exceptions import MusicdipityAuthError
from .utils import humanize_ts
load_dotenv()

app = Flask(__name__)

app.config['REDIS_URL'] = os.getenv("REDIS_URL")

redis_client = FlaskRedis(app, decode_responses=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("You must set a SECRET_KEY in .env")

app.secret_key = SECRET_KEY

# TODO (2020-04-12): Be less aggressive/generous with the permissions we ask for
SCOPE = "user-read-email,user-top-read,user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state,playlist-read-collaborative,playlist-modify-public"

# Keep tracks and artists cached for 1 day
TRACK_AND_ARTIST_CACHE_PERIOD = 86400

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


def get_client_sp():
    """ Returnour client credential. This can only be used to retrieve general info WITHOUT user-specific info."""
    client_credentials_manager = SpotifyClientCredentials()
    return spotipy.Spotify(client_credentials_manager=client_credentials_manager)


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


def get_user_sp(username):
    token = get_existing_user_access_token(username)
    return spotipy.Spotify(auth=token)


def get_datetime_from_spotify_dt_str(dt_str):
    return datetime.datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%fZ")


def get_millis_ts(dt):
    epoch = datetime.datetime.utcfromtimestamp(0)
    return int((dt - epoch).total_seconds() * 1000)


def get_user(username):
    user_info_json = redis_client.get("user:{}".format(username))
    if not user_info_json:
        sp = get_user_sp(username)
        user_info = sp.current_user()
        user_info_json = json.dumps(user_info)
        redis_client.set("user:{}".format(username), user_info_json)
    else:
        user_info = json.loads(user_info_json)
    return user_info


def get_datetime_from_millis_ts(millis_ts):
    timestamp = int(millis_ts) / 1000
    return datetime.datetime.fromtimestamp(timestamp)


def get_artist_for_id(artist_id):
    artist_json = redis_client.get(artist_id)
    if artist_json is None:
        sp = get_client_sp()
        artist_info = sp.artist(artist_id)
        artist_json = json.dumps(artist_info)
        artist_name = artist_info['name']
        redis_client.setex(name="artist:{}".format(artist_id), value=artist_json, time=TRACK_AND_ARTIST_CACHE_PERIOD)
    else:
        artist_info = json.loads(artist_json)
    return artist_info


def get_user_currently_playing(username):
    sp = get_user_sp(username)
    currently_playing = sp.current_user_playing_track()
    if not currently_playing:
        return None

    timestamp = currently_playing['timestamp']

    save_user_recent_tracks_and_artists(username, [{
        'played_at': timestamp,
        'track': currently_playing['item']
    }])

    return currently_playing['item']


def save_user_recent_tracks_and_artists(username, tracks_with_play_info):
    artist_last_played = defaultdict(int)
    artist_map = {}
    
    track_last_played = defaultdict(int)
    track_map = {}
    for track_info in tracks_with_play_info:
        played_at = track_info['played_at']
        track = track_info['track']
        artists = track['artists']

        for artist in artists:
            artist_id = artist['id']
            if played_at > artist_last_played[artist_id]:
                artist_last_played[artist_id] = played_at
            artist_map[artist_id] = artist['name']

        track_id = track['id']
        if played_at > track_last_played[track_id]:
            track_last_played[track_id] = played_at

        track_map[track_id] = {
            'name': track['name'],
            'artist': artists[0]['name'],
        }
        if 'album' in track and 'images' in track['album'] and track['album']['images']:
            track_map[track_id].update({
                'art': track['album']['images'][0]['url']
            })

    pipe = redis_client.pipeline()
    pipe.zadd("recent_artists:{}".format(username), artist_last_played)
    pipe.zadd("recent_tracks:{}".format(username), track_last_played)
    for track_id, track in track_map.items():
        pipe.hmset("track:{}".format(track_id), track)
        pipe.expire(track_id, TRACK_AND_ARTIST_CACHE_PERIOD)
    pipe.execute()


def get_user_last_day_played(username):
    now = datetime.datetime.now()
    one_day_ago = now - datetime.timedelta(days=1)
    one_day_millis = int(get_millis_ts(one_day_ago))

    sp = get_user_sp(username)
    cursor = None
    items = []

    # TODO (2020-04-12) - BUG: For reals, spent ~1 hour debugging this. The Spotify Web API
    # Might just be broken here since paging doesn't appear to work, so we're just limited to 50 for now.
    # https://developer.spotify.com/documentation/web-api/reference-beta/#endpoint-get-recently-played
    while cursor is None or cursor > one_day_millis:
        print("Cursor is ", cursor)
        result = sp.current_user_recently_played(before=cursor,limit=50)
        print("Got {} results".format(len(result['items'])))
        if not result["items"]:
            break
        items.extend(result['items'])
        print("Next results should be at {}".format(result['next']))
        cursor = int(result['cursors']['before'])
        print("Updated cursor to ", cursor)

    print("Loaded {} tracks".format(len(items)))

    for item in items:
        item['played_at'] = get_millis_ts(get_datetime_from_spotify_dt_str(item['played_at']))

    save_user_recent_tracks_and_artists(username, items)
 
    return items
 

def_create_playlist_for_users(user1, user2):
    sp1 = get_user_sp(user1)
    sp2 = get_user_sp(user2)

    