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
#
# The LOCK file, not requirements.txt. The committed .pkl models were written by
# scikit-learn 1.9.0, and requirements.txt is all `>=` ranges that re-resolve on every
# rebuild. An unpickle against a different scikit-learn does not crash the container —
# ml/client.py and ml/forecast.py catch it, log at WARNING and fall back to the rule
# classifier and "forecasting unavailable". The demo comes up looking healthy with its
# whole ML story quietly switched off. Check the `ML` chip reads "trained" after any
# rebuild.
COPY backend/requirements.lock.txt backend/requirements.lock.txt
RUN pip install --no-cache-dir -r backend/requirements.lock.txt

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
#
# --forwarded-allow-ips is not optional here. Render terminates TLS at its edge and
# forwards plain HTTP, so without it uvicorn ignores X-Forwarded-Proto and every
# request looks like http:// to the app — which meant request.base_url handed the
# CAMARA operator an http sink for an https service. "*" trusts the proxy headers on
# every peer, which is correct only because nothing but Render's edge can reach this
# container; do not carry that flag to a directly-exposed deployment.
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --forwarded-allow-ips '*'"]
