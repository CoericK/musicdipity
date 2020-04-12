from musicdipity.spotify_utils import check_fuzzy_match_song_name

"""
These tests are trivially passing for now since we're just doing case insensitive-matching, but as
we add better fuzzy matching, we'll make sure we don't break these base cases.
"""

def test_exact_match():
    assert check_fuzzy_match_song_name("Hey Jude", "Hey Jude")

def test_icase_match():
    assert check_fuzzy_match_song_name("hey jude", "Hey Jude")

def test_shouldnt_match():
    assert not check_fuzzy_match_song_name("Yellow Sub", "Hey Jude")