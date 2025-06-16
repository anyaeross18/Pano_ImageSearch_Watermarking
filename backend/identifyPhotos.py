from google.cloud import vision 
import os
import requests
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
import hashlib
from fastapi import FastAPI, Request, UploadFile, File, Response
from fastapi.responses import JSONResponse

def upload_image_for_search(request: Request, image: UploadFile = File(...), response_db: Response = None, vision_client=None):
    user_id = request.session.get('user', {}).get('user_id', None)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "User not authenticated. Please log in."})

    # Read the image file
    image_bytes = image.file.read()

    # Call Google Cloud Vision API
    pagesFound = detect_web(vision_client, image_bytes)

    # Extract matching images
    links = {
        "partial_match": pagesFound.partial_matching_images,
        "full_match": pagesFound.full_matching_images,
        "visually_similar": pagesFound.visually_similar_images,
        "matching": pagesFound.pages_with_matching_images
    }

    max_items = 15
    image_entries = []

    # 1. Matching (extract partial_matching_images from each page)
    for page in links["matching"]:
        page_url = getattr(page, "url", None)
        page_title = getattr(page, "page_title", "")
        # partial_matching_images could be a list or a single object
        partials = getattr(page, "partial_matching_images", [])
        if isinstance(partials, dict):  # If it's a single dict, wrap in list
            partials = [partials]
        for img in partials:
            img_url = getattr(img, "url", None)
            if img_url:
                image_entries.append({
                    "image_url": img_url,
                    "page_url": page_url,
                    "page_title": page_title,
                    "source_type": "matching"
                })

    # 2. Full match, partial match, visually similar (use page.url directly)
    for key in ["full_match", "partial_match", "visually_similar"]:
        for page in links[key]:
            img_url = getattr(page, "url", None)
            page_title = getattr(page, "page_title", "")
            if img_url:
                image_entries.append({
                    "image_url": img_url,
                    "page_url": img_url,
                    "page_title": page_title,
                    "source_type": key
                })

    results = []
    target_img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    for entry in image_entries:
        query_image_url = entry["image_url"]
        print("Processing image URL:", query_image_url)
        query_img = load_image_cv2(query_image_url)
        print("Loaded query image:", query_img)
        if query_img is not None:
            sift_score = compare_images_sift(query_img, target_img)
            if sift_score < 100:
                results.append({
                    "url": query_image_url,
                    "sift_score": sift_score,
                    "page_url": entry["page_url"],
                    "page_title": entry["page_title"],
                    "source_type": entry["source_type"]
                })

    results = sorted(results, key=lambda x: x["sift_score"])[:max_items]

    return {
        "request": request,
        "message": "Upload successful",
        "results": [{"url": result["page_url"], "sift_score": result["sift_score"]} for result in results],
        "image_name": image.filename if image.filename else "image",
        "image_hash": hashlib.sha256(image_bytes).hexdigest(),
        "uploaded_image": response_db["uploaded_image"]
    }


def detect_web(client, image_bytes):
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.web_detection(image=image)
    web_detection = response.web_detection
    result = web_detection

    return result

def download_image(url):
    """Download image from URL or open local image path, and return a PIL Image."""
    # Check if URL is a local file path or a remote URL
    if url.startswith(('http://', 'https://')):
        # If it's a remote URL, use requests to fetch the image
        response = requests.get(url)

        if response.status_code == 200:
            # Check the content type of the response
            content_type = response.headers.get('Content-Type')

            # Handle common image formats
            if 'image' in content_type:
                try:
                    img = Image.open(BytesIO(response.content)).convert("RGB")
                    return img
                except IOError:
                    print(f"Failed to identify image from {url}. The file might be corrupted.")
                    return None
            else:
                print(f"URL does not point to an image. Content-Type: {content_type}")
                return str(content_type)
        else:
            print(f"Failed to retrieve image from {url}. Status code: {response.status_code}")
            return str(response.status_code)
    else:
        # If it's a local file path, check if the file exists
        if os.path.exists(url):
            try:
                img = Image.open(url).convert("RGB")
                return img
            except IOError:
                print(f"Failed to open image from local path: {url}")
                return None
        else:
            print(f"Local file path does not exist: {url}")
            return None

def extract_sift_features(image):
    """Extract SIFT features from the image."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create()
    keypoints, descriptors = sift.detectAndCompute(gray, None)
    return keypoints, descriptors

def compare_images_sift(img1, img2):
    """Compare two images using SIFT features."""
    # Extract SIFT features
    kp1, desc1 = extract_sift_features(img1)
    kp2, desc2 = extract_sift_features(img2)

    # Use BFMatcher to find the best matches between descriptors
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
    matches = bf.match(desc1, desc2)

    # Sort the matches based on distance (lower is better)
    matches = sorted(matches, key=lambda x: x.distance)

    # Return the average distance of the best matches
    avg_distance = np.mean([m.distance for m in matches[:10]])  # Top 10 matches
    return avg_distance

def load_image_cv2(image_url):
    """Load an image using OpenCV from a URL."""
    try:
      resp = requests.get(image_url)
    except:
      return None
    if resp.status_code != 200:
      return None
    img = np.asarray(bytearray(resp.content), dtype="uint8")
    img = cv2.imdecode(img, cv2.IMREAD_COLOR)
    return img