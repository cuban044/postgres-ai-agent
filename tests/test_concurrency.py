"""Concurrencia real contra PostgreSQL: última unidad e idempotencia simultánea."""

from concurrent.futures import ThreadPoolExecutor


def test_ultima_unidad_solo_la_vende_un_pedido(db, repo):
    with db.cursor() as cursor:
        cursor.execute("UPDATE products SET stock = 1 WHERE sku = 'BEV-001'")

    def comprar():
        return repo.crear_pedido(
            cliente_email="laura@example.com",
            items=[{"sku": "BEV-001", "cantidad": 1}],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [executor.submit(comprar) for _ in range(2)]

    exitos, errores = [], []
    for futuro in futuros:
        try:
            exitos.append(futuro.result())
        except ValueError as exc:
            errores.append(str(exc))

    assert len(exitos) == 1
    assert len(errores) == 1
    assert "Stock insuficiente" in errores[0]
    assert repo.estadisticas()["pedidos"] == 1
    assert repo.obtener_producto("BEV-001")["stock"] == 0


def test_idempotencia_simultanea_no_duplica_pedido(db, repo):
    def comprar():
        return repo.crear_pedido(
            cliente_email="laura@example.com",
            items=[{"sku": "ALI-001", "cantidad": 1}],
            idempotency_key="concurrente-001",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [executor.submit(comprar) for _ in range(2)]
        resultados = [futuro.result() for futuro in futuros]

    assert len({resultado["order_id"] for resultado in resultados}) == 1
    assert repo.estadisticas()["pedidos"] == 1
    assert repo.obtener_producto("ALI-001")["stock"] == 39


def test_pedidos_con_sku_en_orden_inverso_no_hacen_deadlock(repo):
    def comprar(items):
        return repo.crear_pedido(
            cliente_email="laura@example.com",
            items=items,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [
            executor.submit(comprar, [
                {"sku": "BEV-001", "cantidad": 1},
                {"sku": "ALI-001", "cantidad": 1},
            ]),
            executor.submit(comprar, [
                {"sku": "ALI-001", "cantidad": 1},
                {"sku": "BEV-001", "cantidad": 1},
            ]),
        ]
        resultados = [futuro.result() for futuro in futuros]

    assert len(resultados) == 2
    assert repo.estadisticas()["pedidos"] == 2
    assert repo.obtener_producto("BEV-001")["stock"] == 18
    assert repo.obtener_producto("ALI-001")["stock"] == 38
