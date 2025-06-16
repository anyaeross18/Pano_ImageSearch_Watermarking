import uuid
from credentials.database import database

async def get_or_create_user(google_id, name, email):
    query = "SELECT * FROM users WHERE google_sub = :sub"
    user = await database.fetch_one(query, values={"sub": google_id})
    
    if user:
        return user

    insert_query = """
    INSERT INTO users (user_id, email, name, google_sub, google_email)
    VALUES (:user_id, :email, :name, :google_sub, :google_email)
    RETURNING *
    """
    user_id = str(uuid.uuid4())
    values = {
        "user_id": user_id,
        "name": name,
        "email": email,
        "google_sub": google_id,
        "google_email": email
    }
    user = await database.fetch_one(insert_query, values)
    return user
    