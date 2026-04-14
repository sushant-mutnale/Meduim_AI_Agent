# AI Content Automation Platform

An end-to-end multi-agent platform that autonomously researches, drafts, and publishes high-quality technical articles to Medium.

## Features
- **Idempotent 2-Day Cadence**: Powered by Celery Beat to automatically execute.
- **Agentic Workflow**: 10 distinct agents pipeline data from raw internet queries into ranked, outlined, and reviewed drafts.
- **Medium Integration**: Automated publishing with metadata mapping.
- **Fail-safes**: Configurable confidence thresholds to prevent poor output from reaching the public.
- **Admin Dashboard**: Next.js-powered oversight console.

## Architecture
- **Backend API**: FastAPI + Python 3.11
- **Database**: PostgreSQL (SQLAlchemy)
- **Queue/Broker**: Redis + Celery
- **Frontend**: Next.js (Admin Dashboard)

## Getting Started
1. Run `cp .env.example .env` and populate keys (OpenAI, Medium).
2. Start the suite via `docker-compose up --build`.
3. View API at `http://localhost:8000/docs`.
4. View dashboard at `http://localhost:3000`.

## Modules
- `app.agents.*`: LLM wrappers that process topic candidates, abstracts, outlines and write drafts.
- `app.services.*`: Third-party integration clients (Medium API, Reddit, News, etc).
- `app.jobs.*`: Celery tasks managing pipeline execution.
