"""Cloud Storage staging for meal photos.

Uploads raw photo bytes to Cloud Storage for Firebase and returns a
gs:// URI. The calling code (whatever receives the photo from the
client — not an ADK tool) attaches that URI to the agent's message as
an image Part, so the agent's own multimodal model sees the photo
natively rather than via a dedicated vision tool. A GCS URI is the
recommended way to send images to a deployed Agent Runtime agent (see
the adk skill's deployment.md), as opposed to inlining raw bytes.
"""

import uuid
from datetime import datetime, timezone

from firebase_admin import storage

from health_coach.services.firebase_app import app


def stage_meal_photo(user_id: str, image_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Uploads a meal photo to Cloud Storage and returns its gs:// URI.

    Args:
        user_id: The user's unique id, used to namespace the storage path.
        image_bytes: The raw photo bytes.
        content_type: The photo's MIME type, e.g. "image/jpeg", "image/png".

    Returns:
        The gs:// URI of the uploaded photo.
    """
    bucket = storage.bucket(app=app)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    blob_name = f"meal_photos/{user_id}/{timestamp}-{uuid.uuid4().hex[:8]}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type=content_type)
    return f"gs://{bucket.name}/{blob_name}"
