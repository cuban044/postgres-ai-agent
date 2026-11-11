"""Repositorio de dominio sobre PostgreSQL.

Todas las consultas usan parámetros. Las escrituras críticas corren en una
transacción y bloquean las filas necesarias con SELECT ... FOR UPDATE.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from app.db import Database


def _float(valor: Any) -> float | None:
    if valor is None:
        return None
    return float(valor)


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    def listar_productos(
        self, categoria: str | None = None, limite: int = 20
    ) -> list[dict[str, Any]]:
        limite = max(1, min(int(limite), 100))
        consulta = """
            SELECT p.sku, p.name AS nombre, p.normalized_name AS nombre_normalizado,
                   c.slug AS categoria, p.price_mxn, p.stock, p.supplier
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
        """
        with self.db.cursor() as cursor:
            if categoria:
                cursor.execute(
                    consulta + " WHERE c.slug = %s ORDER BY p.name LIMIT %s",
                    (categoria, limite),
                )
            else:
                cursor.execute(consulta + " ORDER BY p.name LIMIT %s", (limite,))
            filas = cursor.fetchall()
        return [self._producto(fila) for fila in filas]

    def obtener_producto(self, sku: str) -> dict[str, Any] | None:
        with self.db.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.sku, p.name AS nombre, p.normalized_name AS nombre_normalizado,
                       c.slug AS categoria, p.price_mxn, p.stock, p.supplier
                FROM products p
                JOIN categories c ON c.category_id = p.category_id
                WHERE p.sku = %s
                """,
                (sku,),
            )
            fila = cursor.fetchone()
        return self._producto(fila) if fila else None

    def listar_clientes(self) -> list[dict[str, Any]]:
        with self.db.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id, name AS nombre, email, phone AS telefono FROM customers ORDER BY customer_id"
            )
            return [dict(fila) for fila in cursor.fetchall()]

    def _producto(self, fila: dict[str, Any]) -> dict[str, Any]:
        return {
            "sku": fila["sku"],
            "nombre": fila["nombre"],
            "nombre_normalizado": fila["nombre_normalizado"],
            "categoria": fila["categoria"],
            "precio_mxn": _float(fila["price_mxn"]),
            "stock": fila["stock"],
            "proveedor": fila.get("supplier"),
        }

    # ------------------------------------------------------------------
    # Pedidos
    # ------------------------------------------------------------------
    def obtener_pedido(self, order_id: int) -> dict[str, Any] | None:
        with self.db.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.order_id, o.status AS estado, o.total_mxn, o.idempotency_key,
                       o.created_at, c.name AS cliente, c.email
                FROM orders o
                JOIN customers c ON c.customer_id = o.customer_id
                WHERE o.order_id = %s
                """,
                (order_id,),
            )
            pedido = cursor.fetchone()
            if pedido is None:
                return None
            cursor.execute(
                """
                SELECT p.sku, oi.product_name AS producto, oi.quantity AS cantidad,
                       oi.unit_price AS precio_unitario, oi.subtotal
                FROM order_items oi
                JOIN products p ON p.product_id = oi.product_id
                WHERE oi.order_id = %s
                ORDER BY oi.order_item_id
                """,
                (order_id,),
            )
            items = cursor.fetchall()
        return {
            "order_id": pedido["order_id"],
            "estado": pedido["estado"],
            "total_mxn": _float(pedido["total_mxn"]),
            "idempotency_key": pedido["idempotency_key"],
            "cliente": pedido["cliente"],
            "email": pedido["email"],
            "creado_en": pedido["created_at"].isoformat(),
            "items": [
                {
                    "sku": item["sku"],
                    "producto": item["producto"],
                    "cantidad": item["cantidad"],
                    "precio_unitario": _float(item["precio_unitario"]),
                    "subtotal": _float(item["subtotal"]),
                }
                for item in items
            ],
        }

    def _pedido_por_idempotencia(self, clave: str) -> dict[str, Any] | None:
        with self.db.cursor() as cursor:
            cursor.execute(
                "SELECT order_id FROM orders WHERE idempotency_key = %s", (clave,)
            )
            fila = cursor.fetchone()
        return self.obtener_pedido(fila["order_id"]) if fila else None

    def crear_pedido(
        self,
        cliente_email: str,
        items: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(items, list) or not items:
            raise ValueError("El pedido debe incluir al menos un ítem")
        if len(items) > 50:
            raise ValueError("Máximo 50 líneas por pedido")
        if idempotency_key:
            existente = self._pedido_por_idempotencia(idempotency_key)
            if existente:
                return {**existente, "idempotente": True}

        try:
            with self.db.conexion() as conexion:
                with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT customer_id, name, email FROM customers WHERE email = %s",
                        (cliente_email,),
                    )
                    cliente = cursor.fetchone()
                    if cliente is None:
                        raise ValueError("Cliente no encontrado")

                    items_normalizados: list[dict[str, Any]] = []
                    for indice, item in enumerate(items):
                        sku = str(item.get("sku", "")).strip().upper()
                        try:
                            cantidad = int(item.get("cantidad", 0))
                        except (TypeError, ValueError) as exc:
                            raise ValueError(f"Cantidad inválida para SKU {sku or '?'}") from exc
                        if not sku or cantidad <= 0:
                            raise ValueError("Cada ítem requiere sku y cantidad positiva")
                        if cantidad > 1000:
                            raise ValueError(f"Cantidad excesiva para {sku}")
                        items_normalizados.append(
                            {"sku": sku, "cantidad": cantidad, "orden": indice}
                        )

                    # Bloquear siempre en el mismo orden evita deadlocks entre pedidos
                    # que incluyen los mismos SKU en distinto orden.
                    items_normalizados.sort(key=lambda item: item["sku"])

                    total = Decimal("0")
                    lineas: list[dict[str, Any]] = []
                    for item in items_normalizados:
                        sku = item["sku"]
                        cantidad = item["cantidad"]

                        cursor.execute(
                            """
                            SELECT product_id, sku, name, price_mxn, stock
                            FROM products WHERE sku = %s FOR UPDATE
                            """,
                            (sku,),
                        )
                        producto = cursor.fetchone()
                        if producto is None:
                            raise ValueError(f"Producto {sku} no encontrado")
                        if producto["stock"] < cantidad:
                            raise ValueError(
                                f"Stock insuficiente para {sku}: disponible "
                                f"{producto['stock']}, solicitado {cantidad}"
                            )
                        subtotal = producto["price_mxn"] * cantidad
                        cursor.execute(
                            "UPDATE products SET stock = stock - %s WHERE product_id = %s",
                            (cantidad, producto["product_id"]),
                        )
                        lineas.append(
                            {
                                "sku": sku,
                                "producto": producto["name"],
                                "cantidad": cantidad,
                                "precio_unitario": _float(producto["price_mxn"]),
                                "subtotal": float(subtotal),
                                "_orden": item["orden"],
                            }
                        )
                        total += subtotal

                    lineas.sort(key=lambda linea: linea["_orden"])
                    for linea in lineas:
                        linea.pop("_orden", None)

                    cursor.execute(
                        """
                        INSERT INTO orders (customer_id, status, total_mxn, idempotency_key)
                        VALUES (%s, 'pending', %s, %s)
                        RETURNING order_id, created_at
                        """,
                        (cliente["customer_id"], total, idempotency_key),
                    )
                    pedido = cursor.fetchone()
                    for linea in lineas:
                        cursor.execute(
                            """
                            INSERT INTO order_items
                                (order_id, product_id, product_name, quantity, unit_price, subtotal)
                            SELECT %s, product_id, name, %s, %s, %s
                            FROM products WHERE sku = %s
                            """,
                            (
                                pedido["order_id"],
                                linea["cantidad"],
                                linea["precio_unitario"],
                                linea["subtotal"],
                                linea["sku"],
                            ),
                        )
        except psycopg2.errors.UniqueViolation:
            if idempotency_key:
                existente = self._pedido_por_idempotencia(idempotency_key)
                if existente:
                    return {**existente, "idempotente": True}
            raise

        return {
            "order_id": pedido["order_id"],
            "estado": "pending",
            "total_mxn": _float(total),
            "idempotency_key": idempotency_key,
            "cliente": cliente["name"],
            "email": cliente["email"],
            "creado_en": pedido["created_at"].isoformat(),
            "items": lineas,
            "idempotente": False,
        }

    # ------------------------------------------------------------------
    # Ventas
    # ------------------------------------------------------------------
    def resumen_ventas(self, desde: str, hasta: str) -> dict[str, Any]:
        try:
            desde_f = date.fromisoformat(desde)
            hasta_f = date.fromisoformat(hasta)
        except ValueError as exc:
            raise ValueError("Fechas inválidas; usa formato YYYY-MM-DD") from exc
        if hasta_f < desde_f:
            raise ValueError("'hasta' no puede ser menor que 'desde'")

        with self.db.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS pedidos, COALESCE(SUM(total_mxn), 0) AS total_mxn
                FROM orders
                WHERE status <> 'cancelled' AND created_at::date BETWEEN %s AND %s
                """,
                (desde_f, hasta_f),
            )
            resumen = cursor.fetchone()
            cursor.execute(
                """
                SELECT p.sku, COALESCE(MAX(oi.product_name), MAX(p.name)) AS producto,
                       SUM(oi.quantity) AS unidades, SUM(oi.subtotal) AS ingresos
                FROM order_items oi
                JOIN orders o ON o.order_id = oi.order_id
                JOIN products p ON p.product_id = oi.product_id
                WHERE o.status <> 'cancelled' AND o.created_at::date BETWEEN %s AND %s
                GROUP BY p.sku
                ORDER BY unidades DESC, ingresos DESC
                LIMIT 5
                """,
                (desde_f, hasta_f),
            )
            top = cursor.fetchall()
        return {
            "desde": desde,
            "hasta": hasta,
            "pedidos": resumen["pedidos"],
            "total_mxn": _float(resumen["total_mxn"]),
            "top_productos": [
                {
                    "sku": fila["sku"],
                    "producto": fila["producto"],
                    "unidades": int(fila["unidades"]),
                    "ingresos": _float(fila["ingresos"]),
                }
                for fila in top
            ],
        }

    # ------------------------------------------------------------------
    # Catálogo: importación normalizada
    # ------------------------------------------------------------------
    def importar_catalogo(self, normalizado: dict[str, Any], origen: str) -> dict[str, Any]:
        items = normalizado.get("items", [])
        validos = [
            item for item in items
            if item.get("precio_mxn") is not None and not item.get("requiere_conversion")
        ]
        omitidos_conversion = sum(1 for item in items if item.get("requiere_conversion"))
        omitidos_sin_precio = sum(
            1 for item in items
            if item.get("precio_mxn") is None and not item.get("requiere_conversion")
        )

        with self.db.conexion() as conexion:
            with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    INSERT INTO catalog_imports (origin, total_rows, unique_rows, duplicates)
                    VALUES (%s, %s, %s, %s)
                    RETURNING import_id
                    """,
                    (
                        origen,
                        normalizado.get("total_entrada", len(items)),
                        normalizado.get("total_salida", len(items)),
                        len(normalizado.get("duplicados", [])),
                    ),
                )
                import_id = cursor.fetchone()["import_id"]

                for slug in {item["categoria"] for item in validos}:
                    cursor.execute(
                        """
                        INSERT INTO categories (slug, name) VALUES (%s, %s)
                        ON CONFLICT (slug) DO NOTHING
                        """,
                        (slug, slug.replace("_", " ").title()),
                    )
                cursor.execute("SELECT category_id, slug FROM categories")
                categorias = {fila["slug"]: fila["category_id"] for fila in cursor.fetchall()}

                upsertados = 0
                for item in validos:
                    cursor.execute(
                        """
                        INSERT INTO products
                            (sku, name, normalized_name, category_id, price_mxn, currency, stock, supplier)
                        VALUES (%s, %s, %s, %s, %s, 'MXN', %s, %s)
                        ON CONFLICT (sku) DO UPDATE SET
                            name = EXCLUDED.name,
                            normalized_name = EXCLUDED.normalized_name,
                            category_id = EXCLUDED.category_id,
                            price_mxn = EXCLUDED.price_mxn,
                            currency = EXCLUDED.currency,
                            stock = EXCLUDED.stock,
                            supplier = EXCLUDED.supplier,
                            updated_at = now()
                        """,
                        (
                            item["sku"],
                            item["nombre"],
                            item["nombre_normalizado"],
                            categorias.get(item["categoria"], categorias["otros"]),
                            item["precio_mxn"],
                            item["stock"],
                            item.get("proveedor") or None,
                        ),
                    )
                    upsertados += 1

        return {
            "import_id": import_id,
            "origen": origen,
            "total_entrada": normalizado.get("total_entrada", len(items)),
            "total_salida": normalizado.get("total_salida", len(items)),
            "upsertados": upsertados,
            "duplicados": normalizado.get("duplicados", []),
            "omitidos_conversion": omitidos_conversion,
            "omitidos_sin_precio": omitidos_sin_precio,
            "categorias": normalizado.get("categorias", []),
        }

    # ------------------------------------------------------------------
    # Ejecuciones del agente
    # ------------------------------------------------------------------
    def registrar_run(
        self,
        run_id: str,
        tarea: str,
        modelo: str,
        modo: str,
        pasos: list[dict[str, Any]],
        respuesta: str,
        tokens_entrada: int,
        tokens_salida: int,
        costo_estimado: float | None,
        duracion_ms: float,
    ) -> None:
        with self.db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs
                    (run_id, task, model, mode, steps, answer, input_tokens,
                     output_tokens, estimated_cost, duration_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    tarea,
                    modelo,
                    modo,
                    Json(pasos),
                    respuesta,
                    tokens_entrada,
                    tokens_salida,
                    costo_estimado,
                    duracion_ms,
                ),
            )

    def obtener_run(self, run_id: str) -> dict[str, Any] | None:
        with self.db.cursor() as cursor:
            cursor.execute("SELECT * FROM agent_runs WHERE run_id = %s", (run_id,))
            fila = cursor.fetchone()
        if fila is None:
            return None
        run = dict(fila)
        run["duration_ms"] = _float(run["duration_ms"])
        run["estimated_cost"] = _float(run["estimated_cost"])
        return run

    # ------------------------------------------------------------------
    # Estadísticas
    # ------------------------------------------------------------------
    def estadisticas(self) -> dict[str, Any]:
        with self.db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM products")
            productos = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) AS total FROM customers")
            clientes = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) AS total FROM orders")
            pedidos = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT COALESCE(SUM(total_mxn), 0) AS total FROM orders WHERE status <> 'cancelled'"
            )
            ingresos = _float(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT status, COUNT(*) AS total FROM orders GROUP BY status ORDER BY status"
            )
            por_estado = {fila["status"]: fila["total"] for fila in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) AS total FROM catalog_imports")
            importaciones = cursor.fetchone()["total"]
        return {
            "productos": productos,
            "clientes": clientes,
            "pedidos": pedidos,
            "ingresos_mxn": ingresos,
            "pedidos_por_estado": por_estado,
            "importaciones_catalogo": importaciones,
        }
