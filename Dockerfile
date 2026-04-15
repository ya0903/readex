FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Install Playwright dependencies (needed for JS-rendered source adapters)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/data

EXPOSE 3100

WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3100"]
