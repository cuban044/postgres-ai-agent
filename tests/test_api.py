def _pedido() -> dict:
    return {
        "cliente_email": "laura@example.com",
        "items": [
            {"sku": "BEV-001", "cantidad": 2},
            {"sku": "ALI-001", "cantidad": 1},
        ],
    }


def test_health(client):
    respuesta = client.get("/health")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["status"] == "ok"
    assert datos["db_ok"] is True
    assert datos["modo_llm"] == "mock"
    assert "consultar_catalogo" in datos["herramientas"]


def test_productos_y_filtro(client):
    todos = client.get("/products").json()
    assert todos["total"] == 10

    bebidas = client.get("/products", params={"categoria": "bebidas"}).json()
    assert bebidas["total"] == 3
    assert all(p["categoria"] == "bebidas" for p in bebidas["productos"])


def test_producto_inexistente(client):
    assert client.get("/products/NOEXISTE").status_code == 404


def test_clientes(client):
    datos = client.get("/customers").json()
    assert datos["total"] == 3
    assert datos["clientes"][0]["email"] == "laura@example.com"


def test_crear_y_consultar_pedido(client):
    respuesta = client.post("/orders", json=_pedido())
    assert respuesta.status_code == 201
    pedido = respuesta.json()
    assert pedido["total_mxn"] == 523.0
    assert pedido["order_id"] == 1

    detalle = client.get(f"/orders/{pedido['order_id']}")
    assert detalle.status_code == 200
    assert detalle.json()["items"][0]["sku"] == "BEV-001"


def test_pedido_inexistente_404(client):
    assert client.get("/orders/999").status_code == 404


def test_validacion_de_pedido(client):
    assert client.post(
        "/orders", json={"cliente_email": "laura@example.com", "items": [{"sku": "BEV-001", "cantidad": 0}]}
    ).status_code == 422
    assert client.post(
        "/orders", json={"cliente_email": "no-es-email", "items": [{"sku": "BEV-001", "cantidad": 1}]}
    ).status_code == 422
    assert client.post(
        "/orders", json={"cliente_email": "laura@example.com", "items": []}
    ).status_code == 422


def test_stock_insuficiente_400(client):
    respuesta = client.post(
        "/orders",
        json={
            "cliente_email": "laura@example.com",
            "items": [{"sku": "BEV-001", "cantidad": 999}],
        },
    )
    assert respuesta.status_code == 400
    assert "Stock insuficiente" in respuesta.json()["detail"]
    assert "SELECT" not in respuesta.text


def test_agente_y_run_persistido(client):
    respuesta = client.post(
        "/agent/run",
        json={"tarea": "consultar_catalogo", "datos": {"categoria": "bebidas"}},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["modo_llm"] == "mock"
    assert datos["traza"]
    assert "Encontré 3 productos" in datos["respuesta"]

    run = client.get(f"/runs/{datos['run_id']}")
    assert run.status_code == 200
    assert run.json()["mode"] == "mock"


def test_webhook_catalogo(client):
    respuesta = client.post(
        "/webhooks/catalog",
        json={
            "origen": "test.csv",
            "filas": [
                {"sku": "IMP-5000", "nombre": "Agua de coco 1 L", "categoria": "Bebidas", "precio": "$45.00", "stock": 12},
                {"sku": "IMP-5001", "nombre": "Producto USD", "categoria": "Otros", "precio": "USD 10"},
            ],
        },
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["upsertados"] == 1
    assert datos["omitidos_conversion"] == 1
    assert client.get("/stats").json()["importaciones_catalogo"] == 1


def test_estadisticas(client):
    client.post("/orders", json=_pedido())
    stats = client.get("/stats").json()
    assert stats["pedidos"] == 1
    assert stats["ingresos_mxn"] == 523.0
    assert stats["pedidos_por_estado"] == {"pending": 1}
