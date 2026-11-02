# Shop365

A fresh marketplace MVP with a React 18 + Vite frontend, FastAPI + SQLite backend, and a Groq-powered LangGraph assistant.

## Architecture

```text
React 18 + Vite (frontend/)
        │ same-origin API requests
        ▼
FastAPI (app/main.py) ── SQLite (data/shop365.db)
        │
        └── LangGraph assistant
              ├── Groq chat model
              ├── read-only catalog, category, order, and seller tools
              ├── 3-turn in-memory conversation window
              └── bounded model retries, timeouts, and graph steps
```

The assistant's tools only read marketplace data. It cannot place or cancel orders. The shopper confirms a demo purchase through the regular checkout API.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer
- A Groq API key to enable AI chat (the marketplace works without one)

## Windows setup

Open PowerShell in this `Shop365` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Set `SECRET_KEY` in `.env` to a long random value if one is not already set. To enable the assistant, add your own `GROQ_API_KEY` to `.env`; do not share or commit it. Install dependencies and build the frontend:

```powershell
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000`. FastAPI serves the production React build and API from one origin. API documentation is at `http://127.0.0.1:8000/docs`.

For frontend development, run FastAPI in one terminal and `npm run dev` from `frontend` in another. Vite proxies `/api` requests to FastAPI on port 8000.

The SQLite database is created on first startup at `data/shop365.db`. The seed catalog is inserted only when its demo seller is absent.

## LangGraph resilience

- `search_products` and `list_categories` are available without signing in.
- `get_my_orders` and `get_my_sales` are only added to the graph for the authenticated user; guest accounts cannot access seller-sales tools.
- Tool functions are read-only and use parameterized SQL with a five-result limit.
- Model requests time out after 20 seconds and retry up to three total attempts with exponential jitter. The default Groq model is `openai/gpt-oss-20b`, which supports tool calling; set `GROQ_MODEL` to another tool-capable model available to your Groq account if needed.
- LangGraph has a recursion limit of eight steps. Tool failures become an explicit tool response for the model to explain.
- The in-memory checkpoint keeps only the latest three user turns per conversation. Conversation memory is scoped to the current user and resets when the server restarts.
- API failures return a clear `502`; missing Groq configuration returns `503`. No fallback response claims an AI request succeeded.

## Marketplace features

- Browse, search, and filter available Diwali products.
- Continue as a guest or register/sign in.
- Keep a local shopping bag and place a demo order; inventory is checked and decremented transactionally.
- Create seller listings and view order or sales history.
- Ask the optional assistant about live catalog and account data.

Checkout is a simulation. No payment is collected.

## Tests

From the project folder:

```powershell
pytest
```

## Production notes

This is a demo application, not a production commerce deployment. Before production, add HTTPS, secure HttpOnly sessions, CSRF defenses, rate limiting, email verification, password recovery, database migrations, monitoring, backups, and a real payment provider with verified webhooks.
