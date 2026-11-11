-- 002_catalog_indexes: importaciones de catálogo, índices y trigger de updated_at.

CREATE TABLE IF NOT EXISTS catalog_imports (
    import_id   BIGSERIAL PRIMARY KEY,
    origin      TEXT NOT NULL,
    total_rows  INTEGER NOT NULL CHECK (total_rows >= 0),
    unique_rows INTEGER NOT NULL CHECK (unique_rows >= 0),
    duplicates  INTEGER NOT NULL CHECK (duplicates >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_normalized_name ON products(normalized_name);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_created ON agent_runs(created_at);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_updated_at ON products;
CREATE TRIGGER trg_products_updated_at
BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
