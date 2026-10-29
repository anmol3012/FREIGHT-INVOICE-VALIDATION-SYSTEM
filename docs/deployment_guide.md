# Deployment Guide — Freight Invoice Validation System

This guide provides step-by-step instructions to run the project locally, inspect its architecture, and deploy it to cloud hosting platforms (**Vercel**, **Render**, **Railway**, and **Docker**).

---

## 1. How This Project Is Built

The Freight Invoice Validation System is engineered as a **modern decoupled full-stack platform** with a production multi-stage build:

```
┌────────────────────────────────────────────────────────┐
│               React 19 Operations Dashboard            │
│       (Vite + TypeScript 5.8 + Tailwind CSS)           │
└───────────────────────────┬────────────────────────────┘
                            │ REST API Calls (/api/v1)
                            ▼
┌────────────────────────────────────────────────────────┐
│                 FastAPI REST Backend                   │
│        (Python 3.12 + Pydantic v2 + SQLAlchemy 2.0)    │
├───────────────────────────┬────────────────────────────┤
│ 20-Step Freight Validator │ Duplicate Detection Engine │
├───────────────────────────┼────────────────────────────┤
│ Weight Rating Service     │ Credit Note Reconciliation │
├───────────────────────────┼────────────────────────────┤
│ Contract Selector         │ Offline Ground-Truth Eval  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                  Relational Database                   │
│         SQLite (WAL Mode) or PostgreSQL 16+            │
└────────────────────────────────────────────────────────┘
```

### Self-Contained Unified Serving
- When `frontend/` is built (`npm run build`), the compiled bundle is copied into `frontend/dist`.
- The FastAPI application at `backend/app/main.py` detects `frontend/dist` and **serves the React UI directly at `/`**.
- This enables deploying the entire system as a **single, unified service** with zero CORS setup, while still allowing the frontend to be deployed independently to CDNs like Vercel.

---

## 2. Quick Local Run (See It Running in 2 Minutes)

To see the dashboard and API in action on your machine:

### Option A: Unified Local Server (Backend + Built UI)
```bash
# 1. Activate virtual environment
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 2. Seed starter dataset (if not already seeded)
python -m backend.app.cli seed --scale starter --seed 20261022

# 3. Start unified server
python -m backend.app.cli serve --host 127.0.0.1 --port 8000
```
- Open **Dashboard UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Open **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Option B: Frontend Hot-Reloading Development Mode
```bash
# Terminal 1 (Backend):
python -m backend.app.cli serve --host 127.0.0.1 --port 8000

# Terminal 2 (Frontend):
cd frontend
npm run dev
```
- Open **Vite Dev Dashboard**: [http://localhost:5173](http://localhost:5173)

---

## 3. Deployment Strategy Overview

| Platform | Best For | Architecture | Database | Cost |
|---|---|---|---|---|
| **Render.com** *(Recommended)* | Unified Full-Stack | Single Docker container (React + FastAPI) | Persistent Disk SQLite or Hosted PostgreSQL | Free tier available |
| **Railway.app** | Unified Full-Stack | Single Docker container | Volume SQLite or PostgreSQL plugin | \$5 free credit |
| **Vercel + Render** | High-Traffic Global CDN | Frontend on Vercel CDN, Backend on Render | Managed Database | Free tier on both |
| **Google Cloud Run / AWS ECS** | Enterprise Scale | Containerized Serverless | Cloud SQL PostgreSQL | Pay per request |

---

## 4. Option 1: 1-Click Unified Deployment on Render.com (Recommended)

Render can build and run the multi-stage `Dockerfile` directly from your GitHub repository.

### Step-by-Step Instructions:
1. Push your repository to GitHub:
   ```bash
   git push origin main
   ```
2. Go to [https://render.com](https://render.com) and sign in.
3. Click **New +** $\to$ **Web Service**.
4. Select **Build and deploy from a Git repository** and pick your `FREIGHT-INVOICE-VALIDATION-SYSTEM` repo.
5. In the configuration page:
   - **Name**: `freight-validation-system`
   - **Region**: Choose closest to you (e.g., Oregon, Frankfurt).
   - **Runtime**: **Docker** (Render will automatically detect the root `Dockerfile`).
   - **Instance Type**: **Free** (or Starter \$7/mo for persistent storage).
6. Under **Advanced / Environment Variables**, add:
   - `ENVIRONMENT`: `production`
   - `DATABASE_URL`: `sqlite:///data/freight_validation.db`
   - `DEFAULT_RANDOM_SEED`: `20261022`
7. Click **Create Web Service**.

> Render will build the React bundle, install Python 3.12 dependencies, and launch FastAPI. Within 3 minutes, you will receive a live HTTPS URL (e.g., `https://freight-validation-system.onrender.com`) serving both the interactive dashboard and `/docs`.

---

## 5. Option 2: Deploying on Vercel (Frontend) + Render/Railway (Backend)

Because Vercel is a serverless platform with read-only/ephemeral storage, SQLite databases cannot persist between serverless function invocations. The standard enterprise pattern is to host the React UI on Vercel's global CDN and connect it to a persistent backend.

### Part A: Deploy the Backend (on Render or Railway)
1. Deploy the backend on Render (as in Section 4 above) or Railway.
2. Note your backend URL (e.g., `https://freight-backend.onrender.com`).

### Part B: Deploy the Frontend to Vercel
1. Go to [https://vercel.com](https://vercel.com) and log in.
2. Click **Add New...** $\to$ **Project**.
3. Import your GitHub repository (`FREIGHT-INVOICE-VALIDATION-SYSTEM`).
4. In the project configuration:
   - **Framework Preset**: **Vite**
   - **Root Directory**: Click edit and select `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
5. Under **Environment Variables**, add:
   - `VITE_API_BASE_URL`: `https://freight-backend.onrender.com/api` *(replace with your actual backend URL)*
6. Click **Deploy**.

> Vercel will build and publish your React 19 dashboard on global edge servers with a custom `*.vercel.app` domain. The `frontend/vercel.json` file automatically handles single-page application client-side route rewrites.

---

## 6. Option 3: Local or VPS Deployment with Docker Compose

To deploy locally or on any cloud Virtual Private Server (Ubuntu/Debian on DigitalOcean, Linode, AWS EC2, or Hetzner):

```bash
# 1. Clone repository
git clone https://github.com/anmol3012/FREIGHT-INVOICE-VALIDATION-SYSTEM.git
cd FREIGHT-INVOICE-VALIDATION-SYSTEM

# 2. Build and launch container in detached mode
docker-compose up -d --build

# 3. Check logs
docker-compose logs -f
```

- Access Dashboard: `http://<your-server-ip>:8000`
- Access Swagger Docs: `http://<your-server-ip>:8000/docs`
- Stop container: `docker-compose down`
