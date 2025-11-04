# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DCDock is a distribution center dock scheduling application with a FastAPI backend and a Textual TUI client. It supports multi-user concurrent access with real-time WebSocket updates, optimistic locking for conflict resolution, and role-based access control.

**Requirements:** Python 3.11 or higher (Python 3.13+ recommended)

## Development Commands

### Initial Setup

```bash
# Quick setup (recommended)
./setup.sh

# Or manual setup
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pip install --force-reinstall "bcrypt>=4.0.0,<5.0.0"
python -m app.seed

cd ../client_tui && python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
```

### Running the Application

```bash
# Terminal 1 - Start backend server
cd backend && python run.py
# Or: make run-backend

# Terminal 2 - Start TUI client
cd client_tui && python run.py
# Or: make run-client
```

### Testing

```bash
# Run all backend tests
cd backend && pytest

# Run with coverage
cd backend && pytest --cov=app --cov-report=html

# Or use Makefile
make test
```

### Code Quality

```bash
# Lint code
cd backend && ruff check app/
cd backend && mypy app/

# Format code
cd backend && black app/
cd backend && ruff check --fix app/

# Or use Makefile
make lint
make format
```

### Database Operations

```bash
# Seed database with demo data
cd backend && python -m app.seed
# Or: make seed

# Database migrations (using Alembic)
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"
```

### Building Production Executables

```bash
# Install build dependencies
cd client_tui && pip install -e ".[build]"

# Build for current platform
cd client_tui && pyinstaller dcdock.spec
# Output: dist/dcdock.exe (Windows) or dist/dcdock (macOS/Linux)
```

## Architecture Overview

### Backend Structure

The backend is organized as follows:

- **`app/api/`** - FastAPI route handlers for each resource (users, ramps, loads, statuses, assignments, audit, websocket)
- **`app/core/`** - Core utilities (config, security/JWT, password hashing)
- **`app/db/`** - Database layer
  - `models.py` - SQLAlchemy ORM models with relationships
  - `session.py` - Database session management and engine configuration
  - `base.py` - Base model classes with timestamps and versioning
- **`app/schemas/`** - Pydantic models for request/response validation
- **`app/services/`** - Business logic layer (currently only audit service)
- **`app/ws/`** - WebSocket connection manager and broadcast handlers
- **`app/seed.py`** - Database seeding script with demo data
- **`app/main.py`** - FastAPI application setup, middleware, and router registration

### Database Models & Relationships

All models inherit from `BaseModel` which provides:
- Auto-incrementing `id` (primary key)
- `created_at` and `updated_at` timestamps
- `version` field for optimistic locking (assignments only)

Key models:
- **User** - Authentication, roles (ADMIN/OPERATOR), tracks created/updated assignments
- **Ramp** - Physical loading docks (R1-R8), identified by unique code
- **Status** - Workflow states (PLANNED, ARRIVED, IN_PROGRESS, DELAYED, COMPLETED, CANCELLED) with colors and sort order
- **Load** - Shipments with direction (IB=inbound, OB=outbound), references, ETAs
- **Assignment** - Central entity linking Ramp + Load + Status with ETAs and audit tracking
- **AuditLog** - Complete change history with before/after JSON snapshots

### Optimistic Locking

All assignment updates require the current `version` number. The version is automatically incremented on each update. If a version mismatch occurs, the API returns HTTP 409 Conflict with the current data, allowing the client to resolve the conflict.

Implementation: `Assignment` model has a `version` field that is checked before updates in `app/api/assignments.py`.

### WebSocket Real-Time Updates

The WebSocket system (`app/ws/manager.py`) broadcasts assignment changes to all connected clients:

- **Connection**: `ws://localhost:8000/api/ws?token=JWT_TOKEN`
- **Message types**: `connection_ack`, `assignment_created`, `assignment_updated`, `assignment_deleted`, `conflict_detected`
- **Direction filtering**: Clients can subscribe to only IB or OB updates
- **Thread-safe**: Uses asyncio locks for concurrent connection management

Broadcasting is triggered automatically from assignment API endpoints (create/update/delete).

See `docs/WEBSOCKET.md` for full API documentation.

### TUI Client Structure

The Textual-based client is organized as:

- **`app/screens/`** - TUI screens (login, main board)
- **`app/services/`** - API client and WebSocket client services
- **`app/widgets/`** - Custom Textual widgets
- **`app/main.py`** - Application entry point with CLI arguments

The client connects to the backend via HTTP (for auth/CRUD) and WebSocket (for real-time updates).

### Authentication Flow

1. User logs in via `POST /api/auth/login` with email/password
2. Backend validates credentials, returns JWT access token
3. Client stores token and includes it in all subsequent requests via `Authorization: Bearer <token>` header
4. WebSocket connections authenticate via query parameter: `?token=<token>`
5. JWT contains user ID and role for authorization checks

Token expiration is configured via `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 1440 = 24 hours).

### Database Switching

The application automatically detects the database type from `DATABASE_URL`:

- **SQLite** (dev): `sqlite+aiosqlite:///./dcdock.db`
- **PostgreSQL** (prod): `postgresql+asyncpg://user:pass@host:5432/dcdock`

Both use async drivers (aiosqlite, asyncpg) and support the same features.

### Role-Based Access Control

- **ADMIN** - Full CRUD access to all resources, can manage users
- **OPERATOR** - Can view all resources, create/update/delete assignments and loads, cannot manage users/ramps/statuses

Authorization is enforced via FastAPI dependencies in `app/api/dependencies.py`:
- `get_current_user()` - Extracts user from JWT
- `require_admin()` - Ensures user has ADMIN role

## Common Development Patterns

### Adding a New API Endpoint

1. Define Pydantic schemas in `app/schemas/<resource>.py`
2. Add route handler in `app/api/<resource>.py`
3. Register router in `app/main.py`
4. Add business logic to `app/services/` if complex
5. Update audit logging if the endpoint modifies data

### Running Tests for a Single File

```bash
cd backend && pytest tests/test_specific_file.py
cd backend && pytest tests/test_specific_file.py::test_function_name
```

### Debugging WebSocket Issues

1. Start backend: `cd backend && python run.py`
2. Run test client: `python backend/test_websocket_client.py [email] [password] [direction]`
3. Trigger changes via API in another terminal
4. Check WebSocket stats: `curl http://localhost:8000/api/ws/stats`

### Production Deployment Notes

- Always use PostgreSQL in production (not SQLite)
- Generate secure `SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Use HTTPS/WSS (not HTTP/WS)
- Configure CORS origins for your domain
- Run database seed: `python -m app.seed` after initial setup
- See `docs/PRODUCTION.md` for full deployment guide including Docker, Nginx, SSL, monitoring

### Demo Credentials

- Admin: `admin@dcdock.com` / `admin123`
- Operator: `operator1@dcdock.com` / `operator123`

## Technology Stack

- **Backend**: FastAPI, SQLAlchemy (async), Pydantic, JWT, Alembic, SQLite/PostgreSQL
- **Frontend**: Textual TUI, WebSocket, PyInstaller
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Code Quality**: ruff, black, mypy
