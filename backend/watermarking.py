import cv2
import numpy as np
import hashlib
import hmac
import base64

from backend.imageTableManagement import image_in_watermarked_image_database, image_has_watermarked_image_made, get_image_from_og_image_database_by_watermark_hash
from backend.imageBucketManagement import upload_image_to_supabase_rawdata, get_signed_url_from_supabase
from backend.imageTableManagement import get_image_from_og_image_database, save_watermarked_image_to_database, add_watermark_info_to_image_dataset, get_watermarked_image_from_database

import re
import requests
from fastapi import Request, Form
from fastapi.responses import JSONResponse

shared_secret_key = open("credentials/sharedWatermarkingKey.txt").read().strip()
SECRET_KEY = hashlib.sha256(shared_secret_key.encode()).digest()

async def watermarking_actions(request: Request, image_url: str = Form(...), action: str = Form(...)):
    # Step 1: Authenticate user
    user_id = request.session.get('user', {}).get('user_id')
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "User not authenticated. Please log in."})

    # Step 2: Download the original image using the Supabase-signed URL
    resp = requests.get(image_url)
    if resp.status_code != 200:
        return JSONResponse(status_code=400, content={"error": "Failed to fetch image from URL."})

    # Step 3: Decode image with OpenCV
    image_array = np.frombuffer(resp.content, np.uint8)
    image_cv = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image_cv is None:
        return JSONResponse(status_code=400, content={"error": "Failed to decode image."})

    # Step 4: Extract image hash and type from the Supabase signed URL
    url_pattern = r"object/sign/([^/]+)/([^/]+)(\.\w+)\?token="
    match = re.search(url_pattern, image_url)
    if not match:
        return JSONResponse(status_code=400, content={"error": "Invalid Supabase image URL format."})
    
    bucket_name, image_hash, image_type = match.groups()

    if action == "embed":
        return await embed_watermark_in_image(image_hash, image_type, image_url, image_cv, bucket_name, user_id)
    elif action == "verify":
        # Step 5: Verify watermark
        verify_response = await verify_watermark(image_hash)
        return {
            "uploaded_image": image_url,  # original image URL
            "image_hash": image_hash,
            "result": verify_response["message"],
            "verified": verify_response["verified"],
        }
    else:
        return JSONResponse(status_code=400, content={"error": "Invalid purpose specified. Use 'embed' or 'verify'."})


async def embed_watermark_in_image(image_hash, image_type, image_url, image_cv, bucket_name, user_id: str):
    # Step 5: Check if image already has a watermark
    if await image_in_watermarked_image_database(image_hash):
        watermarked_record = await get_watermarked_image_from_database(image_hash)
        filename = watermarked_record['record']['watermarked_image_name'] if watermarked_record else f"{image_hash}_watermarked{image_type}"
        return {
                "uploaded_image": image_url,  # original image
                "watermarked_image_url": image_url,  # signed URL for watermarked image
                "result": "Image already Watermarked",
                "download_filename": filename,
                "watermark_image_hash": image_hash,
            }

    # Step 6: Retrieve metadata from your database
    db_result = await get_image_from_og_image_database(image_hash)
    print(f"[INFO] Retrieved DB result: {db_result}")
    record = db_result.get('record') if db_result else None
    name_of_image = record['image_name'].split('.')[0] if record and 'image_name' in record else "image"

    # Step 7: Embed watermark
    watermarked_img = embed_watermark(image_cv, user_id=user_id)
    if watermarked_img.dtype != np.uint8:
        watermarked_img = watermarked_img.astype(np.uint8)

    # Step 8: Encode image to bytes
    success, img_encoded = cv2.imencode(image_type, watermarked_img)
    if not success:
        return JSONResponse(status_code=500, content={"error": "Failed to encode watermarked image."})
        
    raw_bytes = img_encoded.tobytes()
    print(f"[INFO] Watermarked image size: {len(raw_bytes)} bytes")

    # Step 9: Hash & construct filename
    watermark_hash = hashlib.sha256(raw_bytes).hexdigest()
    filename = f"{name_of_image}_watermarked{image_type}"

    # Step 10: Upload to Supabase (RAW bytes only — not BytesIO)
    upload_response = await upload_image_to_supabase_rawdata(
        image=raw_bytes,
        image_name=filename,
        hash=watermark_hash,
        bucket_name="watermarkbucket"
    )

    # Step 11: Save metadata in your DB
    await save_watermarked_image_to_database(
        user_id,
        filename,
        upload_response["file_path"],
        watermark_hash
    )
        
    await add_watermark_info_to_image_dataset(
        original_image_hash=image_hash,
        watermarked_image_hash=watermark_hash,
        watermarked_image_url=upload_response["file_path"]
    )

    # Step 12: Return response
    return {
        "uploaded_image": image_url,  # original image URL
        "watermarked_image_url": upload_response["url"],  # signed URL for watermarked image
        "result": "Watermarking successful",
        "download_filename": filename,
        "watermark_image_hash": watermark_hash,
    }

