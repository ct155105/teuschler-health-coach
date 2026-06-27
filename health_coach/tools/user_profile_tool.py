"""ADK tools for reading and updating the user's profile."""

from datetime import date as date_cls

from google.adk.tools import ToolContext

from health_coach import config
from health_coach.services import firestore_db


def get_user_profile_tool(tool_context: ToolContext) -> dict:
    """Retrieves the user's profile, most recent weigh-in, and today's macro targets.

    Call this first, before responding to the user's first message of a
    session — it's how you learn who you're coaching and what today's
    targets are. No need to call it again later in the same session.

    Returns:
        dict: status ("success" or "error") and, on success, a `profile`
        dict containing any stored profile fields (e.g. age, sex,
        height_cm, goal), `latest_weight_kg` / `latest_weight_date`
        (None if the user has never logged a weight), and today's
        `target_calories`, `target_protein_g`, `target_carbs_g`,
        `target_fat_g`.
    """
    user_id = tool_context.state.get("user:id", config.DEFAULT_USER_ID)
    today = date_cls.today().isoformat()

    try:
        profile = firestore_db.get_user_profile(user_id=user_id, date=today)
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch user profile: {e}"}

    return {"status": "success", "profile": profile}


def set_user_profile_tool(
    tool_context: ToolContext,
    age: int | None = None,
    sex: str | None = None,
    height_cm: float | None = None,
    goal: str | None = None,
) -> dict:
    """Creates or updates the user's profile fields.

    Call this when the user tells you something new or corrected about
    their age, sex, height, or goal — e.g. during onboarding, or if they
    mention "I'm actually 31, not 30". Only pass the fields that changed;
    omitted fields are left as-is.

    Args:
        age: The user's age in years.
        sex: The user's sex, e.g. "male", "female".
        height_cm: The user's height in centimeters.
        goal: Free-text description of the user's goal, e.g.
            "lose 0.5kg/week", "maintain weight".

    Returns:
        dict: status ("success" or "error"), a human-readable message,
        and the fields that were written on success.
    """
    user_id = tool_context.state.get("user:id", config.DEFAULT_USER_ID)

    try:
        updated = firestore_db.set_user_profile(
            user_id=user_id, age=age, sex=sex, height_cm=height_cm, goal=goal
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to update user profile: {e}"}

    if not updated:
        return {"status": "error", "message": "No profile fields were provided to update."}

    return {
        "status": "success",
        "message": f"Updated profile fields: {', '.join(updated.keys())}.",
        "updated": updated,
    }
