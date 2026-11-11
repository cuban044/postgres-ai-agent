-- Semilla idempotente para demo y pruebas.
INSERT INTO categories (slug, name) VALUES
    ('bebidas', 'Bebidas'),
    ('alimentos', 'Alimentos'),
    ('higiene', 'Higiene'),
    ('limpieza', 'Limpieza'),
    ('hogar', 'Hogar'),
    ('mascotas', 'Mascotas'),
    ('otros', 'Otros')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO customers (name, email, phone) VALUES
    ('Laura Méndez', 'laura@example.com', '+52 33 1234 5678'),
    ('Marco Ruiz', 'marco@example.com', '+52 33 8765 4321'),
    ('Ana Torres', 'ana@example.com', '+52 33 5555 0101')
ON CONFLICT (email) DO NOTHING;

INSERT INTO products (sku, name, normalized_name, category_id, price_mxn, stock, supplier)
SELECT v.sku, v.name, v.normalized_name, c.category_id, v.price_mxn, v.stock, v.supplier
FROM (VALUES
    ('BEV-001', 'Café molido 1 kg', 'cafe molido 1 kg', 'bebidas', 249.00, 20, 'Proveedor Norte'),
    ('BEV-002', 'Agua mineral 600 ml', 'agua mineral 600 ml', 'bebidas', 12.50, 100, 'Proveedor Norte'),
    ('BEV-003', 'Jugo de naranja 1 L', 'jugo de naranja 1 l', 'bebidas', 32.00, 35, 'Proveedor Sur'),
    ('ALI-001', 'Galletas de avena', 'galletas de avena', 'alimentos', 25.00, 40, 'Proveedor Sur'),
    ('ALI-002', 'Pan integral', 'pan integral', 'alimentos', 38.00, 25, 'Proveedor Centro'),
    ('ALI-003', 'Queso panela 400 g', 'queso panela 400 g', 'alimentos', 65.00, 18, 'Proveedor Centro'),
    ('HIG-001', 'Jabón de baño 100 g', 'jabon de bano 100 g', 'higiene', 18.00, 50, 'Proveedor Centro'),
    ('LIM-001', 'Detergente 1 L', 'detergente 1 l', 'limpieza', 42.90, 30, 'Proveedor Centro'),
    ('HOG-001', 'Foco LED 9 W', 'foco led 9 w', 'hogar', 35.00, 60, 'Proveedor Centro'),
    ('MAS-001', 'Alimento para perro 3 kg', 'alimento para perro 3 kg', 'mascotas', 189.00, 15, 'Proveedor Norte')
) AS v(sku, name, normalized_name, category_slug, price_mxn, stock, supplier)
JOIN categories c ON c.slug = v.category_slug
ON CONFLICT (sku) DO NOTHING;
