# Orán AERO — versión 0.7

Aplicación meteorológica local con FastAPI y SQLAlchemy. Permite observaciones SYNOP en las secciones **0, 1, 3 y 5**, guardado definitivo, revisión y corrección como versiones independientes, módulo de Valores Extremos UTC e historial.

## Inicio rápido

Desde la carpeta del proyecto:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.bootstrap_admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000`.

Para MySQL/XAMPP, configurar `DATABASE_URL` en `.env` tomando `.env.example` como referencia. SQLite es la configuración predeterminada. Nunca usar bases históricas `oran_aero` ni `oran_aero_v2` para pruebas. No se incluye base de datos ni clave administrativa de ejemplo.

## Menús

- **Realizar SYNOP:** pantallas sin numerar; Fenómenos/visibilidad/suelo; nubosidad repartida en tres pantallas (observada, bases/desplazamiento, capas); precipitación solo en 00, 06, 12, 18 UTC; 57 condicional; secciones 0, 1, 3 y 5.
- **Datos de Estación e Instrumentos:** Jefe puede actualizar identificación y coordenadas, elegir viento estimado `iw=0/3` o con anemómetro `iw=1/4`; inventario con correcciones `S/C`/numéricas y fuera de servicio.
- **Información del Personal:** solo el Jefe crea, modifica o desactiva cuentas, incluso otros jefes; cada usuario cambia su propia contraseña, el Jefe restablece las ajenas.
- **Tablas:** consulta completa, descargar una hoja, proponer modificaciones en Excel, revisar diferencias, activar y restaurar la hoja anterior (solo Jefe).
- **Historial:** consultar informes y versiones; crear corrección desde un informe confirmado. No sobrescribe la versión previa.
- **Valores Extremos:** resumen UTC de 00:00 a 00:00 del día siguiente, viento máximo con primer instante de empate; temperaturas máxima/mínima instrumentales y extremos de TH, TV, PR y HR. Independiente de la HR extrema de Sección 5 que toma día civil previo HOA.

## Reglas críticas

Las temperaturas, presiones y precipitaciones admiten decimales; se cifra únicamente la primera décima y **no se redondea**. Los demás códigos son enteros. Las correcciones instrumentales se aplican automáticamente y se guardan junto a la versión del informe. Los instrumentos fuera de servicio no aportan lecturas nuevas. No se generan grupos SYNOP fuera del alcance seleccionado.

## Archivos relevantes

- `app/main.py`: autenticación, rutas, validación de entrada, persistencia y versiones.
- `app/models.py` y `app/schema_migrations.py`: tablas y ampliaciones aditivas de SQLite.
- `app/synop_v03.py`, `app/synop_rules_v05.py`, `app/section5_v07.py`: motor meteorológico.
- `app/services_v07.py`: extremos diarios UTC, extremos de HR por HOA y acumulación semanal.
- `app/static/workspace_v03.js`: navegación de formularios.
- `data/Tablas_Oran_Aero.xlsx`: consultas de la estación.
- `tests`: pruebas automáticas con `python -m pytest -q` (requiere `pytest` y `httpx` en el entorno de desarrollo).

## Precauciones operativas

Los cambios en tablas usan archivos y copias dentro de `data/`. No reemplazar esos archivos sin respaldo. No conectar esta edición con `oran_aero` histórica. Mantener fuera de repositorios `.env`, `.local_session_secret` y la base de datos. Para red compartida, activar HTTPS y restringir la red.


## Publicación segura en GitHub

Esta distribución fue depurada para compartir **solo el código y recursos de aplicación**: no incluye `.env`, secretos de sesión, entornos virtuales, bases de datos de operación, registros personales, respaldos ni documentos PDF externos.

1. Copiar `.env.example` a `.env` y ajustar la configuración solo en tu computadora (no publicar).
2. Crear un entorno virtual nuevo y ejecutar `python -m pip install -r requirements.txt` (incluye `tzdata` para Windows).
3. Iniciar la aplicación con `python -m scripts.bootstrap_admin` para crear tus propias credenciales y después `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. Si necesitás utilizar los visores de documentos, colocar las copias autorizadas de `clave_synop_smn_2022.pdf` y `libreta_smn_2022.pdf` en `data/pdf/` **solo localmente**. No se incluyen en el repositorio por tratarse de material documental de terceros.
5. La plantilla `.env.example` solo contiene marcadores de posición: **nunca** escribas allí usuarios, contraseñas ni claves reales.

**Importante:** el código incluye un modo de sesión HTTP destinado a desarrollo local (`https_only=False`). Antes de desplegar en una red pública, configurar HTTPS, secretos fuertes, controles de acceso y protección contra ediciones simultáneas del mismo borrador. No existe certificación de uso institucional por el SMN.

Los archivos de tablas meteorológicas de trabajo (`data/Tablas_Oran_Aero.xlsx` y JSON) se conservan porque la aplicación los necesita. Antes de publicar un repositorio público, verificar que tenés autorización para distribuir ese material de referencia.
