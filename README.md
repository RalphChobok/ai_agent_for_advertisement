# AI Agent For Advertisement

A local web application for turning a client reference pack into ad ideas, scripts, quality reviews, exports, and audio.

## What The App Does

1. Upload a client reference pack.
2. Extract client, offer, audience, proof, and brand rules.
3. Generate ad ideas.
4. Approve or reject ideas.
5. Generate scripts for approved ideas.
6. Review scripts and export the passing ones.

## Requirements

- Python 3.10+
- Node.js and npm
- Docker
- Docker Compose

## 1. Create The Environment File

Create `backend/.env` and fill it like this.

Do not commit real API keys.

```env
GEMINI_API_KEY=your_gemini_api_key_here
MODEL_NAME=gemini-2.5-flash

# OpenAI (used for embeddings: text-embedding-3-small)
OPENAI_API_KEY=your_openai_api_key_here

# ElevenLabs (optional / experimental)
# ELEVENLABS_API_KEY=your_old_elevenlabs_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Embedding dedup threshold (0.0-1.0, cosine similarity)
DEDUP_SIMILARITY_THRESHOLD=0.75

# PostgreSQL
POSTGRES_USER=app_user
POSTGRES_PASSWORD=app_password
POSTGRES_DB=app_db
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379
```

## 2. Install Backend Requirements

From the `backend` directory:

```bash
cd backend
pip install -r requirements.txt
```

## 3. Start Docker Services

From the root directory:

```bash
docker compose --env-file backend/.env up -d
```

This starts PostgreSQL and Redis.

## 4. Create The Database Tables

From the migrations directory:

```bash
cd backend/migrations
python run_migrations.py
```

## 5. Run The Backend

From the `backend` directory:

```bash
cd backend
uvicorn main:app --reload
```

The backend runs on:

```text
http://localhost:8000
```

## 6. Run The Background Worker

From the `backend` directory:

```bash
cd backend
celery -A worker.celery_app worker --loglevel=info
```

This is needed for script generation after ideas are approved.

## 7. Install And Run The Frontend

From the `frontend` directory:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on the URL shown by Vite, usually:

```text
http://localhost:5173
```

## Normal Startup Order

Use this order when running the app locally:

1. Fill `backend/.env`.
2. Install backend requirements.
3. Start Docker.
4. Run migrations.
5. Start the backend.
6. Start the Celery worker.
7. Start the frontend.

## Useful Commands

Start Docker:

```bash
docker compose --env-file backend/.env up -d
```

Stop Docker:

```bash
docker compose --env-file backend/.env down
```

Run backend:

```bash
cd backend
uvicorn main:app --reload
```

Run migrations:

```bash
cd backend/migrations
python run_migrations.py
```

Run frontend:

```bash
cd frontend
npm run dev
```

Run worker:

```bash
cd backend
celery -A worker.celery_app worker --loglevel=info
```
