# RoboClub Data Pipeline

Full-stack rewrite of the React dashboard into:
- **FastAPI** (Python) — backend REST + SSE API on port `8000`
- **Flask** (Python) — frontend Jinja2 templates on port `5000`

## Project structure

```
roboclub/
├── backend/
│   ├── main.py              # FastAPI app — all /api/* routes
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py               # Flask app — renders templates
│   ├── requirements.txt
│   ├── Dockerfile
│   └── templates/
│       ├── base.html        # Shared layout, CSS, nav, JS helpers
│       ├── pipeline.html    # Architecture diagram + SSE event stream
│       ├── kafka.html       # Kafka topics & consumer lag
│       ├── docker.html      # Container list with live CPU bars
│       ├── ingestion.html   # Data sources + schema examples
│       ├── dashboard.html   # KPI cards + school status grid (live SSE)
│       ├── attendance.html  # Live check-in feed + attendance board
│       ├── ceo.html         # Weekly digest + send button
│       ├── notifications.html  # Alert rules + notification feed
│       └── 404.html
├── docker-compose.yml
└── README.md
```

## Deploy to Vercel (no Docker)

See **[VERCEL.md](VERCEL.md)** for step-by-step instructions.

Quick version: push to GitHub → import on [vercel.com/new](https://vercel.com/new) → Deploy.

## Running with Docker Compose (recommended)

```bash
docker compose up --build
```

Then open **http://localhost:5000** in your browser.

## Running locally (dev)

**Backend (FastAPI)**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
API docs available at http://localhost:8000/docs

**Frontend (Flask)**
```bash
cd frontend
pip install -r requirements.txt
python app.py          # or: flask run --port 5000
```

Open http://localhost:5000

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/events/stream` | SSE live event stream (~1 event/3.5s) |
| GET | `/api/attendance/live` | Current school attendance snapshot |
| GET | `/api/attendance/stream` | SSE live attendance updates |
| GET | `/api/notifications/stream` | SSE new notifications + badge count |
| GET | `/api/kafka/topics` | Kafka topics with live message counts |
| GET | `/api/kafka/cluster` | Cluster health stats |
| GET | `/api/kafka/consumers` | Consumer lag per service |
| GET | `/api/docker/services` | Running containers with live CPU |
| GET | `/api/notifications` | All notifications |
| PUT | `/api/notifications/{id}/read` | Mark one notification read |
| PUT | `/api/notifications/all/read` | Mark all notifications read |
| GET | `/api/notifications/unread-count` | Badge count |
| GET | `/api/dashboard/kpis` | Live KPI metrics |
| GET | `/api/dashboard/schools` | School status grid |
| GET | `/api/ingestion/sources` | Ingestion pipeline sources |
| GET | `/api/ceo/report` | Weekly digest data |
| POST | `/api/ceo/send` | Trigger CEO report dispatch |
| GET | `/health` | Health check |

## Architecture

```
Browser → Flask :5000 → serves HTML + Jinja2 templates
                         JS in templates → fetch() → FastAPI :8000
                                           SSE      → FastAPI :8000/api/events/stream
```

The Flask app is purely a **view layer** — it renders HTML skeletons and all live data
is fetched client-side via the FastAPI REST/SSE endpoints. This means:
- Flask can be replaced with any template engine or even a CDN-served static HTML
- FastAPI handles all business logic and data serving
- The `API_URL` environment variable points Flask templates at the right backend
