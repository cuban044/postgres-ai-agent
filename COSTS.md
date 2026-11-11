# Costos

## Regla

No se inventan tarifas. El costo del LLM depende del proveedor, modelo y fecha. La demo registra
tokens por ejecución y calcula costo solo si el operador configura los precios vigentes.

## Costo de la demo

- LLM en modo mock: **0** (sin red, sin proveedor).
- PostgreSQL local: **0** (instalación de desarrollo).
- Pruebas y evaluaciones: **0** en servicios externos.

## Costo del modo real

Cada fila de `agent_runs` guarda `input_tokens`, `output_tokens`, `model`, `mode` y
`estimated_cost`.

Fórmula:

```
costo = (tokens_entrada / 1_000_000) × precio_entrada_por_millón
      + (tokens_salida  / 1_000_000) × precio_salida_por_millón
```

Variables:

```bash
export LLM_PRICE_IN_PER_MTOK="<precio vigente>"
export LLM_PRICE_OUT_PER_MTOK="<precio vigente>"
```

Si faltan, `costo_estimado` queda en `null`. No hay tarifa por defecto.

## Ejemplo aritmético (hipotético, no es una tarifa)

Con `precio_entrada = 1.00` y `precio_salida = 2.00` por millón:

- 1,000 tokens de entrada → 0.001
- 500 tokens de salida → 0.001
- Costo de la ejecución → 0.002

Es solo la fórmula. **No** representa el precio de ningún proveedor.

## Cómo medir el costo real

1. Elegir el modelo exacto.
2. Consultar la página oficial de precios y anotar URL y fecha.
3. Configurar las variables.
4. Ejecutar 10–20 casos representativos.
5. Sumar `estimated_cost` en `agent_runs`.
6. Comparar con la facturación del proveedor; si difiere, documentar el ajuste.

## Validación real con tope de presupuesto

`scripts/validar_llm_real.py` queda preparado para una prueba real con Function Calling:

- Exige `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` y precios por millón de tokens.
- Calcula el peor caso y **rechaza la ejecución si supera 0.25 USD**.
- Solo permite la herramienta de lectura `consultar_catalogo`.
- No imprime ni guarda la clave; el reporte va a `evals/llm_real_reporte.json` (ignorado por Git).
- En esta máquina **no hay credencial dedicada**, por lo que no se ejecutó y no se gastó nada.

## Costo de PostgreSQL en producción

No se incluye una cifra porque depende del proveedor, región, almacenamiento, backups y réplicas.
Antes de contratar: cotizar, comparar y no crear infraestructura facturable sin autorización.
