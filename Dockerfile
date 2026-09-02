# Single-service image: builds the dashboard, then serves it from FastAPI so the
# whole demo is one container behind one URL.

FROM node:20-slim AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Install Python deps first so the layer caches across code changes.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY ml/ ml/
COPY data/ data/
COPY --from=ui /ui/dist frontend/dist

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    NAC_MODE=mock \
    AGENT_MODE=rule

EXPOSE 8000
# Hosts inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
