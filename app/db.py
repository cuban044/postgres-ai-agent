"""Pool de conexiones PostgreSQL y utilidades de conexión."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


class Database:
    def __init__(self, dsn: str, minconn: int = 1, maxconn: int = 5):
        self.dsn = dsn
        self.minconn = minconn
        self.maxconn = maxconn
        self._pool = ThreadedConnectionPool(minconn, maxconn, dsn)
        self._cerrado = False

    @contextmanager
    def conexion(self) -> Iterator[psycopg2.extensions.connection]:
        if self._cerrado:
            raise RuntimeError("El pool de conexiones está cerrado")
        conexion = self._pool.getconn()
        try:
            yield conexion
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            self._pool.putconn(conexion)

    @contextmanager
    def cursor(self) -> Iterator[RealDictCursor]:
        with self.conexion() as conexion:
            with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
                yield cursor

    def ping(self) -> bool:
        try:
            with self.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                return cursor.fetchone()["ok"] == 1
        except psycopg2.Error:
            return False

    def cerrar(self) -> None:
        if not self._cerrado:
            self._pool.closeall()
            self._cerrado = True
