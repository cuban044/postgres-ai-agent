# Decisiones técnicas

## D-01. PostgreSQL como fuente de verdad

- **Contexto:** el requisito pide demostrar PostgreSQL, no una base embebida.
- **Decisión:** PostgreSQL real, con restricciones, transacciones e índices; pruebas contra una
  base dedicada (`agente_test`).
- **Alternativa descartada:** SQLite para simplificar.
- **Consecuencia:** la demo exige levantar PostgreSQL, pero lo que se muestra es lo que se afirma.

## D-02. SQL explícito + psycopg2 en lugar de ORM

- **Contexto:** el proyecto debe ser defendible línea por línea y demostrar SQL.
- **Decisión:** repositorio con consultas parametrizadas y `RealDictCursor`.
- **Alternativa descartada:** SQLAlchemy/Drizzle.
- **Consecuencia:** más código manual, pero control total de transacciones, bloqueos y planes.
  Un ORM sería razonable en un equipo grande; aquí ocultaría lo que se quiere demostrar.

## D-03. Pool de conexiones por proceso

- **Contexto:** abrir una conexión por request es caro y agota PostgreSQL.
- **Decisión:** `ThreadedConnectionPool` con mínimo 1 y máximo configurable (5 por defecto).
- **Alternativa descartada:** conexión global compartida.
- **Consecuencia:** seguridad entre hilos y reutilización; en producción se ajusta el pool y se
  añade PgBouncer si hay muchos workers.

## D-04. Transacciones con `SELECT ... FOR UPDATE`

- **Contexto:** dos pedidos concurrentes no pueden vender el mismo stock.
- **Decisión:** bloquear cada producto dentro de la transacción, validar stock y descontar antes
  del commit.
- **Alternativa descartada:** leer stock y actualizar después (race condition).
- **Consecuencia:** consistencia; el bloqueo es por producto y de corta duración.

## D-05. Idempotencia con clave única

- **Contexto:** reintentos de red o doble clic pueden duplicar un pedido.
- **Decisión:** `orders.idempotency_key` único; verificación previa y captura de violación única.
- **Alternativa descartada:** confiar en el cliente.
- **Consecuencia:** la segunda petición devuelve el mismo pedido sin descontar stock otra vez.

## D-06. Snapshot del nombre del producto en `order_items`

- **Contexto:** un catálogo cambia; el historial de un pedido no debería cambiar.
- **Decisión:** guardar `product_name` (además de precio unitario y subtotal) al crear la línea.
- **Alternativa descartada:** hacer join a `products.name` al consultar.
- **Consecuencia:** el histórico es estable. Migración `004` añade la columna con backfill.

## D-07. Runner de migraciones propio

- **Contexto:** la demo necesita migraciones reproducibles sin introducir Alembic.
- **Decisión:** `scripts/migrate.py` aplica archivos `.sql` en orden y registra versiones.
- **Alternativa descartada:** ejecutar un `schema.sql` completo cada vez.
- **Consecuencia:** evolución segura y didáctica. En producción con un equipo grande, Alembic
  (o similar) con revisión de migraciones sería la opción.

## D-08. Normalización determinista y sin conversión de moneda

- **Contexto:** un LLM no debe inventar categorías, precios ni tasas de cambio.
- **Decisión:** reglas de código para nombres, categorías, precios y duplicados; USD se marca y
  no se importa.
- **Alternativa descartada:** pedir al LLM que normalice los datos.
- **Consecuencia:** resultados reproducibles; las filas dudosas se reportan, no se adivinan.

## D-09. Mock LLM por defecto

- **Contexto:** pruebas y demo no pueden depender de red, clave ni costo variable.
- **Decisión:** `MockLLM` con guion determinista; modo real opt-in con API compatible con OpenAI.
- **Alternativa descartada:** exigir una clave desde el inicio.
- **Consecuencia:** 36 pruebas reproducibles; el modo real queda implementado y claramente
  etiquetado como no medido en esta máquina.

## D-10. Webhook con secreto compartido

- **Contexto:** el endpoint de catálogo recibirá datos de terceros.
- **Decisión:** `X-Webhook-Secret` con `hmac.compare_digest` cuando `WEBHOOK_SECRET` está definido.
- **Alternativa descartada:** aceptar cualquier POST.
- **Consecuencia:** protección básica. En producción: firma HMAC del cuerpo, timestamp,
  prevención de replay y rotación de secretos.

## D-11. Pruebas contra PostgreSQL real

- **Contexto:** mockear la base esconde errores de SQL, transacciones y restricciones.
- **Decisión:** cada prueba usa `agente_test`, trunca y re-siembra; se prueba rollback e inyección.
- **Alternativa descartada:** SQLite en memoria o mocks del repositorio.
- **Consecuencia:** pruebas más lentas (~6 s) pero creíbles.

## D-12. Sin autenticación de usuarios en la demo

- **Contexto:** el alcance es demostrar agente + PostgreSQL + API, no un SaaS completo.
- **Decisión:** no incluir login; documentarlo como limitación y plan de producción.
- **Alternativa descartada:** añadir JWT a medias.
- **Consecuencia:** el alcance queda honesto y completo; no se simula seguridad que no existe.
