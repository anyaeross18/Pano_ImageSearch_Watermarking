import hashlib
from datetime import datetime
from credentials.database import database
from fastapi import UploadFile

async def image_in_og_image_database(image_hash: str):
    """
    Checks if an image with the given hash exists in the database.
    """
    query = """
    SELECT COUNT(*) FROM original_images
    WHERE image_hash = :hash
    """

    result = await database.fetch_val(query=query, values={"hash": image_hash})
    
    return result > 0

async def get_image_from_og_image_database_by_watermark_hash(watermark_hash: str):
    """
    Retrieves an original image from the database based on its watermark hash.
    """
    query = """
    SELECT * FROM original_images
    WHERE watermark_hash = :watermark_hash
    """
    
    result = await database.fetch_one(query=query, values={"watermark_hash": watermark_hash})
    
    if not result:
        return {"message": "Original image not found for the given watermark hash."}, 404
    
    return {
        "watermark_hash": watermark_hash,
        "record": dict(result)
    }

async def image_has_watermarked_image_made(image_hash: str):
    """
    Checks if an image with the given hash has a watermarked version in the database.
    """
    query = """
    SELECT COUNT(*) FROM original_images
    WHERE image_hash = :hash AND watermark_hash IS NOT NULL
    """

    result = await database.fetch_val(query=query, values={"hash": image_hash})
    
    return result > 0

async def get_image_from_og_image_database(image_hash: str):
    """
    Retrieves an image from the database based on its hash.
    """
    query = """
    SELECT * FROM original_images
    WHERE image_hash = :hash
    """
    
    result = await database.fetch_one(query=query, values={"hash": image_hash})
    
    if not result:
        return {"message": "Image not found."}, 404
    
    return {
        "image_hash": image_hash,
        "record": dict(result)
    }

async def save_image_to_database(image: UploadFile, user_id: str, filename: str, bucket_path: str, image_hash: str):
    #see if image already exists
    if await image_in_og_image_database(image_hash):
        return {"message": "Image already exists in the database.",
                "image_hash": image_hash,
                "filename": filename,
                "user_id": user_id,
                "record": await get_image_from_og_image_database(image_hash)}, 200 

    print(f"Saving image with hash: {image_hash} for user: {user_id}")

    # Create image record in original imageDB
    insert_query = """
    INSERT INTO original_images (image_hash, user_id, created_at, original_image_url, image_name)
    VALUES (:image_hash, :user_id, :created_at, :original_image_url, :image_name)
    ON CONFLICT (image_hash) DO NOTHING
    RETURNING *
    """

    values = {
        "image_hash": image_hash,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "original_image_url": bucket_path,
        "image_name": filename
    }

    print(f"Executing query: {insert_query} with values: {values}")

    result = await database.fetch_one(query=insert_query, values=values)
    if not result:
        return {"message": "Failed to insert record."}, 500
    
    # Rewind file pointer so the next function can use it
    await image.seek(0)
    
    return {
        "image_hash": image_hash,
        "image_name": filename,
        "user_id": user_id,
        "original_image_url": bucket_path,
        "record": dict(result)
    }, 200

async def add_watermark_info_to_image_dataset(original_image_hash, watermarked_image_hash, watermarked_image_url):
    """
    Adds watermark information to the original image data.
    """
    update_query = """
    UPDATE original_images
    SET watermark_hash = :watermarked_image_hash,
        watermarked_image_url = :watermarked_image_url
    WHERE image_hash = :original_image_hash
    RETURNING *
    """

    values = {
        "original_image_hash": original_image_hash,
        "watermarked_image_hash": watermarked_image_hash,
        "watermarked_image_url": watermarked_image_url
    }

    print(f"Executing query: {update_query} with values: {values}")
    
    result = await database.fetch_one(query=update_query, values=values)
    
    if not result:
        return {"message": "Failed to update original image with watermark info."}, 500
    
    return {
        "original_image_hash": original_image_hash,
        "watermarked_image_hash": watermarked_image_hash,
        "watermarked_image_url": watermarked_image_url,
        "record": dict(result)
    }, 200

async def image_in_watermarked_image_database(image_hash: str):
    """
    Checks if a watermarked image with the given hash exists in the database.
    """
    query = """
    SELECT COUNT(*) FROM watermarked_images
    WHERE watermark_hash = :hash
    """

    result = await database.fetch_val(query=query, values={"hash": image_hash})
    
    return result > 0

async def get_watermarked_image_from_database(image_hash: str):
    """
    Retrieves a watermarked image from the database based on its hash.
    """
    query = """
    SELECT * FROM watermarked_images
    WHERE watermark_hash = :hash
    """
    
    result = await database.fetch_one(query=query, values={"hash": image_hash})
    
    if not result:
        return {"message": "Watermarked image not found."}, 404
    
    return {
        "watermark_hash": image_hash,
        "record": dict(result)
    }
    
async def save_watermarked_image_to_database(user_id: str, filename: str, bucket_path: str, image_hash: str):
    # Check if image already exists in watermarked image database
    if await image_in_watermarked_image_database(image_hash):
        return {"message": "Watermarked image already exists in the database.",
                "watermark_hash": image_hash,
                "watermarked_image_url": bucket_path,
                "user_id": user_id,
                "record": await get_watermarked_image_from_database(image_hash)}, 200

    print(f"Saving watermarked image with hash: {image_hash} for user: {user_id}")

    # Create image record in watermarked imageDB
    insert_query = """
    INSERT INTO watermarked_images (watermark_hash, user_id, created_at, watermark_image_url, watermarked_image_name)
    VALUES (:image_hash, :user_id, :created_at, :watermarked_image_url, :watermarked_image_name)
    ON CONFLICT (watermark_hash) DO NOTHING
    RETURNING *
    """

    values = {
        "image_hash": image_hash,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "watermarked_image_url": bucket_path,
        "watermarked_image_name": filename
    }

    print(f"Executing query: {insert_query} with values: {values}")
    result = await database.fetch_one(query=insert_query, values=values)
    if not result:
        return {"message": "Failed to insert watermarked image record."}, 500

    return {
        "image_hash": image_hash,
        "image_name": filename,
        "user_id": user_id,
        "watermarked_image_url": bucket_path,
        "record": dict(result)
    }, 200