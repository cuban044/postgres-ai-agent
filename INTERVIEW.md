# Defensa técnica — guía de entrevista

## Pitch de 90 segundos

> Construí una demostración de un agente LLM conectado a PostgreSQL y expuesto por una API REST.
> El agente no calcula los datos críticos: decide qué herramienta usar y el repositorio ejecuta SQL
> parametrizado dentro de transacciones. Por ejemplo, al crear un pedido bloqueo cada producto con
> `SELECT ... FOR UPDATE`, valido stock, inserto el pedido y las líneas, descuento inventario y hago
> commit; si algo falla, rollback completo. La API tiene validación Pydantic, clave de idempotencia
> para reintentos, webhook con secreto y trazas de cada ejecución en `agent_runs`. Lo probé contra
> PostgreSQL 18 real con 36 pruebas, incluidas pruebas de inyección SQL y de rollback, y 4 casos
> dorados. No está en producción y por defecto usa un LLM mock para que la demo sea reproducible y
> sin costo; el adaptador para un proveedor real está implementado.

## Cómo explicar la arquitectura en 2 minutos

1. **API:** FastAPI valida la entrada y expone endpoints REST.
2. **Agente:** bucle de function calling con lista cerrada de herramientas y máximo de pasos.
3. **Herramientas:** consultan o escriben a través del repositorio; no hay SQL en el prompt.
4. **Repositorio:** SQL parametrizado, transacciones y bloqueos.
5. **PostgreSQL:** restricciones, índices, `ON CONFLICT`, `JSONB` para trazas.
6. **Observabilidad:** cada ejecución guarda traza, tokens, costo y duración.
7. **Pruebas:** PostgreSQL real, no mocks; truncar y sembrar por prueba.

## Preguntas de PostgreSQL

### 1. ¿Por qué PostgreSQL y no SQLite?

Porque el requisito era PostgreSQL y porque necesito transacciones, bloqueos por fila,
restricciones reales, índices y `ON CONFLICT`. SQLite habría escondido esas capacidades.

### 2. ¿Cómo evitas vender el mismo stock dos veces?

`SELECT ... FOR UPDATE` dentro de una transacción. La fila queda bloqueada hasta el commit; el
segundo pedido espera y luego ve el stock actualizado. Si no alcanza, rollback.

### 3. ¿Qué nivel de aislamiento usas?

El de PostgreSQL por defecto: `READ COMMITTED`. Con `FOR UPDATE` cubro la condición de carrera del
stock. Si necesitara consistencia más estricta, evaluaría `REPEATABLE READ` y el costo de reintentos.

### 4. ¿Qué pasa si falla la segunda línea de un pedido?

Toda la transacción se revierte: no se descuenta la primera, no se crea el pedido, no quedan líneas
huérfanas. Hay una prueba específica (`test_stock_insuficiente_hace_rollback`).

### 5. ¿Cómo funciona la idempotencia?

`orders.idempotency_key` es `UNIQUE`. Antes de crear, busco la clave; si existe, devuelvo el pedido.
Si dos requests concurrentes pasan la verificación, la restricción única hace fallar a uno y el
código recupera el pedido existente. No se descuenta stock dos veces.

### 6. ¿Por qué guardas el nombre del producto en `order_items`?

Porque el catálogo cambia. El pedido histórico debe conservar el nombre y el precio del momento de
la compra. Es una migración con backfill (`004_order_item_snapshot.sql`).

### 7. ¿Qué índices tienes y por qué?

- `products.category_id`: filtro por categoría.
- `products.normalized_name`: búsquedas por nombre normalizado.
- `orders.customer_id` y `orders.created_at`: historial y reportes por fecha.
- `order_items.order_id`: detalle del pedido.
- `agent_runs.created_at`: consultas de ejecuciones recientes.

En producción mediría con `EXPLAIN ANALYZE` antes de añadir más.

### 8. ¿Cómo normalizarías un catálogo de 100.000 filas?

En la demo uso un proceso determinista y `ON CONFLICT`. Para 100k:
1. Cargar a una tabla staging con `COPY` (mucho más rápido que inserts uno a uno).
2. Normalizar por lotes en SQL/Python.
3. Hacer un merge a `products` con `INSERT ... SELECT ... ON CONFLICT`.
4. Procesar en una cola, con idempotencia y métricas.
5. Validar con conteos y muestras antes de publicar.

### 9. ¿Qué pasa con precios en USD?

Se marcan `requiere_conversion` y no se importan. No convierto sin una tasa explícita y con fecha;
inventar una tasa corrompe el catálogo.

### 10. ¿Cómo manejas migraciones?

