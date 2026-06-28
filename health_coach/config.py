"""Centralized environment configuration for the health coach agent.

Reads from `health_coach/.env` (loaded via python-dotenv) so every module
gets its settings from one place instead of scattering `os.getenv` calls.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Google Cloud / Firestore
GOOGLE_CLOUD_PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
GOOGLE_CLOUD_LOCATION = os.environ["GOOGLE_CLOUD_LOCATION"]

# Cloud Storage for Firebase bucket used to stage meal photos before
# attaching them to the agent's message as an image Part.
STORAGE_BUCKET = os.getenv(
    "STORAGE_BUCKET", f"{GOOGLE_CLOUD_PROJECT}.firebasestorage.app"
)

# LLM models
COACH_AGENT_MODEL = os.getenv("COACH_AGENT_MODEL", "gemini-3.5-flash")

# Single-user app for now: tools fall back to this id when the session
# hasn't set a "user:id" state value yet.
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "default_user")

# USDA FoodData Central — free API key: https://fdc.nal.usda.gov/api-key-signup
# Required only for nutrition_tools.lookup_nutrition_tool; None elsewhere is fine.
USDA_API_KEY = os.getenv("USDA_API_KEY")

# Firestore collection names
DAILY_SUMMARIES_COLLECTION = "daily_summaries"
MEALS_COLLECTION = "meals"
WEIGHT_ENTRIES_COLLECTION = "weight_entries"
SAVED_MEALS_COLLECTION = "saved_meals"
