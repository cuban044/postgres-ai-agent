"""Normalización determinista de catálogos.

No convierte monedas: una fila en USD se marca para revisión y no se importa.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

CATEGORIAS: dict[str, list[str]] = {
    "bebidas": [
        "bebida", "cafe", "te", "refresco", "agua", "jugo", "cerveza", "vino", "soda", "energizante",
    ],
    "alimentos": [
        "alimento", "pan", "tortilla", "queso", "carne", "pollo", "verdura", "fruta", "snack",
        "galleta", "pastel", "harina", "arroz", "frijol", "leche", "huevo", "aceite", "cereal",
    ],
    "higiene": [
        "higiene", "shampoo", "pasta dental", "cepillo", "papel higienico", "desodorante",
        "crema corporal", "toalla", "jabon de bano",
    ],
    "limpieza": [
        "limpieza", "detergente", "cloro", "limpiador", "suavizante", "escoba", "trapeador",
        "jabon", "lavatrastes",
    ],
    "hogar": [
        "hogar", "foco", "pila", "vela", "utensilio", "sarten", "olla", "plato", "vaso",
        "organizador",
    ],
    "mascotas": ["mascota", "perro", "gato", "arena para gato", "alimento para perro"],
}

MONEDAS_USD = ("usd", "dolar", "dólar", "us$")


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    sin_tildes = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def limpiar_nombre(valor: Any) -> str:
    texto = re.sub(r"\s+", " ", str(valor or "").strip())
    return texto.strip(" .,-")


def parsear_precio(valor: Any) -> tuple[float | None, str | None, bool]:
    """Devuelve (precio_mxn, moneda, requiere_conversion)."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None, None, False
    if isinstance(valor, (int, float)):
        return round(float(valor), 2), "MXN", False

    texto = str(valor).strip()
    texto_norm = normalizar_texto(texto)
    moneda = "USD" if any(indicador in texto_norm for indicador in MONEDAS_USD) else "MXN"

    limpio = re.sub(r"[^\d.,-]", "", texto)
    if not limpio or limpio in ("-", ".", ","):
        return None, moneda, moneda == "USD"

    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif "," in limpio:
        partes = limpio.split(",")
        if len(partes[-1]) == 2:
            limpio = "".join(partes[:-1]) + "." + partes[-1]
        else:
            limpio = limpio.replace(",", "")
    elif "." in limpio:
        partes = limpio.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            limpio = "".join(partes)

    try:
        numero = float(limpio)
    except ValueError:
        return None, moneda, moneda == "USD"
    if numero < 0:
        return None, moneda, moneda == "USD"
    if moneda == "USD":
        return None, "USD", True
    return round(numero, 2), "MXN", False


def categoria_canonica(categoria: Any, nombre: Any = "") -> tuple[str, str]:
    categoria_norm = normalizar_texto(categoria)
    nombre_norm = normalizar_texto(nombre)

    if categoria_norm in CATEGORIAS:
        return categoria_norm, "alta"
    for canonica, palabras in CATEGORIAS.items():
        if any(palabra in categoria_norm for palabra in palabras):
            return canonica, "alta"
    for canonica, palabras in CATEGORIAS.items():
        if any(palabra in nombre_norm for palabra in palabras):
            return canonica, "media"
    return "otros", "baja"


def _entero(valor: Any) -> int:
    try:
        return max(0, int(float(str(valor).strip())))
    except (TypeError, ValueError):
        return 0


def _sku(valor: Any, nombre_normalizado: str) -> str:
    sku = re.sub(r"[^A-Za-z0-9_-]", "", str(valor or "").strip()).upper()
    if sku:
        return sku[:40]
    digest = hashlib.sha1(nombre_normalizado.encode("utf-8")).hexdigest()[:8].upper()
    return f"IMP-{digest}"


def normalizar_filas(filas: list[dict[str, Any]], maximo: int = 5000) -> dict[str, Any]:
    if not isinstance(filas, list):
        raise ValueError("'filas' debe ser una lista de objetos")
    if len(filas) > maximo:
        raise ValueError(f"Demasiadas filas: máximo {maximo}")

    items: list[dict[str, Any]] = []
    errores: list[dict[str, str]] = []

    for indice, fila in enumerate(filas):
        if not isinstance(fila, dict):
            errores.append({"indice": str(indice), "motivo": "La fila no es un objeto"})
            continue
        nombre = limpiar_nombre(fila.get("nombre"))
        if not nombre:
            errores.append({"indice": str(indice), "motivo": "Falta el nombre"})
            continue
        nombre_normalizado = normalizar_texto(nombre)
        categoria, confianza = categoria_canonica(fila.get("categoria"), nombre)
        precio_mxn, moneda, requiere_conversion = parsear_precio(fila.get("precio"))
        items.append(
            {
                "sku": _sku(fila.get("sku"), nombre_normalizado),
                "nombre": nombre,
                "nombre_normalizado": nombre_normalizado,
                "categoria": categoria,
                "confianza_categoria": confianza,
                "precio_mxn": precio_mxn,
                "moneda": moneda,
                "requiere_conversion": requiere_conversion,
                "stock": _entero(fila.get("stock")),
                "proveedor": limpiar_nombre(fila.get("proveedor")),
            }
        )

    unicos: dict[str, dict[str, Any]] = {}
    apariciones: dict[str, int] = {}
    for item in items:
        clave = item["sku"]
        apariciones[clave] = apariciones.get(clave, 0) + 1
        item["apariciones"] = apariciones[clave]
        unicos[clave] = item

    duplicados = [
        {"sku": sku, "nombre": item["nombre"], "apariciones": item["apariciones"]}
        for sku, item in unicos.items()
        if item["apariciones"] > 1
    ]
    salida = sorted(unicos.values(), key=lambda i: (i["categoria"], i["nombre_normalizado"]))
    return {
        "total_entrada": len(filas),
        "total_salida": len(salida),
        "items": salida,
        "duplicados": duplicados,
        "sin_precio_valido": [
            i["nombre"] for i in salida if i["precio_mxn"] is None and not i["requiere_conversion"]
        ],
        "requieren_conversion": [i["nombre"] for i in salida if i["requiere_conversion"]],
        "errores": errores,
        "categorias": sorted({i["categoria"] for i in salida}),
    }
