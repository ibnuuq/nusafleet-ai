"""
Load CSV hasil generator ke Postgres+PostGIS.
Jalankan setelah schema.sql sudah diterapkan (docker compose up membuatnya otomatis).

    DATABASE_URL=postgresql://user:pass@localhost:5432/nusafleet python load.py
"""
import os
import sys

import pandas as pd
import psycopg2
import psycopg2.extras as extras

SEEDS_DIR = os.path.join(os.path.dirname(__file__), "..", "seeds")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://nusafleet_admin:change_me_admin@localhost:5432/nusafleet")


def load_table(conn, csv_name, table, columns, geom_from_latlon=False):
    path = os.path.join(SEEDS_DIR, f"{csv_name}.csv")
    df = pd.read_csv(path)
    cur = conn.cursor()

    insert_cols = list(columns)
    if geom_from_latlon:
        insert_cols = [c for c in insert_cols if c != "geom"]

    cur.execute(f"TRUNCATE fleet.{table} CASCADE")

    rows = []
    for _, r in df.iterrows():
        row = []
        for c in insert_cols:
            v = r.get(c)
            if pd.isna(v):
                v = None
            row.append(v)
        if geom_from_latlon:
            lat, lon = r.get("lat"), r.get("lon")
            row.append(None if pd.isna(lat) else float(lat))
            row.append(None if pd.isna(lon) else float(lon))
        rows.append(tuple(row))

    if geom_from_latlon:
        col_list = ", ".join(insert_cols + ["_lat", "_lon"])
        placeholders = ", ".join(["%s"] * (len(insert_cols)))
        sql = f"""INSERT INTO fleet.{table} ({', '.join(insert_cols)}, geom)
                  VALUES ({placeholders}, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)"""
    else:
        col_list = ", ".join(insert_cols)
        placeholders = ", ".join(["%s"] * len(insert_cols))
        sql = f"INSERT INTO fleet.{table} ({col_list}) VALUES ({placeholders})"

    extras.execute_batch(cur, sql, rows, page_size=2000)
    conn.commit()
    print(f"  {table:<24} {len(rows):>9,} rows loaded")


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        # regions: load kolom non-geo dulu dengan constraint centroid dilonggarkan sementara,
        # lalu isi centroid via UPDATE (constraint NOT NULL tetap terjaga sebelum commit final)
        cur = conn.cursor()
        cur.execute("ALTER TABLE fleet.regions ALTER COLUMN centroid DROP NOT NULL")
        conn.commit()
        load_table(conn, "regions", "regions",
                   ["region_id", "region_code", "region_name", "island", "congestion_index"],
                   geom_from_latlon=False)
        df = pd.read_csv(os.path.join(SEEDS_DIR, "regions.csv"))
        for _, r in df.iterrows():
            cur.execute(
                "UPDATE fleet.regions SET centroid = ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography WHERE region_id=%s",
                (r.lon, r.lat, r.region_id))
        cur.execute("ALTER TABLE fleet.regions ALTER COLUMN centroid SET NOT NULL")
        conn.commit()

        load_table(conn, "locations", "locations",
                   ["location_id", "location_code", "name", "loc_type", "region_id", "address"],
                   geom_from_latlon=True)

        load_table(conn, "vehicle_models", "vehicle_models",
                   ["model_id", "model_code", "manufacturer", "model_name", "v_class",
                    "capacity_kg", "fuel_type", "nominal_km_per_liter", "year_introduced"])

        load_table(conn, "vehicles", "vehicles",
                   ["vehicle_id", "plate_number", "model_id", "home_depot_id", "acquisition_date",
                    "odometer_km", "status", "service_interval_km", "last_service_odometer_km",
                    "tank_capacity_liter"])

        load_table(conn, "drivers", "drivers",
                   ["driver_id", "driver_code", "full_name", "license_type", "hire_date",
                    "home_depot_id", "employment_status", "birth_year", "safety_score"])

        load_table(conn, "customers", "customers",
                   ["customer_id", "customer_code", "company_name", "segment", "tier", "region_id",
                    "primary_location_id", "contract_start_date", "sla_hours", "is_active"])

        load_table(conn, "customer_sla_history", "customer_sla_history",
                   ["customer_id", "effective_from", "sla_hours"])

        load_table(conn, "orders", "orders",
                   ["order_id", "order_code", "customer_id", "order_date", "requested_pickup_at",
                    "promised_delivery_at", "origin_location_id", "destination_location_id",
                    "weight_kg", "volume_m3", "declared_value_idr", "priority", "status"])

        load_table(conn, "deliveries", "deliveries",
                   ["delivery_id", "order_id", "attempt_no", "vehicle_id", "driver_id",
                    "dispatched_at", "arrived_at", "delivered_at", "planned_distance_km",
                    "actual_distance_km", "status", "failure_reason", "pod_signed",
                    "delivery_cost_idr", "fuel_cost_idr", "toll_cost_idr", "allowance_idr",
                    "overtime_cost_idr"])

        load_table(conn, "fuel_transactions", "fuel_transactions",
                   ["fuel_id", "vehicle_id", "driver_id", "station_location_id", "transacted_at",
                    "liters", "price_per_liter_idr", "total_cost_idr", "odometer_km", "payment_method"])

        load_table(conn, "maintenance", "maintenance",
                   ["maintenance_id", "vehicle_id", "mtc_type", "scheduled_date", "performed_date",
                    "odometer_km", "workshop_location_id", "cost_idr", "downtime_hours", "notes"])

        load_table(conn, "vehicle_events", "vehicle_events",
                   ["event_id", "vehicle_id", "driver_id", "delivery_id", "ev_type", "occurred_at",
                    "severity", "metadata"])

        print("\nSelesai load ke Postgres.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
