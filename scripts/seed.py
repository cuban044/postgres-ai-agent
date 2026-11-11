"""Carga la semilla idempotente de demo/pruebas."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "db" / "seed.sql"


def aplicar_seed(dsn: str) -> None:
    conexion = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(SEED.read_text(encoding="utf-8"))
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Cargar datos de ejemplo")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.dsn:
        print("ERROR: define DATABASE_URL o usa --dsn", file=sys.stderr)
        return 2
    aplicar_seed(args.dsn)
    print("Semilla aplicada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
