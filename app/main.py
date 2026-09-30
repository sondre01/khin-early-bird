import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.scheduler import scheduler_instance
from app.config import PROJECT_ROOT, APP_HOST, APP_PORT, AUTO_RUN_ON_STARTUP
from app.web.routes import router as web_router
from app.pipeline.orchestrator import PipelineOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("early_bird")

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "web" / "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Initializing Khin Early Bird database...")
    init_db()
    
    if not os.getenv("VERCEL"):
        logger.info("Starting background daily automation scheduler...")
        scheduler_instance.start()
    
    if AUTO_RUN_ON_STARTUP and not os.getenv("VERCEL"):
        logger.info("AUTO_RUN_ON_STARTUP is enabled - triggering initial ingestion run...")
        orch = PipelineOrchestrator()
        orch.run(limit_per_keyword=2, send_email=False)
        
    yield
    
    # Shutdown actions
    if not os.getenv("VERCEL"):
        logger.info("Stopping scheduler...")
        scheduler_instance.stop()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Khin Early Bird",
    description="Automated multi-source job extraction & AI qualification validation system for Khin Andrei Gamboa",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for VS Code Live Server (port 5500) and other origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = PROJECT_ROOT / "app" / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/app/web/static", StaticFiles(directory=str(static_dir)), name="app_web_static")

# Include API & Web routes
app.include_router(web_router)

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
