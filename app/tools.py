"""Herramientas del agente. Toda escritura pasa por el repositorio."""

from __future__ import annotations

from typing import Any

from app.normalization import normalizar_filas, normalizar_texto
from app.repository import Repository

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_catalogo",
            "description": "Consulta productos por categoría con su precio y stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "description": "Slug de categoría, ej. bebidas"},
                    "limite": {"type": "integer", "description": "Máximo de productos (1-100)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_pedido",
            "description": "Crea un pedido en PostgreSQL, valida stock y descuenta inventario en una transacción.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_email": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "cantidad": {"type": "integer"},
                            },
                            "required": ["sku", "cantidad"],
                        },
                    },
                    "idempotency_key": {"type": "string"},
                },
                "required": ["cliente_email", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_pedido",
            "description": "Consulta un pedido por su identificador.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "integer"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumen_ventas",
            "description": "Resume pedidos e ingresos en un rango de fechas y los productos más vendidos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "desde": {"type": "string", "description": "YYYY-MM-DD"},
                    "hasta": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["desde", "hasta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "normalizar_catalogo",
            "description": "Normaliza filas de catálogo y las importa a PostgreSQL con upsert por SKU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filas": {"type": "array", "items": {"type": "object"}},
                    "origen": {"type": "string"},
                },
                "required": ["filas"],
            },
        },
    },
]

NOMBRES_HERRAMIENTAS = [schema["function"]["name"] for schema in TOOL_SCHEMAS]


def ejecutar_herramienta(
    nombre: str, argumentos: dict[str, Any], repo: Repository
) -> dict[str, Any]:
    if nombre == "consultar_catalogo":
        categoria = argumentos.get("categoria")
        if categoria is not None:
            categoria = normalizar_texto(categoria)
        try:
            limite = int(argumentos.get("limite", 20))
        except (TypeError, ValueError) as exc:
            raise ValueError("'limite' debe ser un entero") from exc
        productos = repo.listar_productos(categoria=categoria, limite=limite)
        return {"categoria": categoria, "total": len(productos), "productos": productos}

    if nombre == "crear_pedido":
        email = str(argumentos.get("cliente_email", "")).strip()
        if not email:
            raise ValueError("Falta 'cliente_email'")
        items = argumentos.get("items")
        if not isinstance(items, list):
            raise ValueError("'items' debe ser una lista")
        return repo.crear_pedido(
            cliente_email=email,
            items=items,
            idempotency_key=argumentos.get("idempotency_key") or None,
        )

    if nombre == "consultar_pedido":
        try:
            order_id = int(argumentos.get("order_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("'order_id' debe ser un entero") from exc
        pedido = repo.obtener_pedido(order_id)
        if pedido is None:
            raise ValueError(f"No existe el pedido {order_id}")
        return pedido

    if nombre == "resumen_ventas":
        desde = str(argumentos.get("desde", ""))
        hasta = str(argumentos.get("hasta", ""))
        if not desde or not hasta:
            raise ValueError("Se requieren 'desde' y 'hasta'")
        return repo.resumen_ventas(desde, hasta)

    if nombre == "normalizar_catalogo":
        filas = argumentos.get("filas")
        if not isinstance(filas, list) or not filas:
            raise ValueError("'filas' debe ser una lista con al menos una fila")
        normalizado = normalizar_filas(filas)
        return repo.importar_catalogo(
            normalizado, origen=str(argumentos.get("origen") or "api")
        )

    raise ValueError(f"Herramienta desconocida: {nombre}")
