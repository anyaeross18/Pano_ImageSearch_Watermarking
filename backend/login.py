import hashlib
from fastapi import Request
import os
import json
from credentials.Oauth import oauth
from uuid import uuid4

async def handle_google_oauth(request: Request):
    token = await oauth.google.authorize_access_token(request)
    print("Token received:", token)
    
    sub = None
    user = None

    # Fallback to userinfo endpoint
    if not user:
        try:
            resp = await oauth.google.get('https://www.googleapis.com/oauth2/v2/userinfo', token=token)
            if resp.status_code == 200:
                user = resp.json()
                sub = user.get("id")
        except Exception as e:
            print("Error fetching userinfo:", e)

    # Fallback to alternative endpoint
    if not user:
        try:
            resp = await oauth.google.get('https://openidconnect.googleapis.com/v1/userinfo', token=token)
            print("Response from alternative userinfo endpoint:", resp)
            if resp.status_code == 200:
                user = resp.json()
                sub = user.get("id")
        except Exception:
            pass

    if not user or not sub:
        raise Exception("Failed to retrieve user and sub from token or userinfo.")

    return user, sub

async def get_google_oauth_url(request: Request):
    redirect_uri = request.url_for('auth_google')
    state = str(uuid4())  # generate unique state
    request.session["oauth_state"] = state
    print(f"Redirect URI: {redirect_uri}, State: {state}")

    # Pass the state to the authorize_redirect
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)
