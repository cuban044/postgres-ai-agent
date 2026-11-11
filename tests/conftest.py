"""Fixtures de pruebas contra PostgreSQL real.

La base de pruebas se elige por TEST_DATABASE_URL. Si no está definida, se prueban
los puertos locales 55432 (desarrollo en esta máquina) y 5432 (Docker).
"""

from __future__ import annotations

import os

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.factory import create_app
from app.repository import Repository
from scripts.migrate import aplicar_migraciones
from scripts.seed import aplicar_seed

CANDIDATOS = [
    os.getenv("TEST_DATABASE_URL"),
    "postgresql://agente_app@127.0.0.1:55432/agente_test",
    "postgresql://agente_app@127.0.0.1:5432/agente_test",
]

TABLAS = (
    "order_items, orders, products, catalog_imports, agent_runs, customers, categories"
)


def _elegir_dsn() -> str:
    for dsn in CANDIDATOS:
        if not dsn:
            continue
        try:
            conexion = psycopg2.connect(dsn, connect_timeout=2)
            conexion.close()
            return dsn
        except psycopg2.Error:
            continue
    pytest.fail(
        "No hay PostgreSQL disponible para las pruebas. Define TEST_DATABASE_URL "
        "o levanta la base (ver README).",
        pytrace=False,
    )


def truncar(dsn: str) -> None:
    conexion = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(f"TRUNCATE {TABLAS} RESTART IDENTITY CASCADE")
        conexion.commit()
    finally:
        conexion.close()


@pytest.fixture(scope="session")
def dsn() -> str:
    elegido = _elegir_dsn()
    aplicar_migraciones(elegido)
    return elegido


@pytest.fixture
def db(dsn: str):
    truncar(dsn)
    aplicar_seed(dsn)
    database = Database(dsn, minconn=1, maxconn=4)
    yield database
    database.cerrar()


@pytest.fixture
def repo(db: Database) -> Repository:
    return Repository(db)


@pytest.fixture
def settings(dsn: str) -> Settings:
    return Settings(database_url=dsn, llm_model="mock", pool_min=1, pool_max=4)


@pytest.fixture
def app(settings: Settings, db: Database, repo: Repository):
    return create_app(settings=settings, db=db, repo=repo)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)
