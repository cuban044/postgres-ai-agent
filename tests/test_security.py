from dataclasses import replace

from fastapi.testclient import TestClient

from app.factory import create_app


def test_sql_injection_en_query_parametro_no_destruye_tablas(client):
    malicioso = "bebidas'; DROP TABLE products; --"
    respuesta = client.get("/products", params={"categoria": malicioso})
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 0
    # La tabla sigue viva y completa.
    assert client.get("/products").json()["total"] == 10


def test_sql_injection_en_agente_no_destruye_tablas(client):
    respuesta = client.post(
        "/agent/run",
        json={
            "tarea": "consultar_catalogo",
            "datos": {"categoria": "bebidas'; DROP TABLE products; --"},
        },
    )
    assert respuesta.status_code == 200
    assert client.get("/products").json()["total"] == 10


def test_webhook_exige_secreto(settings, db, repo):
    settings_seguro = replace(settings, webhook_secret="secreto-de-prueba")
    cliente = TestClient(create_app(settings=settings_seguro, db=db, repo=repo))
    payload = {
        "origen": "test.csv",
        "filas": [{"sku": "SEG-1", "nombre": "Producto seguro", "categoria": "Otros", "precio": "10"}],
    }
    assert cliente.post("/webhooks/catalog", json=payload).status_code == 401
    assert cliente.post(
        "/webhooks/catalog",
        json=payload,
        headers={"X-Webhook-Secret": "incorrecto"},
    ).status_code == 401
    assert cliente.post(
        "/webhooks/catalog",
        json=payload,
        headers={"X-Webhook-Secret": "secreto-de-prueba"},
    ).status_code == 201


def test_health_no_expone_credenciales(settings, db, repo):
    settings_con_password = replace(
        settings,
        database_url="postgresql://usuario:supersecreto@127.0.0.1:55432/agente",
    )
    cliente = TestClient(create_app(settings=settings_con_password, db=db, repo=repo))
    texto = cliente.get("/health").text
    assert "supersecreto" not in texto
    assert "usuario:" not in texto


def test_catalogo_demasiado_grande_se_rechaza(client):
    filas = [{"nombre": f"Producto {i}"} for i in range(5001)]
    respuesta = client.post(
        "/webhooks/catalog", json={"origen": "grande.csv", "filas": filas}
    )
    assert respuesta.status_code == 422


def test_error_de_negocio_no_filtra_sql(client):
    respuesta = client.post(
        "/orders",
        json={
            "cliente_email": "laura@example.com",
            "items": [{"sku": "BEV-001", "cantidad": 999}],
        },
    )
    assert respuesta.status_code == 400
    texto = respuesta.text.lower()
    assert "stock insuficiente" in texto
    assert "psycopg" not in texto
    assert "traceback" not in texto
