"""Aplica migraciones SQL versionadas.

Uso:
    python scripts/migrate.py
    python scripts/migrate.py --dsn postgresql://...
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

BASE = Path(__file__).resolve().parent.parent
MIGRACIONES = BASE / "db" / "migrations"


def aplicar_migraciones(dsn: str) -> list[str]:
    aplicadas: list[str] = []
    conexion = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version    TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("SELECT version FROM schema_migrations")
            ya_aplicadas = {fila[0] for fila in cursor.fetchall()}
            for archivo in sorted(MIGRACIONES.glob("*.sql")):
                version = archivo.stem
                if version in ya_aplicadas:
                    continue
                cursor.execute(archivo.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )
                aplicadas.append(version)
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
    return aplicadas


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplicar migraciones SQL")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.dsn:
        print("ERROR: define DATABASE_URL o usa --dsn", file=sys.stderr)
        return 2
    aplicadas = aplicar_migraciones(args.dsn)
    if aplicadas:
        print("Migraciones aplicadas:", ", ".join(aplicadas))
    else:
        print("Sin migraciones pendientes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
