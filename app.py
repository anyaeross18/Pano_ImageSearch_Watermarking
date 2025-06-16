import os
import ast
import shutil
import json
from io import BytesIO
from typing import Optional
from contextlib import asynccontextmanager
import re

import cv2
import numpy as np
from PIL import Image
import requests

from google.cloud import vision

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

from databases import Database
import hashlib
import uuid

from backend.watermarking import show_watermark_embedding_locations, watermarking_actions
from backend.identifyPhotos import upload_image_for_search
from backend.userTableManagement import get_or_create_user
from backend.overviewDBManagement import upload_image_to_databases
from backend.login import get_google_oauth_url, handle_google_oauth

from credentials.supabase_DB import supabase_database
from credentials.database import database

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()

app = FastAPI(lifespan=lifespan)
secret_key = open("credentials/secretAPPKey.txt").read().strip()
app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    same_site="lax",     
    https_only=False       
)

# Set the path to the JSON key file you uploaded
key_path = 'credentials/googlecloudAcess.json'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = key_path

app.mount("/pages", StaticFiles(directory="pages"), name="pages")
templates = Jinja2Templates(directory="pages/templates")

vision_client = vision.ImageAnnotatorClient()
temporary_storage = {}

@app.get("/", response_class=HTMLResponse)
async def serve_home_html():
    with open("pages/home.html", "r") as file:
        content = file.read()
    return HTMLResponse(content=content)

@app.get("/pricing", response_class=HTMLResponse)
async def read_pricing(request: Request):
    return templates.TemplateResponse("pricing.html", {"request": request})

@app.get("/upload", response_class=HTMLResponse)
def get_watermarking_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request, "result": ""})

@app.post("/upload", response_class=JSONResponse)
async def upload_image(request: Request, image: UploadFile = File(...), purpose: str = Form(...)):
    response = await upload_image_to_databases(request, image)

    if purpose == "search":
        search_results = upload_image_for_search(request, image, response_db=response, vision_client=vision_client)

        # Generate unique ID and store result
        result_id = str(uuid.uuid4())
        temporary_storage[result_id] = search_results

        return RedirectResponse(url=f"/search/results/{result_id}", status_code=303)

    elif purpose == "watermarking":
        result_id = str(uuid.uuid4())
        temporary_storage[result_id] = response

        return RedirectResponse(url=f"/watermarking/{result_id}", status_code=303)


@app.get("/search/results/{result_id}", response_class=HTMLResponse)
async def view_results(request: Request, result_id: str):
    search_results = temporary_storage.get(result_id)
    if not search_results:
        return HTMLResponse(content="Results not found or expired", status_code=404)

    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "message": search_results.get("message", ""),
        "results": search_results.get("results", []),
        "image_name": search_results.get("image_name", ""),
        "image_hash": search_results.get("image_hash", ""),
        "uploaded_image": search_results.get("uploaded_image", "")
    })



@app.get("/watermarking/{result_id}", response_class=HTMLResponse)
async def view_watermarking_dashboard(request: Request, result_id: str):
    data = temporary_storage.get(result_id)
    if not data:
        return HTMLResponse(content=f"Watermarking data not found or expired - watermakring ext", status_code=404)

    return templates.TemplateResponse("watermark_action.html", {
        "request": request,
        "result_id": result_id,  # 👈 make sure this is here
        "image_hash": data.get("image_hash", ""),
        "name_of_image": data.get("name_of_image", ""),
        "uploaded_image": data.get("uploaded_image", ""),
        "download_filename": data.get("download_filename", "watermarked_image.png")
    })


