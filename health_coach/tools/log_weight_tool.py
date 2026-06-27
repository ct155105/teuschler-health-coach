"""ADK tool for recording the user's daily weigh-in."""

from datetime import date as date_cls

from google.adk.tools import ToolContext

from health_coach import config
from health_coach.services import firestore_db


def log_weight_tool(
    weight_kg: float, tool_context: ToolContext, note: str | None = None
) -> dict:
    """Logs the user's body weight for today.

    Call this whenever the user reports a weigh-in. Only one weight entry
    is kept per day; calling this again today overwrites today's value.

    Args:
        weight_kg: The user's weight in kilograms.
        note: Optional context about the measurement, e.g. "fasted",
            "after workout". Omit if the user didn't mention any.

    Returns:
        dict: status ("success" or "error"), a human-readable message,
        and the stored weight entry on success.
    """
    user_id = tool_context.state.get("user:id", config.DEFAULT_USER_ID)
    today = date_cls.today().isoformat()

    try:
        entry = firestore_db.log_weight(
            user_id=user_id, date=today, weight_kg=weight_kg, note=note
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to log weight: {e}"}

    return {
        "status": "success",
        "message": f"Logged {weight_kg} kg for {today}.",
        "entry": entry,
    }
