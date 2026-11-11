"""Fábrica de la aplicación FastAPI (inyectable en pruebas)."""

from __future__ import annotations

import hmac

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.agent import Agent
from app.config import Settings
from app.db import Database
from app.normalization import normalizar_filas
from app.repository import Repository
from app.schemas import (
    AgentRequest,
    AgentResponse,
    CatalogWebhook,
    Estadisticas,
    PedidoCreate,
    Salud,
)
from app.tools import NOMBRES_HERRAMIENTAS


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    repo: Repository | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    db = db or Database(settings.database_url, settings.pool_min, settings.pool_max)
    repo = repo or Repository(db)

    app = FastAPI(
        title="PostgreSQL AI Agent",
        version="1.0.0",
        description=(
            "Agente LLM con function calling conectado a PostgreSQL y API REST. "
            "Demostración técnica verificable; no es un sistema en producción."
        ),
    )
    app.state.settings = settings
    app.state.db = db
    app.state.repo = repo

    @app.get("/", include_in_schema=False)
    def raiz() -> dict:
        return {
            "nombre": "postgres-ai-agent",
            "modo_llm": settings.modo_llm,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", response_model=Salud)
    def health() -> Salud:
        db_ok = db.ping()
        return Salud(
            status="ok" if db_ok else "degradado",
            db=settings.dsn_seguro(),
            db_ok=db_ok,
            modo_llm=settings.modo_llm,
            modelo=settings.llm_model,
            herramientas=NOMBRES_HERRAMIENTAS,
            webhook_protegido=bool(settings.webhook_secret),
        )

    @app.get("/products")
    def productos(
        categoria: str | None = None,
        limite: int = Query(default=20, ge=1, le=100),
    ) -> dict:
        lista = repo.listar_productos(categoria=categoria, limite=limite)
        return {"total": len(lista), "productos": lista}

    @app.get("/products/{sku}")
    def producto(sku: str) -> dict:
        encontrado = repo.obtener_producto(sku.upper())
        if encontrado is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return encontrado

    @app.get("/customers")
    def clientes() -> dict:
        lista = repo.listar_clientes()
        return {"total": len(lista), "clientes": lista}

    @app.post("/orders", status_code=201)
    def crear_pedido(pedido: PedidoCreate) -> dict:
        try:
            return repo.crear_pedido(
                cliente_email=pedido.cliente_email,
                items=[item.model_dump() for item in pedido.items],
                idempotency_key=pedido.idempotency_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/orders/{order_id}")
    def obtener_pedido(order_id: int) -> dict:
        pedido = repo.obtener_pedido(order_id)
        if pedido is None:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        return pedido

    @app.post("/agent/run", response_model=AgentResponse)
    def ejecutar_agente(peticion: AgentRequest) -> AgentResponse:
        agente = Agent(settings, repo)
        try:
            return agente.ejecutar(peticion.tarea, peticion.datos, peticion.max_pasos)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/webhooks/catalog", status_code=201)
    def webhook_catalogo(
        payload: CatalogWebhook,
        x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    ) -> dict:
        if settings.webhook_secret:
            if not x_webhook_secret or not hmac.compare_digest(
                x_webhook_secret, settings.webhook_secret
            ):
                raise HTTPException(status_code=401, detail="Firma de webhook inválida")
        try:
            normalizado = normalizar_filas(payload.filas)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return repo.importar_catalogo(normalizado, origen=payload.origen)

    @app.get("/stats", response_model=Estadisticas)
    def estadisticas() -> Estadisticas:
        return Estadisticas(**repo.estadisticas())

    @app.get("/runs/{run_id}")
    def obtener_run(run_id: str) -> dict:
        run = repo.obtener_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Ejecución no encontrada")
        return run

    @app.get("/tools")
    def herramientas() -> dict:
        from app.tools import TOOL_SCHEMAS

        return {"herramientas": TOOL_SCHEMAS}

    @app.exception_handler(Exception)
    async def error_no_controlado(_request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno. Revisa los logs del servidor."},
        )

    return app
