"""Adaptadores LLM: mock determinista y cliente OpenAI-compatible."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings


@dataclass
class LLMResponse:
    message: dict[str, Any]
    tokens_entrada: int = 0
    tokens_salida: int = 0


def _estimar_tokens(texto: str) -> int:
    return max(1, len(texto) // 4)


def _parsear_objetivo(contenido: str) -> tuple[str, dict[str, Any]]:
    tarea = "libre"
    coincidencia = re.search(r"TAREA:\s*([a-z_]+)", contenido)
    if coincidencia:
        tarea = coincidencia.group(1)
    datos: dict[str, Any] = {}
    coincidencia_datos = re.search(r"DATOS_JSON:\s*(\{.*\})", contenido, re.DOTALL)
    if coincidencia_datos:
        try:
            datos = json.loads(coincidencia_datos.group(1))
        except json.JSONDecodeError:
            datos = {}
    return tarea, datos


class MockLLM:
    """Guion determinista para demo y pruebas. No llama a la red."""

    def __init__(self) -> None:
        self.llamadas = 0

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.llamadas += 1
        contenido_usuario = next(
            (m.get("content", "") for m in messages if m.get("role") == "user"), ""
        )
        tarea, datos = _parsear_objetivo(contenido_usuario)
        tokens_entrada = _estimar_tokens(json.dumps(messages, ensure_ascii=False))

        if self.llamadas == 1 and tarea != "libre":
            llamada = self._llamada(tarea, datos)
            if llamada is not None:
                mensaje = {"role": "assistant", "content": None, "tool_calls": [llamada]}
                return LLMResponse(mensaje, tokens_entrada, _estimar_tokens(json.dumps(mensaje)))

        contenido = self._respuesta_final(messages, tarea)
        mensaje = {"role": "assistant", "content": contenido}
        return LLMResponse(mensaje, tokens_entrada, _estimar_tokens(contenido))

    @staticmethod
    def _llamada(tarea: str, datos: dict[str, Any]) -> dict[str, Any] | None:
        nombres = {
            "consultar_catalogo": "consultar_catalogo",
            "crear_pedido": "crear_pedido",
            "consultar_pedido": "consultar_pedido",
            "resumen_ventas": "resumen_ventas",
            "normalizar_catalogo": "normalizar_catalogo",
        }
        nombre = nombres.get(tarea)
        if nombre is None:
            return None
        return {
            "id": f"call_{tarea}_1",
            "type": "function",
            "function": {
                "name": nombre,
                "arguments": json.dumps(datos, ensure_ascii=False),
            },
        }

    @staticmethod
    def _respuesta_final(messages: list[dict], tarea: str) -> str:
        mensaje_herramienta = next(
            (m for m in reversed(messages) if m.get("role") == "tool"), None
        )
        if mensaje_herramienta is None:
            return (
                "Modo mock: no hay herramienta que ejecutar. Configura LLM_BASE_URL, "
                "LLM_MODEL y LLM_API_KEY para usar un modelo real."
            )
        try:
            resultado = json.loads(mensaje_herramienta.get("content", "{}"))
        except json.JSONDecodeError:
            return "Modo mock: la herramienta devolvió una respuesta no interpretable."
        if "error" in resultado:
            return f"La herramienta reportó un error: {resultado['error']}"

        if tarea == "consultar_catalogo":
            productos = resultado.get("productos", [])
            nombres = ", ".join(p["nombre"] for p in productos[:3])
            return (
                f"Encontré {resultado.get('total', 0)} productos"
                f"{' en ' + resultado['categoria'] if resultado.get('categoria') else ''}. "
                f"Primeros: {nombres or 'sin resultados'}."
            )
        if tarea == "crear_pedido":
            return (
                f"Pedido #{resultado.get('order_id')} creado por "
                f"${resultado.get('total_mxn'):.2f} MXN con {len(resultado.get('items', []))} línea(s). "
                f"Cliente: {resultado.get('cliente')}. "
                f"{'Operación idempotente: se devolvió el pedido existente.' if resultado.get('idempotente') else 'Stock actualizado en PostgreSQL.'}"
            )
        if tarea == "consultar_pedido":
            return (
                f"Pedido #{resultado.get('order_id')} de {resultado.get('cliente')}: "
                f"estado {resultado.get('estado')}, total ${resultado.get('total_mxn'):.2f} MXN, "
                f"{len(resultado.get('items', []))} línea(s)."
            )
        if tarea == "resumen_ventas":
            top = resultado.get("top_productos", [])
            detalle = ", ".join(f"{p['producto']} ({p['unidades']})" for p in top[:3])
            return (
                f"Entre {resultado.get('desde')} y {resultado.get('hasta')}: "
                f"{resultado.get('pedidos')} pedido(s) por ${resultado.get('total_mxn'):.2f} MXN. "
                f"Top: {detalle or 'sin ventas'}."
            )
        if tarea == "normalizar_catalogo":
            return (
                f"Importación #{resultado.get('import_id')}: "
                f"{resultado.get('total_salida')} de {resultado.get('total_entrada')} filas únicas, "
                f"{len(resultado.get('duplicados', []))} duplicado(s), "
                f"{resultado.get('upsertados')} producto(s) upsertados. "
                f"Omitidos: {resultado.get('omitidos_conversion')} por moneda y "
                f"{resultado.get('omitidos_sin_precio')} sin precio."
            )
        return "Modo mock: tarea completada."


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings):
        if not settings.llm_base_url or not settings.llm_api_key:
            raise ValueError("Faltan LLM_BASE_URL o LLM_API_KEY")
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.api_key = settings.llm_api_key
        self.timeout = settings.timeout_llm

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            with httpx.Client(timeout=self.timeout) as cliente:
                respuesta = cliente.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                respuesta.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"El proveedor LLM respondió HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Error de red al llamar al proveedor LLM: {exc}") from exc
        datos = respuesta.json()
        usage = datos.get("usage", {})
        return LLMResponse(
            message=datos["choices"][0]["message"],
            tokens_entrada=int(usage.get("prompt_tokens", 0)),
            tokens_salida=int(usage.get("completion_tokens", 0)),
        )


def crear_llm(settings: Settings) -> MockLLM | OpenAICompatibleLLM:
    if settings.modo_llm == "real":
        return OpenAICompatibleLLM(settings)
    return MockLLM()
