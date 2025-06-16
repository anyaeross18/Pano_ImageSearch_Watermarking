from credentials.supabase_DB import get_url, get_key, supabase_database
from credentials.database import database
from fastapi import UploadFile
import requests
from supabase import create_client, Client
from io import BytesIO
import re

async def get_signed_url_from_supabase(image_path: str):
    pattern_image_hash = r"(\w*?)/(.*)"
    match = re.match(pattern_image_hash, image_path)
    bucket_name, image_file_name = match.groups() if match else (None, None)
    print(f"Extracted bucket name: {bucket_name}, image file name: {image_file_name} from image path: {image_path}")
    if not bucket_name or not image_file_name:
        print(f"Invalid image path format: {image_path}")
        return {"message": "Invalid image path format."}, 400
    try:
        print(f"Fetching signed URL for image file name: {image_file_name} from bucket: {bucket_name}")
        response = supabase_database.storage.from_(bucket_name).create_signed_url(
            path=image_file_name,
            expires_in=3600  # URL valid for 1 hour
        )
        
        signed_url = response.get("signedURL")
        if not signed_url:
            raise ValueError("Failed to get signed URL from Supabase.")
        
        print(f"Signed URL fetched successfully: {signed_url}")
        return signed_url

    except Exception as e:
        print(f"Error fetching signed URL: {e}")
        return {"message": "Error fetching signed URL from Supabase."}, 500

async def upload_image_to_supabase_rawdata(image: bytes, image_name: str, hash: str, bucket_name: str = "imagebucket"):
    try:
        file_extension = image_name.split('.')[-1] if image_name else 'jpg'
        file_name = f"{hash}.{file_extension}"
        content_type = "image/jpeg"  # Default content type
        print(f"Uploading image with name: {file_name} to bucket: {bucket_name}")
        print(f"Content type: {content_type}")
        
        # Upload using Supabase storage
        response = supabase_database.storage.from_(bucket_name).upload(
            path=file_name,
            file=image,
            file_options={"upsert": "true", "content-type": content_type}
        )

        print(f"Image uploaded to Supabase Storage: {response}")

        signed_url_response = supabase_database.storage.from_(bucket_name).create_signed_url(
            path=file_name,
            expires_in=3600  # URL valid for 1 hour
        ).get("signedURL")

        return {
            "file_path": bucket_name + "/" + file_name,
            "file_name": file_name,
            "url": signed_url_response
        }

    except Exception as e:
        print(f"Error uploading image: {e}")
        return {"message": "Error uploading image to Supabase."}, 500

async def upload_image_to_supabase(image: UploadFile, image_hash: str, bucket_name: str = "imagebucket"):
    try:
        image_content = await image.read()
        print(f"Image content length: {len(image_content)} bytes")
        file_extension = image.filename.split('.')[-1] if image.filename else 'jpg'
        file_name = f"{image_hash}.{file_extension}"
        content_type = image.content_type if image.content_type else "image/jpeg"
        print(f"Uploading image with name: {file_name} to bucket: {bucket_name}")
        print(f"Content type: {content_type}")
        print(f"Content: {image_content[:100]}...")  # Print first 100 bytes for debugging
        
        # Upload using Supabase storage
        response = supabase_database.storage.from_(bucket_name).upload(
            path=file_name,
            file=image_content,
            file_options={"upsert": "true", "content-type": content_type}
        )

        print(f"Image uploaded to Supabase Storage: {response}")

        signed_url_response = supabase_database.storage.from_(bucket_name).create_signed_url(
            path=file_name,
            expires_in=3600  # URL valid for 1 hour
        ).get("signedURL")

        return {
            "file_path": bucket_name + "/" + file_name,
            "file_name": file_name,
            "url": signed_url_response
        }

    except Exception as e:
        print(f"Error uploading image: {e}")
        return {"message": "Error uploading image to Supabase."}, 500