`scripts/migrate.py` aplica archivos SQL en orden y registra versiones en `schema_migrations`.
Cada migración corre en una transacción. En un equipo grande usaría Alembic con revisión.

### 11. ¿Cómo escalarías la base?

PgBouncer, réplica de lectura para catálogo/reportes, índices medidos, particionado de
`agent_runs` por fecha y una cola para importaciones. No lo implementé: lo declaro como plan.

### 12. ¿Qué pasa si PostgreSQL está caído?

La creación del pool falla al arrancar y el health no responde; en producción añadiría reintentos
con backoff, timeout de conexión y un health degradado que no derribe la API.

## Preguntas de API y seguridad

### 13. ¿Cómo evitas SQL injection?

Todas las consultas usan parámetros (`%s`) y psycopg2 los escapa. Hay una prueba que envía
`bebidas'; DROP TABLE products; --` por query param y por payload del agente; la tabla sigue viva.

### 14. ¿Qué valida Pydantic?

Email, SKU, cantidad (1–1000), máximo 50 líneas por pedido y máximo 5000 filas por webhook.
Los errores devuelven 422 sin ejecutar la operación.

### 15. ¿Cómo proteges el webhook?

Secreto compartido en `X-Webhook-Secret` comparado con `hmac.compare_digest`. En producción
añadiría firma HMAC del cuerpo, timestamp, prevención de replay y rotación.

### 16. ¿Por qué no hay login?

Porque el alcance era demostrar agente + PostgreSQL + API. Añadir JWT a medias habría sido peor.
Lo declaro como limitación y explico el plan: autenticación, cuotas y rate limiting.

### 17. ¿Cómo evitas filtrar credenciales en logs o health?

El health usa un DSN saneado sin usuario/password. Los errores de negocio devuelven mensajes
acotados; el manejador global no incluye SQL ni trazas. Hay una prueba que verifica que
`supersecreto` no aparece en `/health`.

## Preguntas del agente y LLM

### 18. ¿Cómo decide el LLM qué herramienta usar?

Se le envían los esquemas JSON de 5 herramientas y el objetivo. Devuelve `tool_calls`; el agente
valida los argumentos, ejecuta y devuelve el resultado. Si no hay tool call, responde texto.

### 19. ¿Por qué el score/pedido no lo calcula el LLM?

Porque un LLM puede inventar cifras. Los números vienen de SQL y de reglas deterministas; el LLM
solo orquesta y redacta.

### 20. ¿Qué pasa si el LLM devuelve argumentos inválidos?

Se registra el paso con `ok: false`, se devuelve un error al modelo y se continúa. No se ejecuta
ninguna operación. Hay pruebas de error de herramienta.

### 21. ¿Cómo controlas el costo?

`AGENT_MAX_STEPS=6`, herramientas deterministas, trazas truncadas, modo mock para pruebas y
precios configurables para calcular costo. No invento una tarifa.

### 22. ¿Por qué no usaste LangChain?

Porque el bucle es pequeño y quiero poder explicar cada línea. Un framework añade capas y
dependencias que no aportan a este alcance.

### 23. ¿Cómo probarías el modo real?

Con una clave de prueba, un presupuesto de tokens, casos dorados y comparación contra el mock.
Mediría latencia, tokens y costo real; no lo he medido en esta máquina.

## Preguntas de proyecto y experiencia

### 24. ¿Qué parte te costó más?

La corrección transaccional y la idempotencia: son fáciles de describir y fáciles de romper.
Las pruebas de rollback y de doble pedido son la evidencia de que funciona.

### 25. ¿Qué mejorarías con más tiempo?

Auth, rate limiting, firma HMAC del webhook, importación por lotes para catálogos grandes,
observabilidad y un frontend mínimo.

### 26. ¿Esto demuestra experiencia profesional con PostgreSQL a escala?

No. Demuestra diseño y ejecución verificable en una demo con PostgreSQL real y pruebas. La
experiencia de producción a gran escala es un tema aparte y no la afirmo sin evidencia.

## Preguntas que deberías hacer tú

- ¿Qué volumen de datos y de tráfico maneja el equipo?
- ¿PostgreSQL autogestionado, Supabase u otro proveedor?
- ¿Cómo gestionan migraciones y despliegues?
- ¿Qué modelo usan y cómo miden costo/calidad?
- ¿Qué esperan de un AI Engineer en los primeros 90 días?

## Checklist antes de la entrevista

- [ ] Poder explicar el flujo de pedido sin mirar código.
- [ ] Poder explicar `FOR UPDATE`, idempotencia y rollback.
- [ ] Poder explicar por qué no se convierte USD.
- [ ] Poder ejecutar la demo y las pruebas en vivo.
- [ ] Tener claro qué es demo y qué sería producción.
