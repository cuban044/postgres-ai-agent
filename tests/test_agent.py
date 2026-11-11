from app.agent import Agent
from app.config import Settings


def _pedido() -> dict:
    return {
        "cliente_email": "laura@example.com",
        "items": [
            {"sku": "BEV-001", "cantidad": 2},
            {"sku": "ALI-001", "cantidad": 1},
        ],
    }


def test_agente_consulta_catalogo(settings, repo):
    resultado = Agent(settings, repo).ejecutar(
        "consultar_catalogo", {"categoria": "bebidas", "limite": 5}
    )
    assert "Encontré 3 productos" in resultado.respuesta
    assert any(p.herramienta == "consultar_catalogo" and p.ok for p in resultado.traza)
    assert repo.obtener_run(resultado.run_id)["mode"] == "mock"


def test_agente_crea_pedido(settings, repo):
    resultado = Agent(settings, repo).ejecutar("crear_pedido", _pedido())
    assert "Pedido #1" in resultado.respuesta
    assert "523.00" in resultado.respuesta
    assert repo.estadisticas()["pedidos"] == 1
    assert repo.obtener_producto("BEV-001")["stock"] == 18


def test_agente_reporta_stock_insuficiente(settings, repo):
    resultado = Agent(settings, repo).ejecutar(
        "crear_pedido",
        {
            "cliente_email": "laura@example.com",
            "items": [{"sku": "BEV-001", "cantidad": 999}],
        },
    )
    assert "Stock insuficiente" in resultado.respuesta
    assert any(not p.ok for p in resultado.traza)
    assert repo.estadisticas()["pedidos"] == 0
    assert repo.obtener_producto("BEV-001")["stock"] == 20


def test_agente_resumen_ventas(settings, repo):
    agente = Agent(settings, repo)
    agente.ejecutar("crear_pedido", _pedido())
    from datetime import date

    hoy = date.today().isoformat()
    resultado = agente.ejecutar("resumen_ventas", {"desde": hoy, "hasta": hoy})
    assert "1 pedido" in resultado.respuesta
    assert "523.00" in resultado.respuesta
    assert "Café molido" in resultado.respuesta


def test_agente_normaliza_catalogo(settings, repo):
    resultado = Agent(settings, repo).ejecutar(
        "normalizar_catalogo",
        {
            "origen": "test.csv",
            "filas": [
                {"sku": "BEV-001", "nombre": "Café molido 1 kg", "categoria": "Bebidas", "precio": "$245.00", "stock": 30, "proveedor": "Sur"},
                {"sku": "IMP-7777", "nombre": "Agua de coco 1 L", "categoria": "Bebidas", "precio": "$45.00", "stock": 12, "proveedor": "Nuevo"},
            ],
        },
    )
    assert "Importación" in resultado.respuesta
    assert "upsertados" in resultado.respuesta
    assert repo.obtener_producto("BEV-001")["precio_mxn"] == 245.0
    assert repo.obtener_producto("IMP-7777") is not None


def test_agente_calcula_costo_si_hay_precios(db, repo):
    settings = Settings(
        database_url=db.dsn,
        llm_model="mock",
        precio_entrada_por_millon=1.0,
        precio_salida_por_millon=2.0,
    )
    resultado = Agent(settings, repo).ejecutar(
        "consultar_catalogo", {"categoria": "bebidas"}
    )
    assert resultado.uso.costo_estimado is not None
    assert resultado.uso.costo_estimado > 0
