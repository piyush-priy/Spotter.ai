# 🛣️ Spotter.ai — Weather-Aware Truck Routing

A decision-support web application for truck drivers and dispatchers. Enter an origin, destination, departure time, and load weight — get up to three route alternatives scored against live weather forecasts with checkpoint-level risk classification.

> **Advisory disclaimer:** This application is a decision-support tool only. Conditions can change. Always follow official road restrictions and your carrier's safety policy.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS |
| Map | Leaflet.js + React-Leaflet |
| State | Zustand |
| Backend | Django 5 + Django REST Framework |
| Geocoding | OpenCage |
| Routing | OpenRouteService |
| Weather | Open-Meteo (free, no key required) |
| Testing | pytest (backend) · Vitest + Playwright (frontend) |

---

## Local Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- pnpm 9+

### Backend

```bash
cd backend

# Create and activate virtualenv
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# → Edit .env and fill in your provider API keys

# Run development server
python manage.py runserver
```

Server runs at `http://localhost:8000`

### Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Configure environment
cp .env.example .env.local
# → Set VITE_API_BASE_URL=http://localhost:8000

# Run dev server
pnpm dev
```

App runs at `http://localhost:5173`

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | ✅ | Django secret key — generate with `python -c "import secrets; print(secrets.token_hex(50))"` |
| `DJANGO_DEBUG` | ✅ | `True` for dev, `False` for prod |
| `DJANGO_ALLOWED_HOSTS` | ✅ | Comma-separated allowed hosts |
| `CORS_ALLOWED_ORIGINS` | ✅ | Comma-separated allowed frontend origins |
| `OPENCAGE_API_KEY` | ✅ | [OpenCage](https://opencagedata.com/) — free: 2,500 req/day |
| `ORS_API_KEY` | ✅ | [OpenRouteService](https://openrouteservice.org/) — free: 2,000 req/day |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `VITE_API_BASE_URL` | ✅ | Backend base URL (e.g. `http://localhost:8000`) |

---

## Running Tests

### Backend

```bash
cd backend
pytest                    # all tests with coverage
pytest -k test_risk       # run only risk engine tests
pytest --cov-report=html  # generate HTML coverage report
```

### Frontend

```bash
cd frontend
pnpm test           # unit tests (Vitest)
pnpm test:e2e       # end-to-end tests (Playwright)
pnpm tsc --noEmit   # type-check
pnpm lint           # ESLint
```

---

## API Reference

### `GET /api/v1/health/`

Returns process health and provider reachability.

### `POST /api/v1/trips/route-analysis`

**Request body:**
```json
{
  "origin": { "query": "Denver, CO" },
  "destination": { "query": "Chicago, IL" },
  "departure_at": "2026-11-02T08:00:00-07:00",
  "load_weight_lb": 42000,
  "checkpoint_spacing_miles": 25
}
```

**Response:** See `IMPLEMENTATION_PLAN.md` §9.2 for full response shape.

---

## Provider Sign-up Links

| Provider | Purpose | Free Tier |
|---|---|---|
| [OpenCage](https://opencagedata.com/api) | Geocoding | 2,500 req/day |
| [OpenRouteService](https://openrouteservice.org/dev/#/signup) | Routing + alternatives | 2,000 req/day |
| [Open-Meteo](https://open-meteo.com/) | Weather forecasts | Free, no key needed |

---

## Known Limitations

- **Forecast horizon:** Open-Meteo provides up to 7 days of hourly forecast. Checkpoints beyond the horizon are marked `UNKNOWN`.
- **Route alternatives:** OpenRouteService may return fewer than 3 alternatives for some city pairs. The UI displays however many are available.
- **No turn-by-turn:** This is a pre-trip decision tool, not navigation.
- **Advisory only:** Risk classification is based on weather forecasts which can change rapidly.

---

## Project Structure

```
spotter-routing/
├── backend/
│   ├── spotter/           # Django project (settings, urls, wsgi, asgi)
│   ├── trips/             # Main app
│   │   ├── adapters/      # Geocoding, routing, weather providers
│   │   ├── engine/        # Pure risk, checkpoint, ranking logic
│   │   └── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/    # TripForm, MapView, RouteSummaryPanel, etc.
│   │   ├── store/         # Zustand state
│   │   ├── api/           # Typed API client
│   │   └── types/         # Shared TypeScript types
│   └── tests/
├── .github/workflows/ci.yml
├── IMPLEMENTATION_PLAN.md
└── README.md
```

---

## Sprint Status

| Sprint | Status | Description |
|---|---|---|
| 0 | ✅ Done | Repo scaffold, CI, health endpoint, .gitignore |
| 1 | 🔜 Next | Risk engine, checkpoint pipeline, boundary tests |
| 2 | ⏳ | Provider adapters + route-analysis API |
| 3 | ⏳ | React UI (form, map, panels, slider) |
| 4 | ⏳ | Integration, E2E tests, accessibility |
| 5 | ⏳ | Deployment, hardening, walkthrough |

