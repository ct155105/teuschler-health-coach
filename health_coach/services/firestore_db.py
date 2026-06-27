"""Firestore data-access layer.

Plain, standalone functions — no ADK imports here. Tools in
`health_coach/tools/` call these; this module owns all Firestore
read/write logic so the tools stay thin and declarative.

Data layout (per user):
    users/{user_id}/daily_summaries/{date}        -> targets + running totals
    users/{user_id}/daily_summaries/{date}/meals/{meal_id} -> logged meals
    users/{user_id}/weight_entries/{date}          -> one weigh-in per day
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import firestore

from health_coach import config

_app = firebase_admin.initialize_app(options={"projectId": config.GOOGLE_CLOUD_PROJECT})
_db = firestore.client(_app)


def get_daily_summary(user_id: str, date: str) -> dict[str, Any]:
    """Fetches the user's targets and running totals for a given day.

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD) identifying the daily session.

    Returns:
        The daily summary dict (targets + consumed totals + remaining
        macros), or a default all-zero summary if no document exists yet.
    """
    doc_ref = (
        _db.collection("users")
        .document(user_id)
        .collection(config.DAILY_SUMMARIES_COLLECTION)
        .document(date)
    )
    doc = doc_ref.get()

    if not doc.exists:
        return {
            "date": date,
            "target_calories": 0,
            "target_protein_g": 0,
            "target_carbs_g": 0,
            "target_fat_g": 0,
            "consumed_calories": 0,
            "consumed_protein_g": 0,
            "consumed_carbs_g": 0,
            "consumed_fat_g": 0,
        }

    summary = doc.to_dict()
    summary["date"] = date
    summary["remaining_calories"] = summary.get("target_calories", 0) - summary.get(
        "consumed_calories", 0
    )
    summary["remaining_protein_g"] = summary.get("target_protein_g", 0) - summary.get(
        "consumed_protein_g", 0
    )
    summary["remaining_carbs_g"] = summary.get("target_carbs_g", 0) - summary.get(
        "consumed_carbs_g", 0
    )
    summary["remaining_fat_g"] = summary.get("target_fat_g", 0) - summary.get(
        "consumed_fat_g", 0
    )
    return summary


def log_meal(
    user_id: str,
    date: str,
    name: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> dict[str, Any]:
    """Records a meal and increments the day's consumed macro totals.

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD) for the daily session this meal belongs to.
        name: Human-readable meal description (e.g. "Grilled chicken salad").
        calories: Calories in the meal.
        protein_g: Grams of protein.
        carbs_g: Grams of carbohydrates.
        fat_g: Grams of fat.

    Returns:
        The created meal record, including its generated id.
    """
    daily_ref = (
        _db.collection("users")
        .document(user_id)
        .collection(config.DAILY_SUMMARIES_COLLECTION)
        .document(date)
    )
    meal_id = str(uuid.uuid4())
    meal_record = {
        "id": meal_id,
        "name": name,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }

    daily_ref.collection(config.MEALS_COLLECTION).document(meal_id).set(meal_record)
    daily_ref.set(
        {
            "consumed_calories": firestore.Increment(calories),
            "consumed_protein_g": firestore.Increment(protein_g),
            "consumed_carbs_g": firestore.Increment(carbs_g),
            "consumed_fat_g": firestore.Increment(fat_g),
        },
        merge=True,
    )

    return meal_record


def log_weight(
    user_id: str, date: str, weight_kg: float, note: str | None = None
) -> dict[str, Any]:
    """Records a weight measurement for a given day, overwriting any prior entry for that day.

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD) for the weigh-in.
        weight_kg: The user's weight in kilograms.
        note: Optional free-text note (e.g. "after workout", "fasted").

    Returns:
        The stored weight entry record.
    """
    entry = {
        "date": date,
        "weight_kg": weight_kg,
        "note": note,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    (
        _db.collection("users")
        .document(user_id)
        .collection(config.WEIGHT_ENTRIES_COLLECTION)
        .document(date)
        .set(entry)
    )
    return entry
