"""Comprueba conectividad y muestra conteos de la base."""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificar PostgreSQL")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.dsn:
        print("ERROR: define DATABASE_URL o usa --dsn", file=sys.stderr)
        return 2
    try:
        conexion = psycopg2.connect(args.dsn, connect_timeout=5)
        with conexion.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            tablas = cursor.fetchone()[0]
        conexion.close()
    except Exception as exc:
        print(f"ERROR de conexión: {exc}", file=sys.stderr)
        return 1
    print(f"PostgreSQL: {version.split(',')[0]}")
    print(f"Tablas en public: {tablas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
