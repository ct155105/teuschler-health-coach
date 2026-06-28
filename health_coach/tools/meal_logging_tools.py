"""ADK tools for logging meals and checking the day's macro totals."""

from datetime import date as date_cls

from google.adk.tools import ToolContext

from health_coach.services import firestore_db


def log_meal_tool(
    name: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    tool_context: ToolContext,
) -> dict:
    """Logs a confirmed meal and updates today's consumed macro totals.

    Only call this once the meal's macros are known from a verified
    source (e.g. the nutrition database tool or explicit user input) —
    never log estimated or guessed values.

    Args:
        name: Short description of the meal, e.g. "Grilled chicken salad".
        calories: Calories in the meal.
        protein_g: Grams of protein.
        carbs_g: Grams of carbohydrates.
        fat_g: Grams of fat.

    Returns:
        dict: status ("success" or "error"), a human-readable message,
        and the stored meal record on success.
    """
    user_id = tool_context.session.user_id
    today = date_cls.today().isoformat()

    try:
        meal = firestore_db.log_meal(
            user_id=user_id,
            date=today,
            name=name,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to log meal: {e}"}

    return {
        "status": "success",
        "message": f"Logged '{name}' ({calories} kcal) for {today}.",
        "meal": meal,
    }


def get_daily_summary_tool(tool_context: ToolContext) -> dict:
    """Retrieves today's macro targets, consumed totals, and remaining macros.

    Call this before answering questions about remaining calories/macros,
    or before suggesting what to eat next, so recommendations are based
    on real logged data rather than assumptions.

    Returns:
        dict: status ("success" or "error") and, on success, the day's
        summary: target_calories, target_protein_g, target_carbs_g,
        target_fat_g, consumed_calories, consumed_protein_g,
        consumed_carbs_g, consumed_fat_g, and the corresponding
        remaining_* values.
    """
    user_id = tool_context.session.user_id
    today = date_cls.today().isoformat()

    try:
        summary = firestore_db.get_daily_summary(user_id=user_id, date=today)
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch daily summary: {e}"}

    return {"status": "success", "summary": summary}
