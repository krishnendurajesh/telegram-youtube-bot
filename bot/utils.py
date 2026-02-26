import re
from urllib.parse import urlparse, parse_qs


import requests

def extract_video_id(url_or_text: str):
    """
    Extracts video ID from various YouTube URL formats or the ID itself.
    """
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",  # Handles v=ID, /ID, /v/ID
        r"youtu\.be\/([0-9A-Za-z_-]{11})",  # Handles youtu.be/ID
        r"youtube\.com\/embed\/([0-9A-Za-z_-]{11})",  # Handles embed
        r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})", # Handles Shorts
        r"youtube\.com\/live\/([0-9A-Za-z_-]{11})",   # Handles Live
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_text)
        if match:
            return match.group(1)
            
    # Check if the text itself is an ID
    if re.match(r"^[0-9A-Za-z_-]{11}$", url_or_text):
        return url_or_text

    return None

def check_link_validity(url: str):
    """
    Checks if a URL is accessible by performing a HEAD request.
    """
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except Exception:
        return False