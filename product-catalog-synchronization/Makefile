.PHONY: help up down api worker frontend install-backend install-frontend

help:
	@echo "PCR Platform – common commands"
	@echo "  make up              Start Postgres + Redis + API + Worker (Docker)"
	@echo "  make down            Stop all Docker services"
	@echo "  make api             Run API locally (SQLite fallback, no Celery)"
	@echo "  make worker          Run Celery worker locally"
	@echo "  make frontend        Run Angular frontend"
	@echo "  make install-backend Install Python deps"
	@echo "  make install-frontend Install npm deps"

up:
	cd docker && docker compose up -d --build

down:
	cd docker && docker compose down

api:
	cd backend && PCR_USE_SQLITE=true PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd backend && PYTHONPATH=. celery -A app.tasks.celery_app.celery_app worker --loglevel=info --concurrency=2

frontend:
	cd frontend && npm start

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install
