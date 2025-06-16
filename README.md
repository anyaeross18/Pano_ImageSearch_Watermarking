# Pano

Pano is a web application for uploading, searching, and watermarking images using FastAPI, OpenCV, and cloud services.

## Features

- **Image Upload:** Upload images for search or watermarking.
- **Image Search:** Find visually similar or matching images using Google Vision and SIFT.
- **Watermarking:** Embed and verify watermarks in images.
- **Google OAuth:** Login with Google for secure access.

## Getting Started

### Disclaimer

This project does not have the credentials uploaded for security reasons. Please contact ar2535@cornell.edu for the entire codebase which includes the credentials and will allow the app to run fully.

This project is for educational purposes only.

### Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/pano.git
    cd pano
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Running the App

Start the FastAPI server with:

```bash
uvicorn app:app --reload --host localhost --port 8000
```

Visit [http://localhost:8000](http://localhost:8000) in your browser.

## Project Structure

```
.
├── app.py
├── backend/
│   ├── identifyPhotos.py
│   ├── watermarking.py
│   ├── imageTableManagement.py
│   └── userTableManagement.py
├── pages/
│   ├── templates/
│   │   ├── search_results.html
│   │   └── watermark_action.html
│   └── styles/
│       └── main.css
├── credentials/ (only available upon request)
├── requirements.txt
├── Dockerfile
└── README.md
```
