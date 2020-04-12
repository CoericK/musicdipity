import sys

import spotipy
import spotipy.util as util

# See .env.example for required environment variables
from dotenv import load_dotenv

load_dotenv()

SCOPE = "user-library-read,user-read-recently-played,user-read-playback-position,user-read-currently-playing,user-modify-playback-state"


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
        print(sp.current_user())
        results = sp.current_user_recently_played(limit=50)
        for item in results["items"]:
            track = item["track"]
            print(track["name"] + " - " + track["artists"][0]["name"])
    else:
        print("Can't get token for", username)


get_auth_prompt_and_recent_tracks()


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