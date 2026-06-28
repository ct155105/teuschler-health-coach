"""Firestore data-access layer.

Plain, standalone functions — no ADK imports here. Tools in
`health_coach/tools/` call these; this module owns all Firestore
read/write logic so the tools stay thin and declarative.

Data layout (per user):
    users/{user_id}                                -> profile (age, sex, height_in, goal, ...)
    users/{user_id}/daily_summaries/{date}        -> targets + running totals + ADK session_id
    users/{user_id}/daily_summaries/{date}/meals/{meal_id} -> logged meals
    users/{user_id}/weight_entries/{date}          -> one weigh-in per day
    users/{user_id}/saved_meals/{hash(food_description)} -> cached per-100g nutrition match
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore

from health_coach import config
from health_coach.services.firebase_app import app

_db = firestore.client(app)


def _saved_meal_key(food_description: str) -> str:
    """Normalizes a food description into a stable Firestore document id."""
    return hashlib.sha1(food_description.strip().lower().encode()).hexdigest()


def get_saved_meal(user_id: str, food_description: str) -> dict[str, Any] | None:
    """Looks up a previously cached nutrition match for this exact food description.

    Matching is exact-text (case/whitespace-insensitive) — reusing the
    same description for a recurring food is what makes this hit.

    Args:
        user_id: The user's unique id.
        food_description: The plain-language food description used as the cache key.

    Returns:
        The cached per-100g nutrition dict (`description`, `calories`,
        `protein_g`, `carbs_g`, `fat_g`), or None on a cache miss.
    """
    doc = (
        _db.collection("users")
        .document(user_id)
        .collection(config.SAVED_MEALS_COLLECTION)
        .document(_saved_meal_key(food_description))
        .get()
    )
    return doc.to_dict() if doc.exists else None


def set_saved_meal(user_id: str, food_description: str, match: dict[str, Any]) -> None:
    """Caches a per-100g nutrition match so future lookups skip the USDA API call.

    Args:
        user_id: The user's unique id.
        food_description: The plain-language food description used as the cache key.
        match: The per-100g nutrition dict to cache.
    """
    (
        _db.collection("users")
        .document(user_id)
        .collection(config.SAVED_MEALS_COLLECTION)
        .document(_saved_meal_key(food_description))
        .set(match)
    )


def get_user_profile(user_id: str, date: str) -> dict[str, Any]:
    """Fetches the user's static profile, latest weigh-in, and today's targets.

    This is the agent's session-bootstrap read: everything it needs to know
    before responding to the first message of the day.

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD) for "today", used to look up the
            current day's macro targets.

    Returns:
        A dict with the profile fields stored on `users/{user_id}`
        (e.g. age, sex, height_in, goal — whatever has been set; empty
        dict if the profile doc doesn't exist yet), plus `latest_weight_lb`
        / `latest_weight_date` (None if no weigh-in has ever been logged),
        plus today's `target_calories`, `target_protein_g`,
        `target_carbs_g`, `target_fat_g`.
    """
    profile_doc = _db.collection("users").document(user_id).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {}

    latest_weight_query = (
        _db.collection("users")
        .document(user_id)
        .collection(config.WEIGHT_ENTRIES_COLLECTION)
        .order_by("date", direction=firestore.Query.DESCENDING)
        .limit(1)
        .get()
    )
    if latest_weight_query:
        latest_entry = latest_weight_query[0].to_dict()
        profile["latest_weight_lb"] = latest_entry.get("weight_lb")
        profile["latest_weight_date"] = latest_entry.get("date")
    else:
        profile["latest_weight_lb"] = None
        profile["latest_weight_date"] = None

    today_summary = get_daily_summary(user_id=user_id, date=date)
    profile["target_calories"] = today_summary["target_calories"]
    profile["target_protein_g"] = today_summary["target_protein_g"]
    profile["target_carbs_g"] = today_summary["target_carbs_g"]
    profile["target_fat_g"] = today_summary["target_fat_g"]

    return profile


def get_session_id_for_date(user_id: str, date: str) -> str | None:
    """Looks up the ADK session id previously recorded for this user's day.

    Used to resume the same ADK session across multiple calls within one
    calendar day, without relying on a deterministic/custom session id
    (the managed Agent Runtime session service only reliably supports
    auto-generated ids — see `deployment.md` in the adk skill).

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD).

    Returns:
        The recorded session id, or None if no session has been started
        for this user on this date yet.
    """
    doc = (
        _db.collection("users")
        .document(user_id)
        .collection(config.DAILY_SUMMARIES_COLLECTION)
        .document(date)
        .get()
    )
    if not doc.exists:
        return None
    return doc.to_dict().get("session_id")


def set_session_id_for_date(user_id: str, date: str, session_id: str) -> None:
    """Records the ADK session id associated with this user's day.

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD).
        session_id: The session id returned by `SessionService.create_session`.
    """
    (
        _db.collection("users")
        .document(user_id)
        .collection(config.DAILY_SUMMARIES_COLLECTION)
        .document(date)
        .set({"session_id": session_id}, merge=True)
    )


def set_user_profile(
    user_id: str,
    age: int | None = None,
    sex: str | None = None,
    height_in: float | None = None,
    goal: str | None = None,
) -> dict[str, Any]:
    """Creates or updates fields on the user's static profile doc.

    Only the fields passed (non-None) are written; existing fields not
    passed are left untouched (merge write, not overwrite).

    Args:
        user_id: The user's unique id.
        age: The user's age in years.
        sex: The user's sex, e.g. "male", "female".
        height_in: The user's height in inches.
        goal: Free-text description of the user's goal, e.g.
            "lose 1lb/week", "maintain weight".

    Returns:
        The merged set of fields written in this call.
    """
    updates = {
        k: v
        for k, v in {
            "age": age,
            "sex": sex,
            "height_in": height_in,
            "goal": goal,
        }.items()
        if v is not None
    }
    _db.collection("users").document(user_id).set(updates, merge=True)
    return updates


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
    # A doc can exist with only some fields set (e.g. log_meal's merge
    # write only ever sets consumed_*, never target_*, if a meal gets
    # logged before targets are) — backfill defaults so every key below
    # is always present, not just safely defaulted for this computation.
    for key in (
        "target_calories",
        "target_protein_g",
        "target_carbs_g",
        "target_fat_g",
        "consumed_calories",
        "consumed_protein_g",
        "consumed_carbs_g",
        "consumed_fat_g",
    ):
        summary.setdefault(key, 0)
    summary["remaining_calories"] = summary["target_calories"] - summary["consumed_calories"]
    summary["remaining_protein_g"] = (
        summary["target_protein_g"] - summary["consumed_protein_g"]
    )
    summary["remaining_carbs_g"] = summary["target_carbs_g"] - summary["consumed_carbs_g"]
    summary["remaining_fat_g"] = summary["target_fat_g"] - summary["consumed_fat_g"]
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
    user_id: str, date: str, weight_lb: float, note: str | None = None
) -> dict[str, Any]:
    """Records a weight measurement for a given day, overwriting any prior entry for that day.

    Args:
        user_id: The user's unique id.
        date: ISO date string (YYYY-MM-DD) for the weigh-in.
        weight_lb: The user's weight in pounds.
        note: Optional free-text note (e.g. "after workout", "fasted").

    Returns:
        The stored weight entry record.
    """
    entry = {
        "date": date,
        "weight_lb": weight_lb,
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
