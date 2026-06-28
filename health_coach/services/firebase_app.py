"""Single shared `firebase_admin` app instance.

Both `firestore_db.py` and `image_staging.py` need an initialized app —
centralized here so `initialize_app` is only ever called once per process.
"""

import firebase_admin

from health_coach import config

app = firebase_admin.initialize_app(
    options={
        "projectId": config.GOOGLE_CLOUD_PROJECT,
        "storageBucket": config.STORAGE_BUCKET,
    }
)
