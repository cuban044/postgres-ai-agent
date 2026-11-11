"""CLI de demostración del agente y del repositorio."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.agent import Agent
from app.config import Settings
from app.db import Database
from app.repository import Repository


def _contexto() -> tuple[Settings, Database, Repository]:
    settings = Settings.from_env()
    db = Database(settings.database_url, settings.pool_min, settings.pool_max)
    return settings, db, Repository(db)


def _imprimir(resultado) -> None:
    print("=" * 70)
    print(resultado.respuesta)
    print("=" * 70)
    print(f"Modelo: {resultado.modelo} | modo: {resultado.modo_llm} | run: {resultado.run_id}")
    print(
        f"Tokens: entrada={resultado.uso.entrada} salida={resultado.uso.salida} "
        f"costo={resultado.uso.costo_estimado if resultado.uso.costo_estimado is not None else 'no configurado'}"
    )
    for paso in resultado.traza:
        print(f"  {paso.paso}. {paso.herramienta} [{'OK' if paso.ok else 'ERROR'}] {paso.duracion_ms} ms")
        print(f"     {paso.resultado_resumen}")


def cmd_productos(args: argparse.Namespace) -> int:
    _, db, repo = _contexto()
    try:
        productos = repo.listar_productos(categoria=args.categoria, limite=args.limite)
        print(f"{len(productos)} producto(s):")
        for p in productos:
            print(f"  {p['sku']:8} {p['nombre']:28} ${p['precio_mxn']:>8.2f}  stock={p['stock']}")
    finally:
        db.cerrar()
    return 0


def cmd_pedido(args: argparse.Namespace) -> int:
    ruta = Path(args.archivo)
    if not ruta.exists():
        print(f"ERROR: no existe {ruta}", file=sys.stderr)
        return 2
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    settings, db, repo = _contexto()
    try:
        _imprimir(Agent(settings, repo).ejecutar("crear_pedido", datos))
    finally:
        db.cerrar()
    return 0


def cmd_ventas(args: argparse.Namespace) -> int:
    settings, db, repo = _contexto()
    try:
        _imprimir(
            Agent(settings, repo).ejecutar(
                "resumen_ventas", {"desde": args.desde, "hasta": args.hasta}
            )
        )
    finally:
        db.cerrar()
    return 0


def cmd_catalogo(args: argparse.Namespace) -> int:
    ruta = Path(args.archivo)
    if not ruta.exists():
        print(f"ERROR: no existe {ruta}", file=sys.stderr)
        return 2
    with ruta.open(encoding="utf-8", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    settings, db, repo = _contexto()
    try:
        _imprimir(
            Agent(settings, repo).ejecutar(
                "normalizar_catalogo", {"filas": filas, "origen": ruta.name}
            )
        )
    finally:
        db.cerrar()
    return 0


def cmd_consulta(args: argparse.Namespace) -> int:
    settings, db, repo = _contexto()
    try:
        _imprimir(
            Agent(settings, repo).ejecutar(
                "consultar_pedido", {"order_id": args.order_id}
            )
        )
    finally:
        db.cerrar()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PostgreSQL AI Agent — demo")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("productos", help="Listar productos")
    p.add_argument("--categoria", default=None)
    p.add_argument("--limite", type=int, default=20)
    p.set_defaults(func=cmd_productos)

    p = sub.add_parser("pedido", help="Crear un pedido desde JSON")
    p.add_argument("archivo")
    p.set_defaults(func=cmd_pedido)

    p = sub.add_parser("ventas", help="Resumen de ventas")
    p.add_argument("--desde", required=True)
    p.add_argument("--hasta", required=True)
    p.set_defaults(func=cmd_ventas)

    p = sub.add_parser("catalogo", help="Normalizar e importar un CSV")
    p.add_argument("archivo")
    p.set_defaults(func=cmd_catalogo)

    p = sub.add_parser("consulta", help="Consultar un pedido")
    p.add_argument("--order-id", type=int, required=True)
    p.set_defaults(func=cmd_consulta)

    p = sub.add_parser("serve", help="Levantar la API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)
    return parser


def main() -> int:
    parser = construir_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
