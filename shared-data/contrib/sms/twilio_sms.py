from twilio.rest import TwilioRestClient

account = "AC######################"
token = "***************************"
client = TwilioRestClient(account, token)

message = client.messages.create(to="+15031112222", from_="+13101112222",
                                 body="Hello there!")