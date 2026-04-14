git init
git remote add origin https://github.com/sushant-mutnale/Meduim_AI_Agent.git
git branch -m main

# Commit 1
git add README.md requirements.txt .env.example .gitignore .dockerignore
git commit -m "chore: initialize project structure and dependencies"

# Commit 2
git add docker/ docker-compose.yml
git commit -m "build: configure containerized environment with Docker"

# Commit 3
git add app/__init__.py app/core/__init__.py app/core/config.py app/db/__init__.py app/db/session.py app/db/models.py
git commit -m "feat(db): establish core configuration and PostgreSQL models"

# Commit 4
git add app/core/celery_app.py app/main.py
git commit -m "feat(api): bootstrap FastAPI and Celery worker setup"

# Commit 5
git add app/services/__init__.py app/services/interfaces.py app/services/medium.py
git commit -m "feat(services): define strict tool contracts and MCP boundaries"

# Commit 6
git add app/services/trends.py app/services/research.py
git commit -m "feat(services): implement live aiohttp network fetchers for trends"

# Commit 7
git add app/utils/__init__.py app/utils/llm.py
git commit -m "feat(utils): robust OpenRouter LLM extraction service"

# Commit 8
git add app/agents/__init__.py app/agents/cpu_tasks.py app/agents/visuals.py app/agents/agents.py
git commit -m "feat(agents): scikit-learn TF-IDF clustering and CPU heuristics"

# Commit 9
git add app/jobs/__init__.py app/jobs/graph_nodes.py app/jobs/graph.py app/jobs/pipeline_job.py
git commit -m "feat(orchestrator): implement strict LangGraph architecture"

# Commit 10
git add dashboard/
git commit -m "feat(ui): bootstrap Next.js monitoring dashboard"

git push -u origin main --force
