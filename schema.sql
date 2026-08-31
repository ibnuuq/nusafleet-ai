-- =====================================================================
-- NusaFleet AI — schema.sql
-- PostgreSQL 16 + PostGIS 3.4
--
-- CATATAN PENTING:
-- Beberapa constraint sengaja TIDAK dipasang supaya data quality trap
-- (D1, D3, D5, D7) bisa hidup di dalam data. Setiap kelalaian yang
-- disengaja diberi tanda [TRAP].
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP SCHEMA IF EXISTS fleet CASCADE;
CREATE SCHEMA fleet;
SET search_path = fleet, public;

-- ---------------------------------------------------------------------
-- ENUM types
-- ---------------------------------------------------------------------
CREATE TYPE location_type   AS ENUM ('depot','workshop','fuel_station','rest_area','customer_site');
CREATE TYPE customer_segment AS ENUM ('fmcg','manufacturing','ecommerce','retail','pharma');
CREATE TYPE customer_tier   AS ENUM ('bronze','silver','gold','platinum');
CREATE TYPE vehicle_class   AS ENUM ('van','cdd','cde','wingbox','tronton','tractor_head');
CREATE TYPE vehicle_status  AS ENUM ('active','in_maintenance','retired');
CREATE TYPE license_type    AS ENUM ('B1','B2','B2_UMUM');
CREATE TYPE employment_status AS ENUM ('permanent','contract','resigned');
CREATE TYPE order_priority  AS ENUM ('standard','express','critical');
CREATE TYPE order_status    AS ENUM ('created','assigned','in_transit','delivered','failed','cancelled');
CREATE TYPE delivery_status AS ENUM ('delivered','failed','returned','cancelled');
CREATE TYPE failure_reason  AS ENUM ('customer_closed','address_not_found','refused','vehicle_breakdown','document_issue');
CREATE TYPE payment_method  AS ENUM ('fuel_card','cash');
CREATE TYPE maintenance_type AS ENUM ('preventive','corrective','inspection');
CREATE TYPE event_type      AS ENUM ('harsh_braking','overspeed','idle_excess','geofence_exit','engine_fault','breakdown','accident');

-- ---------------------------------------------------------------------
-- regions
-- ---------------------------------------------------------------------
CREATE TABLE regions (
    region_id        smallint PRIMARY KEY,
    region_code      text NOT NULL UNIQUE,
    region_name      text NOT NULL,
    island           text NOT NULL,
    centroid         geography(Point,4326) NOT NULL,
    congestion_index numeric(3,2) NOT NULL
);
COMMENT ON COLUMN regions.congestion_index IS 'Faktor pengali transit time. 1.00 = baseline.';

-- ---------------------------------------------------------------------
-- locations
-- ---------------------------------------------------------------------
CREATE TABLE locations (
    location_id   bigserial PRIMARY KEY,
    location_code text NOT NULL UNIQUE,
    name          text NOT NULL,
    loc_type      location_type NOT NULL,
    region_id     smallint NOT NULL REFERENCES regions(region_id),
    address       text,
    geom          geography(Point,4326) NOT NULL
);
CREATE INDEX idx_locations_geom   ON locations USING GIST (geom);
CREATE INDEX idx_locations_type   ON locations (loc_type);
CREATE INDEX idx_locations_region ON locations (region_id);

-- ---------------------------------------------------------------------
-- customers
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    customer_id         bigserial PRIMARY KEY,
    customer_code       text NOT NULL UNIQUE,
    company_name        text NOT NULL,
    segment             customer_segment NOT NULL,
    tier                customer_tier NOT NULL,
    region_id           smallint NOT NULL REFERENCES regions(region_id),
    primary_location_id bigint REFERENCES locations(location_id),
    contract_start_date date NOT NULL,
    sla_hours           smallint NOT NULL,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_customers_segment_tier ON customers (segment, tier);
CREATE INDEX idx_customers_region       ON customers (region_id);

