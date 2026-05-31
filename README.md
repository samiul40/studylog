# Studyflow

A Django-based study tracking app that lets users organise learning resources (videos, readings) into structured units and track their progress.

## Tech Stack

- **Backend:** Django 5.2, PostgreSQL 16, Django REST Framework
- **Auth:** django-allauth (email verification + Google OAuth)
- **Frontend:** Bootstrap (vendored), SCSS compiled via npm
- **Dev tooling:** Docker Compose, MailHog (local email), Nginx (reverse proxy)
- **Testing:** pytest, model-bakery

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js (for SCSS compilation)
- PostgreSQL (local) **or** Docker

---

### Local (venv) Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd studyflow

# 2. Create and activate a virtual environment
python -m venv web/venv
source web/venv/bin/activate   # Windows: web\venv\Scripts\activate

# 3. Install Python dependencies
pip install -r web/requirements.txt

# 4. Install Node dependencies and build CSS
cd web
npm install
npm run build:css

# 5. Set up environment variables
cp web/.env.example web/.env
# Edit web/.env and fill in your Postgres credentials and SECRET_KEY

# 6. Run migrations and start the dev server
python manage.py migrate
python manage.py runserver
```

The app will be available at `http://localhost:8000`.

> **Email in dev:** With `DEBUG=True`, Django uses the console email backend — emails print to the terminal. No mail server needed.

---

### Docker Setup

```bash
# 1. Copy and fill in environment variables
cp web/.env.example web/.env
# Edit web/.env — set SECRET_KEY, Postgres credentials, DJANGO_SETTINGS_MODULE, etc.

# 2. Start all services
docker compose up --build
```

| Service  | URL                           | Notes                        |
|----------|-------------------------------|------------------------------|
| App      | http://localhost               | Served via Nginx on port 80  |
| MailHog  | http://localhost:8025          | Local email UI               |

---

## Common Commands

All commands run from `web/`.

| Task                   | Command                                      |
|------------------------|----------------------------------------------|
| Run dev server         | `python manage.py runserver`                 |
| Run all tests          | `pytest`                                     |
| Run a single test file | `pytest path/to/test_file.py`                |
| Run tests with coverage| `pytest --cov`                               |
| Lint                   | `ruff check web/`                            |
| Fix lint               | `ruff check --fix web/`                      |
| Watch SCSS (dev)       | `npm run watch:css`                          |
| Build CSS (production) | `npm run build:css`                          |
| Make migrations        | `python manage.py makemigrations`            |
| Apply migrations       | `python manage.py migrate`                   |

---

## Project Structure

```
studyflow/
├── docker-compose.yml
├── dockerfiles/
│   ├── backend/        # App Dockerfile
│   └── nginx/          # Nginx config
└── web/                # Django project root
    ├── studyflow/       # Settings package + SCSS source
    ├── learning/        # Core domain app
    ├── accounts/        # Auth (login/logout/profile)
    └── pages/           # Static/landing pages
```

### Key Concepts

- **ResourceType** — categorises resources as `video` or `reading`, driving unit labels ("Unit" vs "Chapter").
- **LearningResource** — user-owned collection of ordered units.
- **LearningUnit** — individual piece of content; `status` auto-updates from `video_progress_minutes` on save.
- **Dashboard stats** — `learning/services/dashboard.py::get_dashboard_stats()` is the single source of truth for both the user dashboard and the staff admin view.

---

## Running Tests

Tests use **SQLite in-memory** when `CI=true` is set, and a real Postgres instance locally.

```bash
cd web
pytest                          # all tests
pytest --cov                    # with coverage report
pytest learning/tests/test_learning_resource_views.py  # single file
```

---

## Environment Variables

| Variable                     | Required   | Description                                                                 |
|------------------------------|------------|-----------------------------------------------------------------------------|
| `SECRET_KEY`                 | Yes        | Django secret key — keep this secret in production                          |
| `DEBUG`                      | Yes        | `True` for dev, `False` for production                                      |
| `ALLOWED_HOSTS`              | Yes        | Comma-separated list of allowed hostnames                                   |
| `POSTGRES_HOST`              | Yes        | Postgres host                                                               |
| `POSTGRES_PORT`              | Yes        | Postgres port (default `5432`)                                              |
| `POSTGRES_DB`                | Yes        | Database name                                                               |
| `POSTGRES_USER`              | Yes        | Database user                                                               |
| `POSTGRES_PASSWORD`          | Yes        | Database password                                                           |
| `DJANGO_SETTINGS_MODULE`     | Docker only| e.g. `studyflow.settings`                                                   |
| `EMAIL_HOST`                 | No         | SMTP host (use `localhost` with MailHog in Docker)                          |
| `EMAIL_PORT`                 | No         | SMTP port (use `1025` with MailHog)                                         |
| `DEFAULT_FROM_EMAIL`         | No         | From address for outgoing emails                                            |
| `ACCOUNT_EMAIL_VERIFICATION` | No         | `mandatory` (production default) or `none` to skip verification in dev      |
| `ADMIN_URL`                  | No         | Path for the Django admin panel (default `admin/`). Set to a random string in production, e.g. `xk9p2m8q3r/` (include trailing slash) |
