"""Reinicia la base de demo: trunca tablas y aplica la semilla."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed import aplicar_seed

TABLAS = "order_items, orders, products, catalog_imports, agent_runs, customers, categories"


def reset(dsn: str) -> None:
    conexion = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(f"TRUNCATE {TABLAS} RESTART IDENTITY CASCADE")
        conexion.commit()
    finally:
        conexion.close()
    aplicar_seed(dsn)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reiniciar datos de demo")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.dsn:
        print("ERROR: define DATABASE_URL o usa --dsn", file=sys.stderr)
        return 2
    reset(args.dsn)
    print("Base de demo reiniciada (truncada + semilla).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
