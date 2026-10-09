# Builds the Angular app, then serves it from FastAPI with Chromium for PDF export.

FROM node:22-slim AS frontend
RUN npm install -g pnpm@11
WORKDIR /frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm exec ng build --configuration production

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HIRED_DATABASE_URL=sqlite:////data/hired.db
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY backend/ ./
COPY --from=frontend /frontend/dist/hired/browser /app/frontend/dist/hired/browser
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
