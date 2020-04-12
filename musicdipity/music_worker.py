import datetime
import time
import json
import os
import sys
from collections import defaultdict

# See .env.example for required environment variables
from dotenv import load_dotenv

from flask_redis import FlaskRedis
from spotipy import SpotifyOAuth, is_token_expired

# TODO Don't * import
from .spotify_utils import *
from .exceptions import MusicdipityAuthError
from twilio_utils import send_sms
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

TEXT_COOLDOWN = int(os.getenv('TEXT_COOLDOWN', 300))

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

        currently_playing = get_and_update_user_currently_playing(user)
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
            artist_info = get_artist_for_id(artist)
            artist_name = artist_info['name']
            print("AHA! WE GOT AN OVERLAP for artist: {}".format(artist_name))
            other_username = artist_to_user_map[artist]
            user_artist_last_played = int(redis_client.zscore("recent_artists:{}".format(other_username), artist))
            ago = humanize_ts(user_artist_last_played)
            user_info = get_user(user)
            other_user_info = get_user(other_username)
            message = "{} just played {}. {} played {} {}".format(user_info['display_name'], artist_name, other_user_info['display_name'], artist_name, ago)
            print(message)
            timestamp = int(time.time())
            user_last_alerted_key = "last_alerted:{}".format(user)
            other_user_last_alerted_key = "last_alerted:{}".format(other_username)
            try:
                last_messaged = [int(l) for l in redis_client.mget([user_last_alerted_key, other_user_last_alerted_key])]
                for ts in last_messaged:
                    if ts > timestamp - TEXT_COOLDOWN:
                        print("Not going to alert users because of recent serendipity.")
                        return
            except:
                pass
            print("OKAY TO MESSAGE!")
            redis_client.mset({
                user_last_alerted_key: timestamp,
                other_user_last_alerted_key: timestamp,
            })
            user_number = get_phone_number_for_user(user)
            other_user_number = get_phone_number_for_user(other_username)
            print(user_number)
            print(other_user_number)
    
            artist_image = artist_info['images'][0]['url'] if 'images' in artist_info and artist_info['images'] else None
            send_sms(to_number=user_number, body=message, media_url=artist_image)
            send_sms(to_number=other_user_number, body=message, media_url=artist_image)

            # TODO 2020-04-12: Add a conditional branch if the other user is not currently listening to spotify
            # We have the logic for this, e.g.
            # if get_user_currently_playing(other_username) raises...
            game_message = "Since you're both Spotify right now, How about a quick game of 🥁 \"Name that {} Song?\" (Simply reply \"Y\" and I'll coordinate)".format(artist_name)
            game_gif = "https://media.giphy.com/media/gLKVCVdLUXMTeIs6MD/giphy.gif"
            send_sms(to_number=user_number, body=game_message, media_url=game_gif)
            send_sms(to_number=other_user_number, body=game_message, media_url=game_gif)

            game_key = 'game:{}'.format(user)
            other_game_key = 'game:{}'.format(other_username)

            redis_client.mset({
                game_key: "{}||{}".format(other_username, artist_info['id']),
                other_game_key: "{}||{}".format(user, artist_info['id'])
            })

def spawn_musicdipity_tasks():
    """ Parent job to enqueue checking for musicdipities across all users."""
    result = q.enqueue(create_musicdipity, ["rickyyean", "dtran320"])
    print("Successfully enqueued task to check for musicdipity for ricky and david ")

