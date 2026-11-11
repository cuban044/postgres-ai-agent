"""Evaluación reproducible contra PostgreSQL real (modo mock, sin red)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))

from app.agent import Agent  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.repository import Repository  # noqa: E402
from scripts.migrate import aplicar_migraciones  # noqa: E402
from scripts.seed import aplicar_seed  # noqa: E402

TABLAS = "order_items, orders, products, catalog_imports, agent_runs, customers, categories"


def _dsn() -> str:
    for candidato in (
        os.getenv("TEST_DATABASE_URL"),
        "postgresql://agente_app@127.0.0.1:55432/agente_test",
        "postgresql://agente_app@127.0.0.1:5432/agente_test",
    ):
        if not candidato:
            continue
        try:
            conexion = psycopg2.connect(candidato, connect_timeout=2)
            conexion.close()
            return candidato
        except psycopg2.Error:
            continue
    raise RuntimeError("No hay PostgreSQL disponible para evaluar.")


def _reset(dsn: str) -> None:
    conexion = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(f"TRUNCATE {TABLAS} RESTART IDENTITY CASCADE")
        conexion.commit()
    finally:
        conexion.close()
    aplicar_seed(dsn)


def cargar_casos() -> list[dict]:
    casos = []
    for numero, linea in enumerate((BASE / "casos.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if linea.strip():
            try:
                casos.append(json.loads(linea))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido en la línea {numero}: {exc}") from exc
    return casos


def ejecutar_todos(dsn: str | None = None) -> dict:
    dsn = dsn or _dsn()
    aplicar_migraciones(dsn)
    settings = Settings(database_url=dsn, llm_model="mock", pool_min=1, pool_max=4)
    db = Database(dsn, 1, 4)
    repo = Repository(db)
    resultados = []
    try:
        for caso in cargar_casos():
            _reset(dsn)
            respuesta = Agent(settings, repo).ejecutar(
                caso["tarea"], caso.get("datos", {})
            )
            espera = caso.get("espera", {})
            chequeos: list[dict] = []

            if "herramienta" in espera:
                chequeos.append({
                    "nombre": f"herramienta={espera['herramienta']}",
                    "ok": any(p.herramienta == espera["herramienta"] for p in respuesta.traza),
                })
            if "herramienta_ok" in espera:
                pasos = [p for p in respuesta.traza if p.herramienta == espera.get("herramienta")]
                chequeos.append({
                    "nombre": f"herramienta_ok={espera['herramienta_ok']}",
                    "ok": bool(pasos) and all(p.ok is espera["herramienta_ok"] for p in pasos),
                })
            for texto in espera.get("respuesta_contiene", []):
                chequeos.append({
                    "nombre": f"respuesta contiene '{texto}'",
                    "ok": texto.lower() in respuesta.respuesta.lower(),
                })
            if "pedidos" in espera:
                chequeos.append({
                    "nombre": f"pedidos={espera['pedidos']}",
                    "ok": repo.estadisticas()["pedidos"] == espera["pedidos"],
                })
            for sku, stock in espera.get("stock", {}).items():
                producto = repo.obtener_producto(sku)
                chequeos.append({
                    "nombre": f"stock({sku})={stock}",
                    "ok": bool(producto) and producto["stock"] == stock,
                })
            if "producto_existe" in espera:
                chequeos.append({
                    "nombre": f"producto_existe({espera['producto_existe']})",
                    "ok": repo.obtener_producto(espera["producto_existe"]) is not None,
                })
            for sku, precio in espera.get("precio", {}).items():
                producto = repo.obtener_producto(sku)
                chequeos.append({
                    "nombre": f"precio({sku})={precio}",
                    "ok": bool(producto) and producto["precio_mxn"] == precio,
                })

            resultados.append({
                "id": caso["id"],
                "ok": all(c["ok"] for c in chequeos),
                "chequeos": chequeos,
                "respuesta": respuesta.respuesta,
                "traza": [p.model_dump() for p in respuesta.traza],
            })
    finally:
        db.cerrar()

    total = len(resultados)
    pasados = sum(1 for r in resultados if r["ok"])
    reporte = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modo_llm": "mock",
        "base_datos": "postgresql",
        "total": total,
        "pasados": pasados,
        "tasa": round(pasados / total, 3) if total else 0.0,
        "casos": resultados,
    }
    (BASE / "reporte.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return reporte


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluar el agente")
    parser.add_argument("--dsn", default=None)
    args = parser.parse_args()
    reporte = ejecutar_todos(args.dsn)
    print(f"Evaluación: {reporte['pasados']}/{reporte['total']} ({reporte['tasa'] * 100:.1f}%)")
    for caso in reporte["casos"]:
        print(f"  [{'OK' if caso['ok'] else 'FALLO'}] {caso['id']}")
        for chequeo in caso["chequeos"]:
            if not chequeo["ok"]:
                print(f"      falló: {chequeo['nombre']}")
    return 0 if reporte["pasados"] == reporte["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
