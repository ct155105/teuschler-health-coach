"""USDA FoodData Central API client — authoritative per-100g nutrient lookups.

Plain HTTP client, no ADK imports. Tools in `health_coach/tools/` call
this; it owns all FoodData Central request/response handling.

Two-call lookup: the `/foods/search` endpoint often omits proximate
macros (Energy/Protein/Fat/Carbohydrate) for many entries, but the
`/food/{fdcId}` detail endpoint reliably reports them for "SR Legacy"
foods — so we search to find a matching fdcId, then fetch its detail.
"""

from typing import Any

import httpx

from health_coach import config

_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# USDA standard nutrient numbers for the four macros we track (per 100g).
_NUTRIENT_NUMBERS = {
    "208": "calories",
    "203": "protein_g",
    "204": "fat_g",
    "205": "carbs_g",
}


def search_food(query: str) -> dict[str, Any] | None:
    """Looks up per-100g macros for a food via USDA FoodData Central.

    Restricted to "SR Legacy" data, which reliably reports complete
    proximate macros per 100g — unlike some "Foundation"/"Branded"
    entries, which can omit these or report per-label-serving in
    inconsistent units.

    Args:
        query: Free-text food description, e.g. "grilled chicken breast".

    Returns:
        A dict with `fdc_id`, `description`, and per-100g `calories`,
        `protein_g`, `carbs_g`, `fat_g` — or None if no match was found.
    """
    if not config.USDA_API_KEY:
        raise RuntimeError(
            "USDA_API_KEY is not set. Get a free key at "
            "https://fdc.nal.usda.gov/api-key-signup and set it in health_coach/.env"
        )

    search_response = httpx.get(
        f"{_BASE_URL}/foods/search",
        params={
            "api_key": config.USDA_API_KEY,
            "query": query,
            "dataType": "SR Legacy",
            "pageSize": 1,
        },
        timeout=10.0,
    )
    search_response.raise_for_status()
    foods = search_response.json().get("foods", [])
    if not foods:
        return None
    fdc_id = foods[0]["fdcId"]

    detail_response = httpx.get(
        f"{_BASE_URL}/food/{fdc_id}",
        params={"api_key": config.USDA_API_KEY},
        timeout=10.0,
    )
    detail_response.raise_for_status()
    detail = detail_response.json()

    macros = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    for nutrient in detail.get("foodNutrients", []):
        number = nutrient.get("nutrient", {}).get("number")
        key = _NUTRIENT_NUMBERS.get(number)
        if key is not None:
            macros[key] = nutrient.get("amount") or 0.0

    return {
        "fdc_id": fdc_id,
        "description": detail.get("description", foods[0]["description"]),
        **macros,
    }
