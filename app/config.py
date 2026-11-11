"""Configuración desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _float_opcional(valor: str | None) -> float | None:
    if valor is None or not valor.strip():
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _int_opcional(valor: str | None, defecto: int) -> int:
    if valor is None or not valor.strip():
        return defecto
    try:
        return int(valor)
    except ValueError:
        return defecto


@dataclass(frozen=True)
class Settings:
    # En esta máquina de desarrollo PostgreSQL escucha en 55432.
    # En Docker o en un servidor se define DATABASE_URL explícitamente.
    database_url: str = "postgresql://agente_app@127.0.0.1:55432/agente"
    pool_min: int = 1
    pool_max: int = 5
    llm_base_url: str | None = None
    llm_model: str = "mock"
    llm_api_key: str | None = None
    max_pasos: int = 6
    webhook_secret: str | None = None
    precio_entrada_por_millon: float | None = None
    precio_salida_por_millon: float | None = None
    timeout_llm: float = 60.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://agente_app@127.0.0.1:55432/agente"
            ),
            pool_min=_int_opcional(os.getenv("DB_POOL_MIN"), 1),
            pool_max=_int_opcional(os.getenv("DB_POOL_MAX"), 5),
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_model=os.getenv("LLM_MODEL", "mock"),
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            max_pasos=_int_opcional(os.getenv("AGENT_MAX_STEPS"), 6),
            webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
            precio_entrada_por_millon=_float_opcional(os.getenv("LLM_PRICE_IN_PER_MTOK")),
            precio_salida_por_millon=_float_opcional(os.getenv("LLM_PRICE_OUT_PER_MTOK")),
            timeout_llm=float(os.getenv("LLM_TIMEOUT", "60")),
        )

    @property
    def modo_llm(self) -> str:
        return "real" if (self.llm_base_url and self.llm_api_key and self.llm_model != "mock") else "mock"

    def dsn_seguro(self) -> str:
        """DSN sin credenciales, apto para logs/health."""
        if "://" not in self.database_url:
            return "postgresql"
        resto = self.database_url.split("://", 1)[1]
        host = resto.split("@", 1)[1] if "@" in resto else resto
        return f"postgresql://{host}"
