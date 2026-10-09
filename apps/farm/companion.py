"""Companion planting alerts for Mosquera Farm Log.

Checks neighboring plants (adjacent cells, same plot) against known
bad/beneficial pairings and returns warnings + highlights for the map.
"""

# Canonical lowercase names.
ALIASES = {
    "tomatoes": "tomato",
    "potatoes": "potato",
    "potatos": "potato",
    "carrots": "carrot",
    "onions": "onion",
    "peppers": "pepper",
    "cucumbers": "cucumber",
    "marigolds": "marigold",
    "beans": "bean",
}

# (plant_a, plant_b) sorted -> (kind, reason). kind is "bad" or "good".
PAIRINGS = {
    ("potato", "tomato"): ("bad", "Share blight and pests — keep tomatoes and potatoes apart."),
    ("corn", "tomato"): ("bad", "Shared pests (corn earworm / tomato fruitworm)."),
    ("bean", "onion"): ("bad", "Alliums stunt the growth of beans."),
    ("bean", "garlic"): ("bad", "Garlic inhibits beans planted nearby."),
    ("carrot", "dill"): ("bad", "Mature dill stunts neighboring carrots."),
    ("cabbage", "tomato"): ("bad", "They compete — tomatoes shade out cabbage."),
    ("cucumber", "potato"): ("bad", "Potatoes inhibit cucumbers and squash."),
    ("fennel", "tomato"): ("bad", "Fennel inhibits most nearby vegetables."),
    ("marigold", "tomato"): ("good", "Marigolds repel nematodes and aphids from tomatoes."),
    ("basil", "tomato"): ("good", "Basil repels hornworms and may improve tomato flavor."),
    ("carrot", "onion"): ("good", "They confuse each other's pests (carrot fly / onion fly)."),
    ("bean", "corn"): ("good", "Beans fix nitrogen while corn gives support (Three Sisters)."),
    ("cabbage", "dill"): ("good", "Dill attracts wasps that prey on cabbage worms."),
    ("carrot", "lettuce"): ("good", "Fast lettuce marks rows; shallow and deep roots share well."),
    ("basil", "pepper"): ("good", "Basil repels thrips and flies around peppers."),
    ("bean", "cucumber"): ("good", "Beans feed nitrogen-hungry cucumbers."),
}


def normalize(name: str) -> str:
    key = (name or "").strip().lower()
    return ALIASES.get(key, key)


def pairing(a: str, b: str):
    """Return (kind, reason) for two plant names, or None."""
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return None
    return PAIRINGS.get(tuple(sorted((na, nb))))


def adjacent(p, q) -> bool:
    """Same plot neighbors: cells touching (including same cell)."""
    if p.area_id != q.area_id or p.area_id is None:
        return False
    return max(abs(p.pos_x - q.pos_x), abs(p.pos_y - q.pos_y)) <= 1


def analyze(plants: list) -> list:
    """Return alerts: [{"kind", "a", "b", "reason", "ids"}]. Bad first."""
    plants = list(plants)
    alerts = []
    for i in range(len(plants)):
        for j in range(i + 1, len(plants)):
            p, q = plants[i], plants[j]
            if not adjacent(p, q):
                continue
            hit = pairing(p.name, q.name)
            if hit:
                kind, reason = hit
                alerts.append({
                    "kind": kind, "a": p.name, "b": q.name,
                    "reason": reason, "ids": {p.id, q.id},
                })
    alerts.sort(key=lambda a: (0 if a["kind"] == "bad" else 1, a["a"], a["b"]))
    return alerts
