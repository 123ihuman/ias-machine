"""One-time OAuth setup: sign in once, save refresh token."""
import os, json
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT = 'config/oauth_client.json'
TOKEN  = 'config/oauth_token.json'
SCOPES = ['https://www.googleapis.com/auth/drive']

flow = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES)
creds = flow.run_local_server(port=8085, prompt='consent', access_type='offline')
with open(TOKEN, 'w') as f:
    f.write(creds.to_json())
print('\n✅ Token saved to', TOKEN)
print('Now uploads will count against your personal Google Drive quota.')