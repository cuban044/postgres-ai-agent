"""Bucle del agente: LLM -> herramientas -> PostgreSQL -> respuesta trazable."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.config import Settings
from app.llm import crear_llm
from app.repository import Repository
from app.schemas import AgentResponse, PasoTraza, UsoTokens
from app.tools import TOOL_SCHEMAS, ejecutar_herramienta

PROMPT_SISTEMA = """Eres un agente de operaciones para una distribuidora.

Reglas:
- Usa las herramientas para consultar o modificar PostgreSQL; no inventes datos.
- Nunca inventes precios, stock, pedidos ni ventas.
- Si falta un dato, pide lo necesario en lugar de suponerlo.
- Mantén las respuestas breves y accionables, en español.
- No ejecutes acciones fuera de las herramientas disponibles.
"""


def _costo(entrada: int, salida: int, settings: Settings) -> float | None:
    if (
        settings.precio_entrada_por_millon is None
        or settings.precio_salida_por_millon is None
    ):
        return None
    return round(
        (entrada / 1_000_000) * settings.precio_entrada_por_millon
        + (salida / 1_000_000) * settings.precio_salida_por_millon,
        6,
    )


def _resumen(valor: Any, limite: int = 500) -> str:
    texto = json.dumps(valor, ensure_ascii=False, default=str)
    return texto if len(texto) <= limite else texto[:limite] + "..."


class Agent:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def ejecutar(
        self, tarea: str, datos: dict[str, Any], max_pasos: int | None = None
    ) -> AgentResponse:
        inicio = time.time()
        run_id = uuid.uuid4().hex[:12]
        llm = crear_llm(self.settings)
        maximo = max_pasos or self.settings.max_pasos
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PROMPT_SISTEMA},
            {
                "role": "user",
                "content": f"TAREA: {tarea}\nDATOS_JSON: {json.dumps(datos, ensure_ascii=False)}",
            },
        ]
        traza: list[PasoTraza] = []
        tokens_entrada = 0
        tokens_salida = 0
        respuesta_final = "No se pudo completar la tarea dentro del límite de pasos."

        for numero in range(1, maximo + 1):
            respuesta = llm.complete(messages, TOOL_SCHEMAS)
            tokens_entrada += respuesta.tokens_entrada
            tokens_salida += respuesta.tokens_salida
            mensaje = respuesta.message
            tool_calls = mensaje.get("tool_calls") or []
            if not tool_calls:
                respuesta_final = mensaje.get("content") or ""
                break

            messages.append(mensaje)
            for llamada in tool_calls:
                nombre = llamada.get("function", {}).get("name", "")
                argumentos_raw = llamada.get("function", {}).get("arguments", "{}")
                try:
                    argumentos = (
                        json.loads(argumentos_raw)
                        if isinstance(argumentos_raw, str)
                        else argumentos_raw
                    )
                    if not isinstance(argumentos, dict):
                        raise ValueError("Los argumentos deben ser un objeto JSON")
                except (json.JSONDecodeError, ValueError) as exc:
                    argumentos = {}
                    resultado = {"error": f"Argumentos inválidos: {exc}"}
                    ok = False
                    duracion = 0.0
                else:
                    inicio_herramienta = time.time()
                    try:
                        resultado = ejecutar_herramienta(nombre, argumentos, self.repo)
                        ok = True
                    except (ValueError, TypeError) as exc:
                        resultado = {"error": str(exc)}
                        ok = False
                    duracion = round((time.time() - inicio_herramienta) * 1000, 2)

                traza.append(
                    PasoTraza(
                        paso=numero,
                        herramienta=nombre,
                        argumentos=argumentos,
                        ok=ok,
                        resultado_resumen=_resumen(resultado),
                        duracion_ms=duracion,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": llamada.get("id", nombre),
                        "content": json.dumps(resultado, ensure_ascii=False, default=str),
                    }
                )

        duracion_total = round((time.time() - inicio) * 1000, 2)
        costo = _costo(tokens_entrada, tokens_salida, self.settings)
        self.repo.registrar_run(
            run_id=run_id,
            tarea=tarea,
            modelo=self.settings.llm_model,
            modo=self.settings.modo_llm,
            pasos=[paso.model_dump() for paso in traza],
            respuesta=respuesta_final,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            costo_estimado=costo,
            duracion_ms=duracion_total,
        )
        return AgentResponse(
            run_id=run_id,
            respuesta=respuesta_final,
            traza=traza,
            modelo=self.settings.llm_model,
            modo_llm=self.settings.modo_llm,  # type: ignore[arg-type]
            uso=UsoTokens(
                entrada=tokens_entrada,
                salida=tokens_salida,
                costo_estimado=costo,
            ),
            duracion_ms=duracion_total,
        )
