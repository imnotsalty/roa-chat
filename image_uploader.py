import requests
import base64

def upload_image_to_freeimage(image_bytes: bytes):
    """
    Uploads an image from bytes to freeimage.host and returns the direct URL.
    This uses the public API key provided.
    """
    FREEIMAGE_API_URL = "https://freeimage.host/api/1/upload"
    # This is a public key, but for production, it's better to get this from an environment variable.
    API_KEY = "6d207e02198a847aa98d0a2a901485a5"

    try:
        # The API requires the image to be sent as a base64 string.
        base64_image = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            'key': API_KEY,
            'action': 'upload',
            'source': base64_image,
            'format': 'json'
        }

        # Make the POST request to the API.
        response = requests.post(FREEIMAGE_API_URL, data=payload, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes

        result = response.json()

        # Check the response from the API for success.
        if result.get("status_code") == 200 and result.get("image"):
            # The direct URL to the image.
            image_url = result["image"]["url"]
            print(f"Image uploaded successfully to freeimage.host: {image_url}")
            return image_url
        else:
            error_message = result.get("status_txt", "Unknown error from freeimage.host API.")
            print(f"Failed to upload image. API Error: {error_message}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the request to freeimage.host: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during image upload: {e}")
        return None