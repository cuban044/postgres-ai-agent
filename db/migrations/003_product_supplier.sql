-- 003_product_supplier: procedencia del producto para importaciones de catálogo.

ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier TEXT;
