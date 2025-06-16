CREATE TABLE watermarked_images (
    watermark_hash TEXT PRIMARY KEY, -- sha256 of the watermark image
    user_id UUID REFERENCES users(user_id),
    watermark_image BYTEA,            -- watermark image (as binary)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE original_images (
    image_hash TEXT PRIMARY KEY,                     -- sha256 of the original
    user_id UUID REFERENCES users(user_id),
    original_image BYTEA,                            -- original image (as binary)
    watermarked_image BYTEA,                         -- watermarked image (as binary)
    watermark_hash TEXT REFERENCES watermarked_images(watermark_hash), -- hash of the watermark image
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

