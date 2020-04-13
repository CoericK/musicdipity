import datetime
import os

from flask import Flask

from flask_redis import FlaskRedis
# See .env.example for required environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

app.config['REDIS_URL'] = os.getenv("REDIS_URL")

redis_client = FlaskRedis(app, decode_responses=True)

def get_all_users():
    # TODO 2020-04-13: CAREFUL Don't run this when we have lots of keys/users
    authed_users = redis_client.keys('user:*')
    pipe = redis_client.pipeline()
    for user_key in authed_users:
        user = pipe.get(user_key)
        print("{} - {}".format(user['display_name'], user['email'] if 'email' in user else 'No email'))


# Borrowed from https://shubhamjain.co/til/how-to-render-human-readable-time-in-jinja/
def humanize_ts(timestamp_ms):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    timestamp = int(timestamp_ms / 1000)
    now = datetime.datetime.now()
    diff = now - datetime.datetime.fromtimestamp(timestamp)
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(int(second_diff)) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(int(second_diff / 60)) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(int(second_diff / 3600)) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(int(day_diff / 7)) + " weeks ago"
    if day_diff < 365:
        return str(int(day_diff / 30)) + " months ago"
    return str(int(day_diff / 365)) + " years ago"
