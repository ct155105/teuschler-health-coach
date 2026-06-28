"""Centralized environment configuration for the health coach agent.

Reads from `health_coach/.env` (loaded via python-dotenv) so every module
gets its settings from one place instead of scattering `os.getenv` calls.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Google Cloud / Vertex AI model calls
GOOGLE_CLOUD_PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
GOOGLE_CLOUD_LOCATION = os.environ["GOOGLE_CLOUD_LOCATION"]

# Firestore/Storage project id — deliberately a separate var from
# GOOGLE_CLOUD_PROJECT above. Deployed Agent Runtime containers pre-set
# GOOGLE_CLOUD_PROJECT ambiently to the numeric project number (not the
# project ID), and `adk deploy` itself drops our .env's GOOGLE_CLOUD_PROJECT
# rather than passing it through. Firestore's default-database lookup
# doesn't resolve the same way by project number as by project ID, so
# firebase_admin needs its own var name that nothing else overrides.
FIRESTORE_PROJECT_ID = os.environ["FIRESTORE_PROJECT_ID"]

# Cloud Storage for Firebase bucket used to stage meal photos before
# attaching them to the agent's message as an image Part.
STORAGE_BUCKET = os.getenv(
    "STORAGE_BUCKET", f"{FIRESTORE_PROJECT_ID}.firebasestorage.app"
)

# LLM models
COACH_AGENT_MODEL = os.getenv("COACH_AGENT_MODEL", "gemini-3.5-flash")

# USDA FoodData Central — free API key: https://fdc.nal.usda.gov/api-key-signup
# Required only for nutrition_tools.lookup_nutrition_tool; None elsewhere is fine.
USDA_API_KEY = os.getenv("USDA_API_KEY")

# Firestore collection names
DAILY_SUMMARIES_COLLECTION = "daily_summaries"
MEALS_COLLECTION = "meals"
WEIGHT_ENTRIES_COLLECTION = "weight_entries"
SAVED_MEALS_COLLECTION = "saved_meals"