-- Riwayat perubahan SLA. Tanpa tabel ini, anomali A10 tidak bisa dibuktikan.
CREATE TABLE customer_sla_history (
    sla_history_id bigserial PRIMARY KEY,
    customer_id    bigint NOT NULL REFERENCES customers(customer_id),
    effective_from date NOT NULL,
    sla_hours      smallint NOT NULL
);
CREATE INDEX idx_sla_hist_cust ON customer_sla_history (customer_id, effective_from);

-- ---------------------------------------------------------------------
-- vehicle_models
-- ---------------------------------------------------------------------
CREATE TABLE vehicle_models (
    model_id             smallserial PRIMARY KEY,
    model_code           text NOT NULL UNIQUE,
    manufacturer         text NOT NULL,
    model_name           text NOT NULL,
    v_class              vehicle_class NOT NULL,
    capacity_kg          integer NOT NULL,
    fuel_type            text NOT NULL DEFAULT 'diesel',
    nominal_km_per_liter numeric(4,2) NOT NULL,
    year_introduced      smallint NOT NULL
);

-- ---------------------------------------------------------------------
-- vehicles
-- ---------------------------------------------------------------------
CREATE TABLE vehicles (
    vehicle_id                bigserial PRIMARY KEY,
    plate_number              text NOT NULL UNIQUE,
    model_id                  smallint NOT NULL REFERENCES vehicle_models(model_id),
    home_depot_id             bigint NOT NULL REFERENCES locations(location_id),
    acquisition_date          date NOT NULL,
    odometer_km               integer NOT NULL,
    status                    vehicle_status NOT NULL,
    service_interval_km       integer NOT NULL,
    last_service_odometer_km  integer NOT NULL,
    tank_capacity_liter       smallint NOT NULL
);
CREATE INDEX idx_vehicles_model  ON vehicles (model_id);
CREATE INDEX idx_vehicles_depot  ON vehicles (home_depot_id);
CREATE INDEX idx_vehicles_status ON vehicles (status);

-- ---------------------------------------------------------------------
-- drivers
-- ---------------------------------------------------------------------
CREATE TABLE drivers (
    driver_id         bigserial PRIMARY KEY,
    driver_code       text NOT NULL UNIQUE,
    full_name         text NOT NULL,
    license_type      license_type NOT NULL,
    hire_date         date NOT NULL,
    home_depot_id     bigint NOT NULL REFERENCES locations(location_id),
    employment_status employment_status NOT NULL,
    birth_year        smallint,
    safety_score      numeric(4,1)
);
CREATE INDEX idx_drivers_depot   ON drivers (home_depot_id);
CREATE INDEX idx_drivers_license ON drivers (license_type);

-- ---------------------------------------------------------------------
-- orders
-- ---------------------------------------------------------------------
CREATE TABLE orders (
    order_id             bigserial PRIMARY KEY,
    order_code           text NOT NULL UNIQUE,
    customer_id          bigint NOT NULL REFERENCES customers(customer_id),
    order_date           timestamptz NOT NULL,
    requested_pickup_at  timestamptz NOT NULL,
    promised_delivery_at timestamptz NOT NULL,
    origin_location_id   bigint NOT NULL REFERENCES locations(location_id),
    destination_location_id bigint NOT NULL REFERENCES locations(location_id),
    weight_kg            numeric(10,2) NOT NULL,   -- [TRAP D7] 340 baris bernilai 0
    volume_m3            numeric(8,2),
    declared_value_idr   bigint,
    priority             order_priority NOT NULL,
    status               order_status NOT NULL
);
CREATE INDEX idx_orders_date     ON orders (order_date);
CREATE INDEX idx_orders_customer ON orders (customer_id);
CREATE INDEX idx_orders_status   ON orders (status);
CREATE INDEX idx_orders_dest     ON orders (destination_location_id);
COMMENT ON COLUMN orders.weight_kg IS 'Berat kiriman. Sebagian kecil baris bernilai 0 karena input error.';

