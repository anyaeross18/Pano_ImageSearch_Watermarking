    
import hashlib
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.templating import Jinja2Templates
from backend.imageBucketManagement import upload_image_to_supabase_rawdata, get_signed_url_from_supabase
from backend.imageTableManagement import (
    image_in_og_image_database,
    get_image_from_og_image_database,
    image_in_watermarked_image_database,
    get_image_from_og_image_database_by_watermark_hash,
    save_image_to_database
)
from backend.watermarking import embed_watermark, show_watermark_embedding_locations
from backend.imageTableManagement import image_has_watermarked_image_made


async def upload_image_to_databases(request: Request, image: UploadFile):
    user_id = request.session.get('user', {}).get('user_id', None)
    if not user_id:
        return {"status": "error", "message": "User not authenticated. Please log in."}, 401

    name_of_image = image.filename if image.filename else "image"
    print("Received image:", name_of_image)

    # image hash
    image_bytes = await image.read()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    await image.seek(0)

    #check image hash not in watermarked or original image database
    if await image_in_og_image_database(image_hash):
        record = await get_image_from_og_image_database(image_hash)
        if record:
            signed_url = await get_signed_url_from_supabase(record['record']['original_image_url'])
            print("Image already exists in the database:", signed_url)
            download_filename = record['record']['image_name'] if 'image_name' in record['record'] else f"{image_hash}.jpg"
            download_filename = download_filename.split('.')[0] + "_watermarked." + download_filename.split('.')[-1]

            return {
                "request": request,
                "response": {"status": "OK", "message": "Image already exists in the database."},
                "image_hash": image_hash,
                "name_of_image": name_of_image,
                "uploaded_image": await get_signed_url_from_supabase(record['record']['original_image_url']),
                "download_filename": download_filename
            }

    if await image_in_watermarked_image_database(image_hash):
        record = await get_image_from_og_image_database_by_watermark_hash(image_hash)
        if record:
            signed_url = await get_signed_url_from_supabase(record['record']['watermarked_image_url'])
            print("Image already has a watermarked version in the database:", signed_url)
            download_filename = record['record']['watermarked_image_name'] if 'watermarked_image_name' in record['record'] else f"{image_hash}_watermarked.jpg"
            return {
                "request": request,
                "response": {"status": "error", "message": "Image already has a watermarked version in the database."},
                "image_hash": image_hash,
                "name_of_image": name_of_image,
                "uploaded_image": signed_url,
                "download_filename": download_filename
            }

    # Now upload to Supabase Storage (S3 equivalent)
    image_bucket = await upload_image_to_supabase_rawdata(image_bytes, name_of_image, image_hash)
    print("Image uploaded to bucket:", image_bucket)

    # Save metadata to the PostgreSQL DB first
    image_record = await save_image_to_database(image, user_id, name_of_image, image_bucket['file_path'], image_hash)
    if image_record[1] != 200:
        return {"status": "error", "message": image_record[0]['message']}, image_record[1]
    image_record = image_record[0]  # Extract the record from the tuple
    print("Image record created:", image_record)

    response = {"status": "success", "database_info": image_record, "bucket_info": image_bucket}
    print("signed URL:", image_bucket['url'])
    download_filename = image_record['record']['image_name'] if 'image_name' in image_record['record'] else f"{image_hash}.jpg"
    download_filename = download_filename.split('.')[0] + "_watermarked." + download_filename.split('.')[-1]
    return {
        "request": request,
        "response": response,
        "image_hash": image_hash,
        "name_of_image": name_of_image,
        "uploaded_image": image_bucket['url'],
        "download_filename": download_filename
    }