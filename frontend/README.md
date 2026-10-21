# Frontend development

From `frontend/`, run `npm install`, `npm run dev`, and open
`http://127.0.0.1:5173`. Run `npm test` for frontend tests and `npm run build`
to verify the production bundle.

The login form calls the existing FastAPI authentication API. On load and after
login, `/me` verifies the server session. Logout sends the in-memory CSRF token
in `X-CSRF-Token`. Only an explicit theme preference goes into localStorage;
credentials and authentication tokens do not go into browser storage.

The Vite development server proxies relative `/api/v1/...` requests to
`http://127.0.0.1:8000`. Run FastAPI with `AUTH_COOKIE_MODE=localhost` and
`AUTH_ALLOWED_ORIGIN=http://127.0.0.1:5173`. The browser stays on one origin;
the backend's host-only, HttpOnly development cookie passes through the proxy.
The browser supplies the Origin header for authentication POSTs. The backend
requires its exact allowed origin; do not set this header manually in JavaScript.
For local HTTP, use `127.0.0.1` consistently and keep the backend's development
cookie mode. Production uses HTTPS and the secure `__Host-salon_session` cookie.
