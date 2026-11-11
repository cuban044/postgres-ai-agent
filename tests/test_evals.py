from evals.run_evals import ejecutar_todos


def test_casos_dorados_pasan(dsn):
    reporte = ejecutar_todos(dsn)
    assert reporte["total"] >= 4
    assert reporte["pasados"] == reporte["total"], reporte
    assert reporte["tasa"] == 1.0
