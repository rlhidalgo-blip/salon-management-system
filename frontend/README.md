# Frontend development

From `frontend/`, run `npm install`, `npm run dev`, and open
`http://127.0.0.1:5173`. Run `npm run build` to verify the production bundle.

The login screen is a frontend-only preview in Sprint 3C. Sign In validates
required fields but does not call the API or create a session yet.

The Vite development server proxies relative `/api/v1/...` requests to
`http://127.0.0.1:8000`. Run FastAPI with `AUTH_COOKIE_MODE=localhost` and
`AUTH_ALLOWED_ORIGIN=http://127.0.0.1:5173`. The browser stays on one origin;
the backend's host-only, HttpOnly development cookie passes through the proxy.
Do not put session tokens in localStorage or sessionStorage. Future
state-changing requests must include the backend-required CSRF header.
