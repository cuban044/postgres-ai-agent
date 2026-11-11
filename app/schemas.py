"""Modelos Pydantic de entrada y salida."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Tarea = Literal[
    "consultar_catalogo",
    "crear_pedido",
    "consultar_pedido",
    "resumen_ventas",
    "normalizar_catalogo",
    "libre",
]


class AgentRequest(BaseModel):
    tarea: Tarea = "consultar_catalogo"
    datos: dict[str, Any] = Field(default_factory=dict)
    max_pasos: int | None = Field(default=None, ge=1, le=12)


class PasoTraza(BaseModel):
    paso: int
    herramienta: str
    argumentos: dict[str, Any]
    ok: bool
    resultado_resumen: str
    duracion_ms: float


class UsoTokens(BaseModel):
    entrada: int = 0
    salida: int = 0
    costo_estimado: float | None = None
    moneda: str = "USD"


class AgentResponse(BaseModel):
    run_id: str
    respuesta: str
    traza: list[PasoTraza]
    modelo: str
    modo_llm: Literal["mock", "real"]
    uso: UsoTokens
    duracion_ms: float


class ItemPedido(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    cantidad: int = Field(ge=1, le=1000)


class PedidoCreate(BaseModel):
    cliente_email: str = Field(
        min_length=3,
        max_length=200,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    items: list[ItemPedido] = Field(min_length=1, max_length=50)
    idempotency_key: str | None = Field(default=None, max_length=100)


class CatalogWebhook(BaseModel):
    origen: str = Field(min_length=1, max_length=120)
    filas: list[dict[str, Any]] = Field(min_length=1, max_length=5000)


class Salud(BaseModel):
    status: str
    db: str
    db_ok: bool
    modo_llm: str
    modelo: str
    herramientas: list[str]
    webhook_protegido: bool


class Estadisticas(BaseModel):
    productos: int
    clientes: int
    pedidos: int
    ingresos_mxn: float
    pedidos_por_estado: dict[str, int]
    importaciones_catalogo: int
