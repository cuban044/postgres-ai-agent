# Guion de demostración (6–8 minutos)

## Preparación

```bash
cd 03-proyectos/postgres-ai-agent

# PostgreSQL local en 55432 (si no está corriendo)
PG="$(scoop prefix postgresql)/bin"
"$PG/pg_ctl" -D "$(scoop prefix postgresql)/data" -o "-p 55432" -l "$(scoop prefix postgresql)/postgres-55432.log" start

export DATABASE_URL="postgresql://agente_app@127.0.0.1:55432/agente"
export TEST_DATABASE_URL="postgresql://agente_app@127.0.0.1:55432/agente_test"

python scripts/migrate.py
python scripts/reset_demo.py
python -m pytest -q
python evals/run_evals.py
```

Resultado esperado: **36 passed** y **4/4 (100%)**.

## 1. Salud y conexión real (30 s)

```bash
uvicorn app.main:app --reload
```

Abrir http://127.0.0.1:8000/health. Señalar:

- `db_ok: true`, base PostgreSQL, modo `mock`.
- 5 herramientas expuestas.
- No aparece ningún password en la respuesta.

## 2. Catálogo desde PostgreSQL (30 s)

```bash
curl "http://127.0.0.1:8000/products?categoria=bebidas&limite=3"
```

Señalar el filtro por categoría (columna indexada) y el stock real.

## 3. Pedido transaccional (90 s)

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_email": "laura@example.com",
    "items": [
      {"sku": "BEV-001", "cantidad": 2},
      {"sku": "ALI-001", "cantidad": 1}
    ],
    "idempotency_key": "demo-001"
  }'
```

Resultado real de la demo:

```json
{
  "order_id": 1,
  "estado": "pending",
  "total_mxn": 523.0,
  "items": [
    {"sku": "BEV-001", "cantidad": 2, "subtotal": 498.0},
    {"sku": "ALI-001", "cantidad": 1, "subtotal": 25.0}
  ],
  "idempotente": false
}
```

Señalar:

- `SELECT ... FOR UPDATE` bloquea el stock.
- Si una línea falla, rollback completo.
- Repetir el POST con `demo-001` devuelve el mismo pedido con `"idempotente": true` y **no**
  descuenta stock otra vez.

Prueba de stock insuficiente:

```bash
curl -i -X POST http://127.0.0.1:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"cliente_email":"laura@example.com","items":[{"sku":"BEV-001","cantidad":999}]}'
```

Debe responder `400` con `Stock insuficiente` y el stock intacto.

## 4. Agente sobre PostgreSQL (60 s)

```bash
curl -X POST http://127.0.0.1:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{"tarea":"resumen_ventas","datos":{"desde":"2026-11-01","hasta":"2026-11-30"}}'
```

Señalar:

- `traza` con la herramienta ejecutada, argumentos y duración.
- Respuesta: 1 pedido, $523.00 MXN, top Café molido y Galletas.
- `run_id` permite recuperar la traza con `GET /runs/{id}`.
- El LLM decide la herramienta; los números vienen de SQL.

## 5. Importación de catálogo (90 s)

```bash
curl -X POST http://127.0.0.1:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "tarea":"normalizar_catalogo",
    "datos":{
      "origen":"demo.csv",
      "filas":[
        {"sku":"BEV-001","nombre":"Café molido 1 kg","categoria":"Bebidas","precio":"$245.00","stock":30,"proveedor":"Sur"},
        {"sku":"IMP-7777","nombre":"Agua de coco 1 L","categoria":"Bebidas","precio":"$45.00","stock":12,"proveedor":"Nuevo"},
        {"sku":"IMP-7778","nombre":"Producto USD","categoria":"Otros","precio":"USD 10"}
      ]
    }
  }'
```

Señalar:

- Upsert por SKU (`ON CONFLICT DO UPDATE`).
- Fila USD **no** se convierte: se omite y se reporta.
- Se registra la importación en `catalog_imports`.
- Duplicados y precios inválidos se reportan, no se adivinan.

## 6. Webhook protegido (45 s)

Con `WEBHOOK_SECRET` definido:

```bash
curl -i -X POST http://127.0.0.1:8000/webhooks/catalog \
  -H "Content-Type: application/json" \
  -d '{"origen":"x.csv","filas":[{"sku":"X-1","nombre":"Producto","categoria":"Otros","precio":"10"}]}'
# 401

curl -X POST http://127.0.0.1:8000/webhooks/catalog \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -d '{"origen":"x.csv","filas":[{"sku":"X-1","nombre":"Producto","categoria":"Otros","precio":"10"}]}'
# 201
```

## 7. Pruebas y evaluación (45 s)

```bash
python -m pytest -q
python evals/run_evals.py
```

Señalar:

- 36 pruebas contra PostgreSQL real, no mocks.
- Pruebas de rollback, idempotencia, inyección SQL y webhook.
- 4 casos dorados reproducibles.

## Preguntas que conviene provocar

- ¿Qué pasa si dos clientes compran el último producto a la vez?
- ¿Qué pasa si el webhook se reintenta?
- ¿Qué pasa si el proveedor manda un precio en USD?
- ¿Qué pasa si el LLM devuelve argumentos inválidos?
- ¿Cómo se controla el costo del LLM?

## Honestidad

- Es una demostración, no producción.
- El modo LLM real está implementado pero no medido aquí.
- La autenticación de usuarios está fuera del alcance y se declara como pendiente.
