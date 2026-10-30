FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app/ ./app/
RUN pip install --no-cache-dir .
COPY --from=frontend-build /build/frontend/dist/ /app/frontend/dist/
COPY deploy/render/start.sh /app/deploy/render/start.sh
CMD ["sh", "/app/deploy/render/start.sh"]
