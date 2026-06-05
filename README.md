# Ventusky Forecast API

API REST de pronóstico meteorológico construida con **FastAPI** y **Docker**.

---

## Estructura del proyecto

```
ventusky-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # Entrada de la app FastAPI
│   ├── routes.py            # Endpoints REST
│   └── ventusky_service.py  # Scraping y lógica de negocio
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2

---

## Levantar con Docker Compose

```bash
# 1. Clonar / copiar el proyecto
cd ventusky-api

# 2. Construir la imagen
docker compose build

# 3. Levantar en background
docker compose up -d

# 4. Ver logs
docker compose logs -f

# 5. Detener
docker compose down
```

La API quedará disponible en: **http://localhost:8000**

---

## Endpoints

### `GET /health`
Verificación de estado del servicio.

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

### `GET /forecast/hourly`
Pronóstico hora a hora (8 horarios por día).

| Parámetro | Tipo  | Requerido | Descripción |
|-----------|-------|-----------|-------------|
| `lat`     | float | ✅        | Latitud     |
| `lon`     | float | ✅        | Longitud    |

```bash
curl "http://localhost:8000/forecast/hourly?lat=-17.783&lon=-63.182"
```

---

### `GET /forecast/daily`
Resumen diario: temperatura min/max, lluvia acumulada, velocidad y ráfaga de viento.

```bash
curl "http://localhost:8000/forecast/daily?lat=-17.783&lon=-63.182"
```

---

### `GET /forecast/tramos`
Pronóstico dividido por tramos del día: `madrugada`, `mañana`, `tarde`, `noche`.

```bash
curl "http://localhost:8000/forecast/tramos?lat=-17.783&lon=-63.182"
```

---

## Campos de respuesta

| Campo  | Descripción                        |
|--------|------------------------------------|
| `td`   | Temperatura (°C)                   |
| `sr`   | Lluvia acumulada (mm)              |
| `rp`   | Probabilidad de lluvia (%)         |
| `vsd`  | Velocidad del viento (km/h)        |
| `vg`   | Ráfaga de viento (km/h)            |
| `vdId` | Dirección del viento (ID)          |
| `vd45` | Dirección del viento (45°)         |

---

## Desarrollo local (sin Docker)

```bash
# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# Instalar dependencias
pip install -r requirements.txt

# Correr la API
uvicorn app.main:app --reload --port 8000
```
