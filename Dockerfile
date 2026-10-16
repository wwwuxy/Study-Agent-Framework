FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /workspace
COPY backend ./backend
RUN pip install --no-cache-dir -r backend/requirements.lock && pip install --no-cache-dir --no-deps ./backend
COPY --from=web /web/dist ./frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
