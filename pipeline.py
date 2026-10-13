import argparse
import datetime

import jsonstore
from config import load_config
from emissions import co2_kg, equivalents, summarize
from geo import Geocoder
from routing import Router
from vinted_client import VintedClient


def extract_seller(conversation):
    """Pull the seller city/country out of a conversation payload."""
    transaction = conversation.get("transaction") or {}
    opposite_user = conversation.get("opposite_user") or {}
    city = transaction.get("seller_city")
    if not city:
        return None
    return {"city": city, "country": opposite_user.get("country_code")}


def location_query(seller):
    if seller["country"]:
        return f"{seller['city']}, {seller['country']}"
    return seller["city"]


def load_conversation(client, conversation_id, cache_dir):
    cache_file = cache_dir / f"{conversation_id}.json"
    cached = jsonstore.load(cache_file, None)
    if cached is not None:
        return cached
    conversation = client.fetch_conversation(conversation_id)
    jsonstore.save(cache_file, conversation)
    return conversation


def build_record(order, seller, seller_fix, route, factor):
    price = order.get("price") or {}
    record = {
        "conversation_id": order["conversation_id"],
        "transaction_id": order.get("transaction_id"),
        "title": order.get("title"),
        "date": order.get("date"),
        "status": order.get("status"),
        "price_amount": price.get("amount"),
        "price_currency": price.get("currency_code"),
        "photo_url": order.get("photo_url"),
        "seller_city": seller["city"] if seller else None,
        "seller_country": seller["country"] if seller else None,
        "seller_lat": seller_fix["lat"] if seller_fix else None,
        "seller_lon": seller_fix["lon"] if seller_fix else None,
        "route_distance_m": None,
        "route_km": None,
        "route_duration_s": None,
        "co2_kg": None,
    }
    if route:
        record["route_distance_m"] = round(route["distance_m"], 1)
        record["route_km"] = round(route["distance_m"] / 1000.0, 3)
        record["route_duration_s"] = round(route["duration_s"], 1)
        record["co2_kg"] = round(co2_kg(route["distance_m"], factor), 3)
    return record


def run_pipeline(fixed_location, config=None, on_progress=None, fixed_point=None):
    """Run the full calculation and return the emissions payload.

    on_progress, if given, is called as on_progress(message, current, total).
    fixed_point, if given, is a resolved {'lat','lon','display_name'} and skips
    geocoding the reference location.
    """
    config = config or load_config()
    factor = config["truck_factor_kg_per_km"]

    def emit(message, current=None, total=None):
        if on_progress:
            on_progress(message, current, total)

    client = VintedClient(config)
    geocoder = Geocoder(config)
    router = Router(config)

    if fixed_point is not None:
        fixed = fixed_point
        emit(f"Fixed location: {fixed.get('display_name', fixed_location)}")
    else:
        fixed = geocoder.geocode(fixed_location)
        if not fixed:
            raise ValueError(f"Could not geocode fixed location: {fixed_location!r}")
        emit(f"Fixed location: {fixed['display_name']}")

    orders, pagination = client.fetch_orders()
    total_orders = len(orders)
    emit(f"Fetched {total_orders} orders (total_entries={pagination.get('total_entries')})", 0, total_orders)

    conv_dir = config["cache_dir"] / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)

    records = []
    features = []
    for index, order in enumerate(orders, 1):
        conversation = load_conversation(client, order["conversation_id"], conv_dir)
        seller = extract_seller(conversation)
        seller_fix = geocoder.geocode(location_query(seller)) if seller else None
        route = router.route(seller_fix, fixed) if seller_fix else None

        record = build_record(order, seller, seller_fix, route, factor)
        records.append(record)

        if route and route.get("geometry"):
            features.append(
                {
                    "type": "Feature",
                    "geometry": route["geometry"],
                    "properties": {
                        "conversation_id": record["conversation_id"],
                        "transaction_id": record["transaction_id"],
                        "title": record["title"],
                        "seller_city": record["seller_city"],
                        "route_km": record["route_km"],
                        "co2_kg": record["co2_kg"],
                    },
                }
            )

        target = f"{record['seller_city']} ({record['route_km']} km)" if route else "no route"
        emit(f"[{index}/{total_orders}] {order.get('title')!r} -> {target}", index, total_orders)

    totals = summarize(records, factor)
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fixed_location": fixed,
        "truck_factor_kg_per_km": factor,
        "totals": totals,
        "equivalents": equivalents(totals["total_co2_kg"], config.get("equivalents", [])),
        "orders": records,
    }
    jsonstore.save(config["data_dir"] / "emissions.json", payload)
    jsonstore.save(
        config["data_dir"] / "routes.geojson",
        {"type": "FeatureCollection", "features": features},
    )
    emit("Finished", total_orders, total_orders)
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Compute CO2 emissions for Vinted orders."
    )
    parser.add_argument(
        "fixed_location",
        help="reference location every order is routed to (e.g. 'Tübingen, DE' or '48.52,9.05')",
    )
    args = parser.parse_args()

    def print_progress(message, current=None, total=None):
        print(message)

    payload = run_pipeline(args.fixed_location, on_progress=print_progress)
    totals = payload["totals"]
    print(
        f"\nDone. {totals['routed_order_count']}/{totals['order_count']} orders routed, "
        f"{totals['total_distance_km']} km, {totals['total_co2_kg']} kg CO2."
    )


if __name__ == "__main__":
    main()
