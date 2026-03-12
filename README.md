# Transaction Management System

### Full-stack Concurrency protection, race conditions and time complexity O(1)

This repository contains a full-stack transaction management system built with Python and React. The system has been re-architected to guarantee ACID compliance, handle high concurrency without race conditions, and provide O(1) read performance for account balances.

The original architecture suffered from linear O(N) time complexity on read operations and lacked concurrency protection.

The system was redesigned for production readiness:

1. Layered Architecture — Strict separation of concerns
2. CQRS & Denormalization for scaling (Solving the O(N) Read Bottleneck)
3. The Unit of Work Pattern (Solving Race Conditions)
4. Idempotency (Safe retries on network failures)
5. Two-Tier Error Handling — Safe error responses without leaking internals


## Tech Stack

| Layer    | Technology                                         |
| -------- | -------------------------------------------------- |
| Frontend | JavaScript, React 18, Vite 6                       |
| Backend  | Python 3.13, Sanic 24 (async)                      |
| Database | SQLite with WAL-mode + aiosqlite                   |
| Testing  | Cypress (E2E), pytest (backend), Vitest (frontend) |

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm

## Architecture
```
app-sanic/
├── server.py              # Entry point — Sanic app, CORS, startup
├── config/settings.py     # Centralized configuration
├── routes/api_routes.py   # HTTP handlers (network layer)
├── services/              # Business logic + validation
├── models/
│   ├── database.py        # Connection management + schema
│   ├── repositories.py    # Parameterized SQL queries (data layer)
│   └── unit_of_work.py    # BEGIN EXCLUSIVE / COMMIT / ROLLBACK
└── utils/
    ├── exceptions.py      # AppError → BadRequestError, NotFoundError
    └── error_handler.py   # Two-tier: domain errors (4xx) + catch-all (500)

app-react/src/
├── components/            # UI components (TransactionForm, TransactionList, TransactionItem)
├── hooks/useTransactions  # State management + validation logic
└── services/api.js        # Network layer — all fetch() calls
```

## Key Design Decisions

| Decision             | Problem                                                                                | Solution                                                                                         |
| -------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Layered Architecture | HTTP logic and database queries in one file makes testing hard and code unmaintainable | Decoupled into Routes, Services, Repositories and more                                           |
| Denormalized balance | GET /accounts/:id required SUM() over all transactions — O(n)                          | Pre-computed balance column updated atomically on each write — O(1)                              |
| WAL-mode             | Default SQLite journal blocks readers during writes                                    | WAL separates readers from writers, enabling concurrent access                                   |
| Unit of Work         | Denormalized balance creates risk of inconsistent state                                | BEGIN EXCLUSIVE → atomic `balance = balance + ?` → COMMIT/ROLLBACK                               |
| Idempotency          | Network retries could create duplicate transactions                                    | UNIQUE constraint on idempotency_key — safe to retry                                             |
| aiosqlite            | Synchronous sqlite3 blocks Sanic's event loop                                          | Non-blocking I/O via background thread — event loop stays free                                   |
| Explicit INDEX       | Queries on account_id require full table scan — O(n)                                   | B-tree index enables O(log n) lookups                                                            |
| Two-tier errors      | Risk of leaking internal details to client                                             | Domain errors (4xx) return safe messages; unexpected errors (500) log full traceback server-side |

## Code Quality
  - **Type safety**: Python type annotations on all service, repository, and route functions
  - **Python**: Formatted with Black, linted with Ruff — config in pyproject.toml
  - **React/JS**: Formatted with Prettier — config in .prettierrc


## Getting Started
To run the application, you can choose between running both servers from the root or running them individually for better log visibility during development.

### Unified Startup:

**Directory:** root directory

**Command:**
```bash
# 1. Setup Python Environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies & Build
npm install
npm run build

# 3. Start both servers
# Backend runs on http://localhost:8000
# Frontend runs on http://localhost:3000
npm run start
```

### Start each server individually (Development/Review):
**Command:**
```bash
# Terminal 1 (Backend)
cd app-sanic
source ../venv/bin/activate  # Assuming venv is in the root
pip install -r requirements.txt
sanic server.app

# Terminal 2 (Frontend)
cd app-react
npm install # Assuming not already installed
npm run start
```


## Running Tests

The test part is split into three layers:

- **Cypress (End 2 End):** Verifies the full user flow — create transactions, read balances, reject invalid input.
- **pytest (Backend):** 14 integration tests proving ACID guarantees, idempotency, validation rules, and race condition safety against a real SQLite database.
- **Vitest (Frontend):** 6 component tests covering the gaps Cypress misses — deposit/withdrawal CSS rendering, error message display, and form state preservation on failed submissions.

To run the tests, follow the instructions below based on which part of the system you want to verify.

#### 1. Run the Cypress e2e tests
The application must be running before executing E2E tests

**Directory:** root directory

**Command:**
```bash
npm run test

# Or open the Cypress UI
npm run test:ui
```


#### 2. Run the integration tests

**Directory:** app-sanic

**Command:**
```bash
cd app-sanic
source ../venv/bin/activate
python -m pytest -v
```


#### 3. Run the component/UX tests

**Directory:** app-react

**Command:**
```bash
cd app-react
npm run test
```

#### Backend Tests — pytest 

| #   | Test                      | What it proves                                               | Layer                |
| --- | ------------------------- | ------------------------------------------------------------ | -------------------- |
| 1   | create + read             | Round-trip works: POST → GET returns the same data           | Service              |
| 2   | missing account_id        | BadRequestError (400) thrown on missing input                | Service              |
| 3   | missing amount            | BadRequestError (400) thrown when amount=None                | Service              |
| 4   | unknown transaction       | NotFoundError (404) thrown for unknown ID                    | Service              |
| 5   | unknown account           | NotFoundError (404) thrown for unknown account               | Service              |
| 6   | balance +10, -3 = 7       | Denormalized balance computes correctly                      | Service + Repository |
| 7   | negative balance          | Negative balances are allowed (no business rule blocks them) | Service              |
| 8   | duplicate idempotency_key | Same key → same transaction_id, no double-charge             | UoW + Repository     |
| 9   | NULL keys independent     | UNIQUE allows multiple NULLs (SQL standard)                  | Repository           |
| 10  | LIMIT 50                  | Pagination: 60 inserts → GET returns max 50                  | Repository           |
| 11  | filter by account         | ?account_id=X filters correctly                              | Repository           |
| 12  | UoW COMMIT                | Data persists after successful async with                    | UoW                  |
| 13  | UoW ROLLBACK              | Data discarded when exception is raised inside UoW           | UoW                  |
| 14  | 50 concurrent inserts     | BEGIN EXCLUSIVE prevents race conditions (balance = 5000)    | UoW + Service        |

#### Frontend Test — Vitest

| #   | Test                        | What it proves                                                | Component       |
| --- | --------------------------- | ------------------------------------------------------------- | --------------- |
| 1   | renders main layout         | App renders without crashing, both panels present             | App             |
| 2   | error message renders       | error prop displays in .error div                             | TransactionForm |
| 3   | inputs preserved on failure | Fields retain values when onSubmit returns false              | TransactionForm |
| 4   | inputs cleared on success   | Fields clear when onSubmit returns true                       | TransactionForm |
| 5   | deposit CSS class           | Positive amounts render with .deposit class                   | TransactionItem |
| 6   | withdrawal CSS class        | Negative amounts render with .withdrawal class and minus sign | TransactionItem |
