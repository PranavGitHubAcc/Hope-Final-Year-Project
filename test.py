from twilio.rest import Client

account_sid = 'ACa6823bc36ab97d6da213b8939d990a05'
auth_token = 'eb9bda4f3e4befdeaec4d6c2270fd0a0'
client = Client(account_sid, auth_token)

message = client.messages.create(
  from_='whatsapp:+14155238886',
  content_sid='HXb5b62575e6e4ff6129ad7c8efe1f983e',
  content_variables='{"1":"12/1","2":"3pm"}',
  to='whatsapp:+918421278804'
)

print(message.sid)