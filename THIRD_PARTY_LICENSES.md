# Licencias de terceros

Este proyecto **no incluye un archivo LICENSE para su propio código**. Por ahora se mantiene sin
licencia de reutilización; todos los derechos quedan reservados al autor hasta que decida otra cosa.
Esto no implica que las dependencias carezcan de licencia: cada una tiene la suya.

## Dependencias directas

| Dependencia | Uso | Licencia | Nota |
|---|---|---|---|
| Python 3.13 | Runtime | PSF License | Entorno de ejecución |
| FastAPI | API REST | MIT | Verificar en PyPI antes de distribuir |
| Uvicorn | Servidor ASGI | BSD-3-Clause | Verificar metadatos del paquete |
| Pydantic | Validación | MIT | Verificar metadatos del paquete |
| psycopg2-binary | Driver PostgreSQL | LGPL con excepciones | Revisar obligaciones si se distribuye el binario |
| httpx | Cliente HTTP | BSD-3-Clause | Confirmado en metadatos |
| pytest | Pruebas | MIT | Solo desarrollo |

## Dependencias transitivas

Las dependencias transitivas (Starlette, AnyIO, Click, H11, Certifi, etc.) tienen sus propias
licencias. Antes de una distribución pública:

1. Generar un inventario con `pip-licenses` o `pip show` en un entorno limpio.
2. Revisar LICENSE de cada paquete en PyPI.
3. Conservar los avisos de copyright requeridos.
4. No reutilizar código de terceros sin cumplir su licencia.

## Contenido propio

- Código, migraciones, pruebas y documentación: autoría del dueño del workspace, con asistencia de
  herramientas de IA declarada.
- No contiene código de SitioBox, Manus, Base44 ni de otros productos comerciales.
- No contiene assets, fuentes ni imágenes de terceros.
- Los datos de ejemplo son ficticios (`@example.com`).

## Estado

- `LICENSE` propio: **no incluido** (decisión pendiente; derecho reservado por defecto).
- Licencias de terceros: documentadas arriba; verificar versiones fijadas antes de publicar.
