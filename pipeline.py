import argparse
import datetime
import json

from config import load_config
from emissions import co2_kg, summarize
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
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    conversation = client.fetch_conversation(conversation_id)
    cache_file.write_text(json.dumps(conversation, ensure_ascii=False))
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


def main():
    parser = argparse.ArgumentParser(
        description="Compute CO2 emissions for Vinted orders."
    )
    parser.add_argument(
        "fixed_location",
        help="reference location every order is routed to (e.g. 'Tübingen, DE' or '48.52,9.05')",
    )
    args = parser.parse_args()

    config = load_config()
    factor = config["truck_factor_kg_per_km"]

    client = VintedClient(config)
    geocoder = Geocoder(config)
    router = Router(config)

    fixed = geocoder.geocode(args.fixed_location)
    if not fixed:
        raise SystemExit(f"Could not geocode fixed location: {args.fixed_location!r}")
    print(f"Fixed location: {fixed['display_name']} ({fixed['lat']}, {fixed['lon']})")

    orders, pagination = client.fetch_orders()
    print(
        f"Fetched {len(orders)} orders "
        f"(total_entries={pagination.get('total_entries')})"
    )

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
        print(f"[{index}/{len(orders)}] {order.get('title')!r} -> {target}")

    totals = summarize(records, factor)
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fixed_location": fixed,
        "truck_factor_kg_per_km": factor,
        "totals": totals,
        "orders": records,
    }
    (config["data_dir"] / "emissions.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )
    (config["data_dir"] / "routes.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)
    )

    print(
        f"\nDone. {totals['routed_order_count']}/{totals['order_count']} orders routed, "
        f"{totals['total_distance_km']} km, {totals['total_co2_kg']} kg CO2."
    )


if __name__ == "__main__":
    main()
