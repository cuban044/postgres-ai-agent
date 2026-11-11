-- 004_order_item_snapshot: el pedido conserva el nombre del producto al momento de la compra.
-- Backfill para pedidos existentes antes de exigir NOT NULL.

ALTER TABLE order_items ADD COLUMN IF NOT EXISTS product_name TEXT;

UPDATE order_items oi
SET product_name = p.name
FROM products p
WHERE p.product_id = oi.product_id
  AND oi.product_name IS NULL;

ALTER TABLE order_items ALTER COLUMN product_name SET NOT NULL;
