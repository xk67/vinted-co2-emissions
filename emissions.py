def co2_kg(distance_m, truck_factor_kg_per_km):
    """CO2 in kg for a road distance, using a per-km truck emission factor."""
    if distance_m is None:
        return None
    return (distance_m / 1000.0) * truck_factor_kg_per_km


def summarize(orders, truck_factor_kg_per_km):
    routed = [o for o in orders if o.get("route_distance_m") is not None]
    total_distance_m = sum(o["route_distance_m"] for o in routed)
    total_co2_kg = sum(o["co2_kg"] for o in routed if o["co2_kg"] is not None)
    return {
        "order_count": len(orders),
        "routed_order_count": len(routed),
        "total_distance_km": round(total_distance_m / 1000.0, 3),
        "total_co2_kg": round(total_co2_kg, 3),
        "truck_factor_kg_per_km": truck_factor_kg_per_km,
    }
