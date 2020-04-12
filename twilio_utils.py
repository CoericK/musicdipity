
from twilio.rest import Client

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