-- ---------------------------------------------------------------------
-- deliveries
-- ---------------------------------------------------------------------
-- [TRAP D3] order_id sengaja TIDAK unique: satu order bisa punya 2 attempt.
-- [TRAP D1] tidak ada CHECK (delivered_at > dispatched_at).
CREATE TABLE deliveries (
    delivery_id         bigserial PRIMARY KEY,
    order_id            bigint NOT NULL REFERENCES orders(order_id),
    attempt_no          smallint NOT NULL DEFAULT 1,
    vehicle_id          bigint NOT NULL REFERENCES vehicles(vehicle_id),
    driver_id           bigint NOT NULL REFERENCES drivers(driver_id),
    dispatched_at       timestamptz NOT NULL,
    arrived_at          timestamptz,
    delivered_at        timestamptz,
    planned_distance_km numeric(8,2) NOT NULL,
    actual_distance_km  numeric(8,2),
    status              delivery_status NOT NULL,
    failure_reason      failure_reason,
    pod_signed          boolean NOT NULL DEFAULT false,
    delivery_cost_idr   bigint NOT NULL,
    fuel_cost_idr       bigint NOT NULL,
    toll_cost_idr       bigint NOT NULL,
    allowance_idr       bigint NOT NULL,
    overtime_cost_idr   bigint NOT NULL,
    route_geom          geography(LineString,4326)
);
CREATE INDEX idx_deliveries_order    ON deliveries (order_id);
CREATE INDEX idx_deliveries_vehicle  ON deliveries (vehicle_id);
CREATE INDEX idx_deliveries_driver   ON deliveries (driver_id);
CREATE INDEX idx_deliveries_disp     ON deliveries (dispatched_at);
CREATE INDEX idx_deliveries_status   ON deliveries (status);
CREATE INDEX idx_deliveries_geom     ON deliveries USING GIST (route_geom);

COMMENT ON TABLE  deliveries IS 'Satu order dapat memiliki lebih dari satu delivery bila percobaan pertama gagal.';
COMMENT ON COLUMN deliveries.delivery_cost_idr IS 'Total = fuel + toll + allowance + overtime.';

-- ---------------------------------------------------------------------
-- fuel_transactions
-- ---------------------------------------------------------------------
CREATE TABLE fuel_transactions (
    fuel_id             bigserial PRIMARY KEY,
    vehicle_id          bigint NOT NULL REFERENCES vehicles(vehicle_id),
    driver_id           bigint REFERENCES drivers(driver_id),
    station_location_id bigint NOT NULL REFERENCES locations(location_id),
    transacted_at       timestamptz NOT NULL,
    liters              numeric(7,2) NOT NULL,
    price_per_liter_idr integer NOT NULL,
    total_cost_idr      bigint NOT NULL,
    odometer_km         integer NOT NULL,   -- [TRAP] tidak dijamin monoton (A07)
    payment_method      payment_method NOT NULL
);
CREATE INDEX idx_fuel_vehicle_time ON fuel_transactions (vehicle_id, transacted_at);
CREATE INDEX idx_fuel_time         ON fuel_transactions (transacted_at);
CREATE INDEX idx_fuel_station      ON fuel_transactions (station_location_id);

-- ---------------------------------------------------------------------
-- maintenance
-- ---------------------------------------------------------------------
-- [TRAP D5] performed_date NULL = pekerjaan belum dilakukan (backlog), bukan biaya nol.
CREATE TABLE maintenance (
    maintenance_id       bigserial PRIMARY KEY,
    vehicle_id           bigint NOT NULL REFERENCES vehicles(vehicle_id),
    mtc_type             maintenance_type NOT NULL,
    scheduled_date       date NOT NULL,
    performed_date       date,
    odometer_km          integer,
    workshop_location_id bigint REFERENCES locations(location_id),
    cost_idr             bigint,
    downtime_hours       numeric(6,1),
    notes                text
);
CREATE INDEX idx_mtc_vehicle   ON maintenance (vehicle_id, scheduled_date);
CREATE INDEX idx_mtc_performed ON maintenance (performed_date);
CREATE INDEX idx_mtc_workshop  ON maintenance (workshop_location_id);
COMMENT ON COLUMN maintenance.performed_date IS 'NULL berarti pekerjaan belum dikerjakan (backlog).';