@app.get("/show/watermarking")
async def show_watermark(request: Request, result_id: Optional[str] = None):
    print("Showing watermark for result_id:", result_id)
    print("Temporary storage contents:", temporary_storage)
    data = temporary_storage.get(result_id)
    if not data:
        return HTMLResponse(content=f"Watermarking data not found or expired {result_id}\n{temporary_storage}", status_code=404)

    watermarked_image = data.get("watermark_image_hash", "")
    uploaded_image = data.get("uploaded_image", "")
    print("Watermarked image:", watermarked_image)
    print("Uploaded image:", uploaded_image)
    response = await show_watermark_embedding_locations(request, watermarked_image)

    if isinstance(response, JSONResponse):
        return response

    return templates.TemplateResponse("watermark_action.html", {
        "request": request,
        "uploaded_image": uploaded_image,
        "watermarked_image_url": response.get("watermarked_image_url"),
        "image_hash": response.get("image_hash"),
        "name_of_image": response.get("name_of_image", "image"),
        "image_with_embedding_shown": response.get("image_with_embedding_shown", False),
        "download_filename": response.get("download_filename", "watermarked_image.png"),
        "result_id": result_id  # Pass back into the template
    })


@app.post("/watermarking/action")
async def watermarking(request: Request):
    form = await request.form()
    action = form.get("action")
    image_url = form.get("image_url")
    result_id = form.get("result_id")

    response = await watermarking_actions(request, image_url, action)

    # Inside watermarking function after getting response
    temporary_storage[result_id] = {
        "image_hash": response.get("image_hash", ""),
        "uploaded_image": response.get("uploaded_image", ""),
        "watermarked_image_url": response.get("watermarked_image_url", ""),
        "watermark_image_hash": response.get("watermark_image_hash", ""),
        "download_filename": response.get("download_filename", "watermarked_image.png"),
        "result": response.get("result", ""),
        "verified": response.get("verified", False),
        "name_of_image": response.get("name_of_image", ""),
        "result_id": result_id
    }

    if action == "embed":
        return templates.TemplateResponse("watermark_action.html", {
            "request": request,
            "image_hash": response.get("image_hash", ""),
            "name_of_image": response.get("name_of_image", ""),
            "uploaded_image": response.get("uploaded_image", ""),
            "download_filename": response.get("download_filename", "watermarked_image.png"),
            "watermarked_image_url": response.get("watermarked_image_url", ""),
            "watermark_image_hash": response.get("watermark_image_hash", ""),
            "result": response.get("result", ""),
            "result_id": result_id
        })

    elif action == "verify":
        return templates.TemplateResponse("watermark_action.html", {
            "request": request,
            "image_hash": response.get("image_hash", ""),
            "name_of_image": response.get("name_of_image", ""),
            "uploaded_image": response.get("uploaded_image", ""),
            "download_filename": response.get("download_filename", "watermarked_image.png"),
            "watermarked_image_url": response.get("watermarked_image_url", ""),
            "watermark_image_hash": response.get("watermark_image_hash", ""),
            "verified": response.get("verified", False),
            "result": response.get("result", ""),
            "result_id": result_id
        })
    return JSONResponse(status_code=400, content={"error": "Unknown action specified."})


@app.get("/download/watermarking")
async def download_watermarked_image(url: str, filename: str = "watermarked.png"):
    # Download the image from the signed URL
    resp = requests.get(url)
    if resp.status_code != 200:
        return JSONResponse(status_code=400, content={"error": "Failed to fetch image for download."})
    return StreamingResponse(
        BytesIO(resp.content),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get('/login/google')
async def login_via_google(request: Request):
    return await get_google_oauth_url(request)

from backend.userTableManagement import get_or_create_user

@app.get('/auth/google')
async def auth_google(request: Request):
    try:
        print("Handling Google OAuth callback")
        print("Request query params:", request.query_params)
        print("Request session state before processing:", request.session.get("oauth_state"))

        returned_state = request.query_params.get("state")
        expected_state = request.session.get("oauth_state")
        print(f"Returned state: {returned_state}, Expected state: {expected_state}")

        user_info, sub = await handle_google_oauth(request)
        print("User info received:", user_info)

        request.session['user'] = {
            'user_id': str(user_info['id']),
            'email': user_info['email'],
            'name': user_info['name']
        }

        resp = await get_or_create_user(
            str(user_info['id']),
            email=user_info['email'],
            name=user_info['name']
        )
        print("User created or fetched:", resp)
        print("user_id:", resp['user_id'])
        request.session['user']['user_id'] = resp['user_id']

        return RedirectResponse(url="/upload", status_code=303)

    except Exception as e:
        import traceback
        print("❌ Google auth failed:", str(e))
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": "Google OAuth failed", "detail": str(e)})
