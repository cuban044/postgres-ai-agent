"""Validación mínima de un LLM real con Function Calling.

Seguridad:
- No se ejecuta sin el flag --ejecutar.
- Exige LLM_BASE_URL, LLM_MODEL, LLM_API_KEY y precios por millón de tokens.
- Rechaza la ejecución si el peor caso estimado supera 0.25 USD.
- No imprime ni guarda la clave.
- Solo permite la herramienta de lectura consultar_catalogo.

Uso seguro (sin llamada):
    python scripts/validar_llm_real.py

Uso real (requiere credencial autorizada y presupuesto aprobado):
    export LLM_BASE_URL="https://..."
    export LLM_MODEL="modelo"
    export LLM_API_KEY="..."
    export LLM_PRICE_IN_PER_MTOK="..."
    export LLM_PRICE_OUT_PER_MTOK="..."
    export DATABASE_URL="postgresql://..."
    python scripts/validar_llm_real.py --ejecutar
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.repository import Repository  # noqa: E402
from app.tools import TOOL_SCHEMAS, ejecutar_herramienta  # noqa: E402

PRESUPUESTO_MAXIMO_USD = 0.25
MAX_TOKENS_POR_LLAMADA = 300
TOKENS_ENTRADA_PESIMISTAS = 1500
LLAMADAS_PREVISTAS = 2

PROMPT_SISTEMA = (
    "Eres un agente de operaciones. Usa la herramienta consultar_catalogo para "
    "responder con datos reales. No inventes productos ni precios. Responde en español."
)
PROMPT_USUARIO = "Consulta el catálogo de bebidas, máximo 3 productos, y resume qué encontraste."


def _precio(nombre: str) -> float | None:
    valor = os.getenv(nombre)
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _costo(tokens_in: int, tokens_out: int, precio_in: float, precio_out: float) -> float:
    return round(
        (tokens_in / 1_000_000) * precio_in + (tokens_out / 1_000_000) * precio_out,
        6,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validar LLM real con Function Calling")
    parser.add_argument("--ejecutar", action="store_true", help="Realizar la llamada real")
    args = parser.parse_args()

    base_url = (os.getenv("LLM_BASE_URL") or "").rstrip("/")
    modelo = os.getenv("LLM_MODEL") or ""
    api_key = os.getenv("LLM_API_KEY") or ""
    precio_in = _precio("LLM_PRICE_IN_PER_MTOK")
    precio_out = _precio("LLM_PRICE_OUT_PER_MTOK")

    faltantes = [
        nombre
        for nombre, valor in [
            ("LLM_BASE_URL", base_url),
            ("LLM_MODEL", modelo),
            ("LLM_API_KEY", api_key),
            ("LLM_PRICE_IN_PER_MTOK", precio_in),
            ("LLM_PRICE_OUT_PER_MTOK", precio_out),
        ]
        if not valor
    ]
    if faltantes:
        print("BLOQUEO: faltan variables para una prueba real segura:")
        print("  " + ", ".join(faltantes))
        print("No se realizó ninguna llamada y no se consumió presupuesto.")
        return 2

    peor_caso = _costo(
        TOKENS_ENTRADA_PESIMISTAS * LLAMADAS_PREVISTAS,
        MAX_TOKENS_POR_LLAMADA * LLAMADAS_PREVISTAS,
        precio_in,
        precio_out,
    )
    if peor_caso > PRESUPUESTO_MAXIMO_USD:
        print(
            f"BLOQUEO: peor caso estimado ${peor_caso:.6f} supera el tope "
            f"de ${PRESUPUESTO_MAXIMO_USD:.2f}."
        )
        return 2

    if not args.ejecutar:
        print("Configuración completa. Simulación sin llamada:")
        print(f"  proveedor: {base_url}")
        print(f"  modelo: {modelo}")
        print(f"  peor caso estimado: ${peor_caso:.6f} (tope ${PRESUPUESTO_MAXIMO_USD:.2f})")
        print("No se llamó al proveedor. Usa --ejecutar solo con autorización vigente.")
        return 0

    settings = Settings.from_env()
    db = Database(settings.database_url, 1, 2)
    repo = Repository(db)
    mensajes = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": PROMPT_USUARIO},
    ]
    tokens_in = 0
    tokens_out = 0
    inicio = time.time()
    herramienta = None
    args_herramienta = None
    resultado_herramienta = None
    respuesta_final = None

    try:
        with httpx.Client(timeout=60, trust_env=False) as cliente:
            def llamar(payload_mensajes: list[dict], max_tokens: int) -> dict:
                respuesta = cliente.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": modelo,
                        "messages": payload_mensajes,
                        "tools": TOOL_SCHEMAS,
                        "tool_choice": "auto",
                        "max_tokens": max_tokens,
                        "temperature": 0,
                    },
                )
                respuesta.raise_for_status()
                return respuesta.json()

            primera = llamar(mensajes, MAX_TOKENS_POR_LLAMADA)
            uso = primera.get("usage", {})
            tokens_in += int(uso.get("prompt_tokens", 0))
            tokens_out += int(uso.get("completion_tokens", 0))
            mensaje = primera["choices"][0]["message"]
            tool_calls = mensaje.get("tool_calls") or []
            if not tool_calls:
                print("FALLO: el modelo no llamó ninguna herramienta.")
                return 1
            llamada = tool_calls[0]
            herramienta = llamada.get("function", {}).get("name")
            if herramienta != "consultar_catalogo":
                print(f"FALLO: herramienta no permitida: {herramienta}")
                return 1
            args_herramienta = json.loads(
                llamada.get("function", {}).get("arguments", "{}")
            )
            resultado_herramienta = ejecutar_herramienta(herramienta, args_herramienta, repo)
            mensajes.append(mensaje)
            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": llamada.get("id", "call_1"),
                    "content": json.dumps(resultado_herramienta, ensure_ascii=False),
                }
            )
            segunda = llamar(mensajes, MAX_TOKENS_POR_LLAMADA)
            uso = segunda.get("usage", {})
            tokens_in += int(uso.get("prompt_tokens", 0))
            tokens_out += int(uso.get("completion_tokens", 0))
            respuesta_final = segunda["choices"][0]["message"].get("content") or ""
    except httpx.HTTPStatusError as exc:
        print(f"FALLO HTTP: {exc.response.status_code}")
        return 1
    except httpx.HTTPError as exc:
        print(f"FALLO de red: {exc}")
        return 1
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FALLO de validación: {exc}")
        return 1
    finally:
        db.cerrar()

    duracion = round(time.time() - inicio, 2)
    costo_real = _costo(tokens_in, tokens_out, precio_in, precio_out)
    reporte = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proveedor": base_url,
        "modelo": modelo,
        "herramienta": herramienta,
        "argumentos": args_herramienta,
        "tokens_entrada": tokens_in,
        "tokens_salida": tokens_out,
        "costo_estimado_usd": costo_real,
        "presupuesto_maximo_usd": PRESUPUESTO_MAXIMO_USD,
        "dentro_de_presupuesto": costo_real <= PRESUPUESTO_MAXIMO_USD,
        "duracion_s": duracion,
        "respuesta_final": respuesta_final,
    }
    destino = Path(__file__).resolve().parent.parent / "evals" / "llm_real_reporte.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {herramienta} ejecutada; respuesta recibida.")
    print(f"Tokens: entrada={tokens_in} salida={tokens_out}")
    print(f"Costo estimado: ${costo_real:.6f} (tope ${PRESUPUESTO_MAXIMO_USD:.2f})")
    print(f"Duración: {duracion}s | reporte: {destino}")
    return 0 if reporte["dentro_de_presupuesto"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