-- ---------------------------------------------------------------------
-- vehicle_events
-- ---------------------------------------------------------------------
CREATE TABLE vehicle_events (
    event_id    bigserial PRIMARY KEY,
    vehicle_id  bigint NOT NULL REFERENCES vehicles(vehicle_id),
    driver_id   bigint REFERENCES drivers(driver_id),   -- [TRAP D8] NULL untuk event non-driving
    delivery_id bigint REFERENCES deliveries(delivery_id),
    ev_type     event_type NOT NULL,
    occurred_at timestamptz NOT NULL,
    severity    smallint NOT NULL CHECK (severity BETWEEN 1 AND 5),
    geom        geography(Point,4326),
    metadata    jsonb
);
CREATE INDEX idx_events_vehicle_time ON vehicle_events (vehicle_id, occurred_at);
CREATE INDEX idx_events_type         ON vehicle_events (ev_type);
CREATE INDEX idx_events_geom         ON vehicle_events USING GIST (geom);
CREATE INDEX idx_events_delivery     ON vehicle_events (delivery_id);

-- =====================================================================
-- Role read-only untuk agent.
-- Guardrail utama ada di sini, BUKAN di prompt LLM.
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nusafleet_ro') THEN
        CREATE ROLE nusafleet_ro LOGIN PASSWORD 'change_me';
    END IF;
END$$;

GRANT USAGE ON SCHEMA fleet, public TO nusafleet_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA fleet TO nusafleet_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA fleet GRANT SELECT ON TABLES TO nusafleet_ro;
REVOKE CREATE ON SCHEMA fleet, public FROM nusafleet_ro;

ALTER ROLE nusafleet_ro SET default_transaction_read_only = on;
ALTER ROLE nusafleet_ro SET statement_timeout = '30s';
ALTER ROLE nusafleet_ro SET search_path = fleet, public;

-- =====================================================================
-- View bantu untuk agent. Sengaja minimal: kalau semua sudah disediakan
-- sebagai view, kemampuan SQL agent tidak pernah benar-benar teruji.
-- =====================================================================
CREATE OR REPLACE VIEW v_delivery_enriched AS
SELECT
    d.delivery_id,
    d.order_id,
    d.attempt_no,
    d.status                       AS delivery_status,
    o.status                       AS order_status,
    o.priority,
    o.weight_kg,
    o.promised_delivery_at,
    c.customer_id,
    c.segment,
    c.tier,
    r_dest.region_code             AS dest_region_code,
    l_org.location_code            AS origin_code,
    l_dest.location_code           AS dest_code,
    v.vehicle_id,
    vm.model_code,
    vm.v_class,
    dr.driver_id,
    dr.license_type,
    d.dispatched_at,
    d.delivered_at,
    d.planned_distance_km,
    d.actual_distance_km,
    d.delivery_cost_idr
FROM deliveries d
JOIN orders     o      ON o.order_id  = d.order_id
JOIN customers  c      ON c.customer_id = o.customer_id
JOIN locations  l_org  ON l_org.location_id  = o.origin_location_id
JOIN locations  l_dest ON l_dest.location_id = o.destination_location_id
JOIN regions    r_dest ON r_dest.region_id   = l_dest.region_id
JOIN vehicles   v      ON v.vehicle_id  = d.vehicle_id
JOIN vehicle_models vm ON vm.model_id   = v.model_id
JOIN drivers    dr     ON dr.driver_id  = d.driver_id;

COMMENT ON VIEW v_delivery_enriched IS
'Join dasar delivery-order-customer-vehicle-driver. Tidak memfilter baris cacat: kalkulasi transit time tetap harus menambahkan syarat delivered_at > dispatched_at.';