async def show_watermark_embedding_locations(request: Request, watermarked_image_hash: str):
    # Step 1: Authenticate user
    user_id = request.session.get('user', {}).get('user_id')
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "User not authenticated. Please log in."})

    # Step 2: Retrieve metadata from your database
    db_result = await get_image_from_og_image_database_by_watermark_hash(watermarked_image_hash)
    print(f"[INFO] Retrieved DB result: {db_result}")
    record = db_result.get('record') if db_result else None
    if not record:
        return JSONResponse(status_code=404, content={"error": "Image not found in database."})

    # Step 3: Get the signed URL for the watermarked image and original image
    watermarked_image_url = record.get('watermarked_image_url')
    if not watermarked_image_url:
        return JSONResponse(status_code=404, content={"error": "Watermarked image URL not found."})
    original_image_url = record.get('original_image_url')
    if not original_image_url:
        return JSONResponse(status_code=404, content={"error": "Original image URL not found."})

    #step 4: get bytes of both images
    signed_url_watermarked_image = await get_signed_url_from_supabase(watermarked_image_url)
    signed_url_original_image = await get_signed_url_from_supabase(original_image_url)

    if not signed_url_watermarked_image or not signed_url_original_image:
        return JSONResponse(status_code=404, content={"error": "Failed to retrieve signed URLs."})

    wm_response = requests.get(signed_url_watermarked_image)
    og_response = requests.get(signed_url_original_image)

    wm_bytes = wm_response.content
    og_bytes = og_response.content

    #step 5: pass bytes to watermark showing function
    image_with_embedding_shown = show_watermark_embedding_locations_helper(og_bytes, wm_bytes)

    download_filename = record.get('image_name', f"{watermarked_image_hash}_watermarked.jpg")
    download_filename = download_filename.split('.')[0] + "_watermarked." + download_filename.split('.')[-1]

    return{
        "watermarked_image_url": signed_url_watermarked_image,
        "original_image_url": signed_url_original_image,
        "image_hash": watermarked_image_hash,
        "name_of_image": record.get('image_name', 'image'),
        "image_with_embedding_shown": image_with_embedding_shown,
        "download_filename": download_filename,
    }

def show_watermark_embedding_locations_helper(original_img_bytes, watermarked_img_bytes):
    """Highlight where watermark bits were embedded, including marker."""
    original_img = cv2.imdecode(np.frombuffer(original_img_bytes, np.uint8), cv2.IMREAD_COLOR)
    watermarked_img = cv2.imdecode(np.frombuffer(watermarked_img_bytes, np.uint8), cv2.IMREAD_COLOR)

    if original_img is None or watermarked_img is None:
        raise ValueError("Failed to decode one of the images.")
    if original_img.shape != watermarked_img.shape:
        raise ValueError("Image dimensions must match.")

    # Step 1: Find which pixels have changed (only 1-bit difference in blue channel)
    diff_blue = cv2.absdiff(original_img[:, :, 2], watermarked_img[:, :, 2])
    diff_mask = (diff_blue > 0).astype(np.uint8) * 255

    # Step 2: Convert to 3-channel for visualization
    highlight = original_img.copy()
    highlight[diff_mask > 0] = [0, 0, 255]  # Highlight modified pixels in red

    image_with_embedding_shown = cv2.cvtColor(highlight, cv2.COLOR_BGR2RGB)
    _, buffer = cv2.imencode('.png', image_with_embedding_shown)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/png;base64,{img_base64}"


def generate_watermark_text(user_id: str, image_hash: str) -> str:
    base_text = f"{user_id}_{image_hash}"
    signature = hmac.new(SECRET_KEY, base_text.encode(), hashlib.sha256).digest()
    short_sig = base64.urlsafe_b64encode(signature[:6]).decode('utf-8')
    return f"{base_text}:{short_sig}"

def embed_watermark(image: np.ndarray, user_id: str) -> np.ndarray:
    if not user_id:
        raise ValueError("User ID must be provided.")
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected an RGB image.")

    h, w, _ = image.shape
    if h < 100 or w < 100:
        raise ValueError("Image too small to embed watermark.")

    # 1. Generate a watermark text using hash of image + user ID
    watermark_text = generate_watermark_text(user_id, hashlib.sha256(image.tobytes()).hexdigest())

    # 2. Make a copy to avoid overwriting the original
    watermarked = image.copy()

    # 3. Add fixed binary marker in top-left corner (for verification)
    marker_bits = [1, 0, 1, 0, 1, 1, 0, 0]
    for i, bit in enumerate(marker_bits):
        watermarked[i, 0, 2] = (watermarked[i, 0, 2] & 0xFE) | bit  # Only blue channel

    # 4. Convert text to binary
    binary = ''.join(format(ord(char), '08b') for char in watermark_text)
    bit_count = len(binary)

    # 5. Generate random positions (seeded by watermark for reproducibility)
    seed = int(hashlib.md5(watermark_text.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    positions = set()
    while len(positions) < bit_count:
        row = rng.integers(10, h - 10)
        col = rng.integers(10, w - 10)
        positions.add((row, col))
    positions = list(positions)

    # 6. Embed bits into blue channel at random positions
    for i, (r, c) in enumerate(positions):
        watermarked[r, c, 2] = (watermarked[r, c, 2] & 0xFE) | int(binary[i])

    return watermarked

async def verify_watermark(image_hash: str):
    if not image_hash:
        raise ValueError("Image hash must be provided.")

    if await image_in_watermarked_image_database(image_hash):
        return {"message": "Image is Verified", "verified":True}
    elif await image_has_watermarked_image_made(image_hash):
        return {"message": "Uploaded Image is not Verified although has an associated watermarked version created and in database.", "verified":False}
    else:
        return {"message": "Image is not Verified. Please Embed image to add watermarking.", "verified":False}