import datetime
import json
import os
import sys
from collections import defaultdict

# See .env.example for required environment variables
from dotenv import load_dotenv

from flask_redis import FlaskRedis
from spotipy import SpotifyOAuth, is_token_expired

from .spotify_utils import *
from .exceptions import MusicdipityAuthError
from .utils import humanize_ts
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

##############################################################################################
# MUSIC SERENDIPITY WORKERS
##############################################################################################

class MusicdipityWorkerError(Exception):
    pass

def create_musicdipity(users_arr=None):
    if users_arr is None or not isinstance(users_arr, list) or not len(users_arr) > 1:
        raise MusicdipityWorkerError("user_arrs should be a list of 2 or more usernames")
    user_artists = {}
    user_current_artists = {}
    for user in users_arr:
        print(user)
        user_artists[user] = set(redis_client.zrange("recent_artists:{}".format(user), 0, -1))
        print(user_artists[user])

        currently_playing = get_user_currently_playing(user)
        if not currently_playing:
            print("not playing anything")
            continue
        print("user is currently playing {}".format(currently_playing['name']))
        currently_playing_artists = currently_playing['artists']
        currently_playing_artist_ids = set(artist['id'] for artist in currently_playing_artists)
        user_current_artists[user] = currently_playing_artist_ids

    artist_to_user_map = defaultdict(list)
    for user, current_artists in user_current_artists.items():
        other_user_artists = set()
        for other_user, artists in user_artists.items():
            if user == other_user:
                continue
            for artist in artists:
                artist_to_user_map[artist] = other_user
            other_user_artists |= artists

        print(currently_playing_artist_ids)
        print(other_user_artists)
        overlaps = currently_playing_artist_ids & other_user_artists
        if overlaps:
            # TODO 2020-04-12: Be more intelligent about which artist if the current song overlaps with several
            artist = overlaps.pop()
            print(artist)
            artist_name = get_artist_name_for_id(artist)
            print(artist_name)
            print("AHA! WE GOT AN OVERLAP for artist: {}".format(artist_name))
            username = artist_to_user_map[artist]
            user_artist_last_played = int(redis_client.zscore("recent_artists:{}".format(username), artist))
            print(user_artist_last_played)
            ago = humanize_ts(user_artist_last_played)
            print("You just played {}. {} played {} {}".format(artist_name, username, artist_name, ago))


def spawn_musicdipity_tasks():
    """ Parent job to enqueue checking for musicdipities across all users."""
    result = q.enqueue(create_musicdipity, ["dtran320", "rickyyean"])
    print("Successfully enqueued task to check for musicdipity for ricky and david ")

