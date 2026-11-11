from datetime import date

import pytest

from app.normalization import normalizar_filas


def test_listar_productos_por_categoria(repo):
    productos = repo.listar_productos(categoria="bebidas")
    assert len(productos) == 3
    assert all(p["categoria"] == "bebidas" for p in productos)
    assert productos[0]["precio_mxn"] is not None


def test_crear_pedido_descuenta_stock(repo):
    pedido = repo.crear_pedido(
        cliente_email="laura@example.com",
        items=[
            {"sku": "BEV-001", "cantidad": 2},
            {"sku": "ALI-001", "cantidad": 1},
        ],
    )
    assert pedido["order_id"] == 1
    assert pedido["total_mxn"] == 523.0
    assert pedido["estado"] == "pending"
    assert len(pedido["items"]) == 2

    cafe = repo.obtener_producto("BEV-001")
    galletas = repo.obtener_producto("ALI-001")
    assert cafe["stock"] == 18
    assert galletas["stock"] == 39

    detalle = repo.obtener_pedido(1)
    assert detalle["cliente"] == "Laura Méndez"
    assert detalle["total_mxn"] == 523.0


def test_stock_insuficiente_hace_rollback(repo):
    before = repo.obtener_producto("BEV-001")["stock"]
    with pytest.raises(ValueError, match="Stock insuficiente"):
        repo.crear_pedido(
            cliente_email="laura@example.com",
            items=[
                {"sku": "BEV-001", "cantidad": before + 1},
                {"sku": "ALI-001", "cantidad": 1},
            ],
        )
    after = repo.obtener_producto("BEV-001")["stock"]
    assert after == before
    assert repo.estadisticas()["pedidos"] == 0
    assert repo.obtener_producto("ALI-001")["stock"] == 40


def test_idempotencia_evita_doble_pedido(repo):
    primero = repo.crear_pedido(
        cliente_email="laura@example.com",
        items=[{"sku": "BEV-001", "cantidad": 2}],
        idempotency_key="clave-001",
    )
    segundo = repo.crear_pedido(
        cliente_email="laura@example.com",
        items=[{"sku": "BEV-001", "cantidad": 2}],
        idempotency_key="clave-001",
    )
    assert primero["order_id"] == segundo["order_id"]
    assert segundo["idempotente"] is True
    assert repo.estadisticas()["pedidos"] == 1
    assert repo.obtener_producto("BEV-001")["stock"] == 18


def test_cliente_inexistente(repo):
    with pytest.raises(ValueError, match="Cliente no encontrado"):
        repo.crear_pedido(
            cliente_email="nadie@example.com",
            items=[{"sku": "BEV-001", "cantidad": 1}],
        )
    assert repo.estadisticas()["pedidos"] == 0


def test_pedido_inexistente(repo):
    assert repo.obtener_pedido(999) is None


def test_resumen_ventas(repo):
    repo.crear_pedido(
        cliente_email="laura@example.com",
        items=[
            {"sku": "BEV-001", "cantidad": 2},
            {"sku": "ALI-001", "cantidad": 1},
        ],
    )
    hoy = date.today().isoformat()
    resumen = repo.resumen_ventas(hoy, hoy)
    assert resumen["pedidos"] == 1
    assert resumen["total_mxn"] == 523.0
    assert resumen["top_productos"][0]["sku"] == "BEV-001"
    assert resumen["top_productos"][0]["unidades"] == 2

    with pytest.raises(ValueError):
        repo.resumen_ventas("2026-12-31", "2026-01-01")


def test_importar_catalogo_actualiza_y_omite(repo):
    filas = [
        {"sku": "BEV-001", "nombre": "Café molido 1 kg", "categoria": "Bebidas", "precio": "$255.00", "stock": 25, "proveedor": "Norte"},
        {"sku": "BEV-001", "nombre": "cafe MOLIDO 1 KG", "categoria": "cafe", "precio": "$245.00", "stock": 30, "proveedor": "Sur"},
        {"sku": "IMP-9001", "nombre": "Agua de coco 1 L", "categoria": "Bebidas", "precio": "$45.00", "stock": 12, "proveedor": "Nuevo"},
        {"sku": "IMP-9002", "nombre": "Alimento para perro", "categoria": "Mascotas", "precio": "USD 18.50", "stock": 8, "proveedor": "Norte"},
        {"sku": "IMP-9003", "nombre": "Producto sin precio", "categoria": "Otros", "precio": "", "stock": 5, "proveedor": "Sur"},
    ]
    normalizado = normalizar_filas(filas)
    resultado = repo.importar_catalogo(normalizado, origen="test.csv")

    assert resultado["total_entrada"] == 5
    assert resultado["total_salida"] == 4
    assert resultado["upsertados"] == 2
    assert resultado["omitidos_conversion"] == 1
    assert resultado["omitidos_sin_precio"] == 1
    assert len(resultado["duplicados"]) == 1

    cafe = repo.obtener_producto("BEV-001")
    assert cafe["precio_mxn"] == 245.0
    assert cafe["stock"] == 30
    assert cafe["proveedor"] == "Sur"
    assert repo.obtener_producto("IMP-9001") is not None
    assert repo.estadisticas()["importaciones_catalogo"] == 1


def test_sql_injection_en_categoria_es_parametrica(repo):
    productos = repo.listar_productos(categoria="bebidas'; DROP TABLE products; --")
    assert productos == []
    # La tabla sigue existiendo y con sus 10 productos.
    assert len(repo.listar_productos(limite=100)) == 10
