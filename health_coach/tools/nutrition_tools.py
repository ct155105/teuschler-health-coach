"""ADK tool for looking up per-portion macros, with a per-user cache for repeat foods."""

from google.adk.tools import ToolContext

from health_coach.services import firestore_db, usda_fdc


def lookup_nutrition_tool(
    food_description: str, quantity_g: float, tool_context: ToolContext
) -> dict:
    """Looks up macros for a food item, reusing a per-user cache for repeat foods.

    Call this for each distinct food item you identify (e.g. from a meal
    photo) before logging the meal — never estimate calories/macros from
    visual judgment alone. After looking up every item in a meal, sum
    the results yourself before calling log_meal_tool.

    For foods the user eats regularly, reuse the exact same
    food_description text each time (e.g. always "my usual protein
    shake", not a rephrased variant) — the cache matches on exact text,
    so consistent phrasing avoids a redundant nutrition database lookup.

    Args:
        food_description: Plain-language food name, e.g. "grilled chicken
            breast", "white rice, cooked". Be specific but simple, and
            consistent across calls for the same food.
        quantity_g: Estimated portion size in grams.

    Returns:
        dict: status ("success" or "error"). On success: `description`
        (the matched food name — compare it to what you expected, since
        it may not be an exact match) and scaled `calories`, `protein_g`,
        `carbs_g`, `fat_g` for the given quantity.
    """
    user_id = tool_context.session.user_id

    match = firestore_db.get_saved_meal(user_id=user_id, food_description=food_description)
    if match is None:
        try:
            match = usda_fdc.search_food(food_description)
        except Exception as e:
            return {"status": "error", "message": f"Nutrition lookup failed: {e}"}

        if match is None:
            return {
                "status": "error",
                "message": f"No USDA FoodData Central match found for '{food_description}'.",
            }

        firestore_db.set_saved_meal(
            user_id=user_id, food_description=food_description, match=match
        )

    scale = quantity_g / 100.0
    return {
        "status": "success",
        "description": match["description"],
        "calories": round(match["calories"] * scale, 1),
        "protein_g": round(match["protein_g"] * scale, 1),
        "carbs_g": round(match["carbs_g"] * scale, 1),
        "fat_g": round(match["fat_g"] * scale, 1),
    }
