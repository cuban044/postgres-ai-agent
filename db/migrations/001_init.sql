-- 001_init: núcleo del dominio.
-- Ejecutado por scripts/migrate.py dentro de una transacción.

CREATE TABLE IF NOT EXISTS categories (
    category_id SERIAL PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    product_id      BIGSERIAL PRIMARY KEY,
    sku             TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id),
    price_mxn       NUMERIC(12, 2) NOT NULL CHECK (price_mxn >= 0),
    currency        CHAR(3) NOT NULL DEFAULT 'MXN' CHECK (currency IN ('MXN', 'USD')),
    stock           INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        BIGSERIAL PRIMARY KEY,
    customer_id     BIGINT NOT NULL REFERENCES customers(customer_id),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    total_mxn       NUMERIC(12, 2) NOT NULL CHECK (total_mxn >= 0),
    idempotency_key TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id      BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id    BIGINT NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    subtotal      NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id          TEXT PRIMARY KEY,
    task            TEXT NOT NULL,
    model           TEXT NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('mock', 'real')),
    steps           JSONB NOT NULL DEFAULT '[]'::jsonb,
    answer          TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    estimated_cost  NUMERIC(12, 6),
    duration_ms     NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
