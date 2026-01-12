from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pix_service import gerar_pix_playwright, setup_browser, shutdown_browser
from contextlib import asynccontextmanager
import uvicorn
import logging
import os
import asyncio
import uuid
import time

# --- Configuração de Logs Estruturados ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("PixAPI")

# Garante que a pasta de debug existe
os.makedirs("debug", exist_ok=True)

# Limite de concorrência (Ajustado para VPS)
CONCURRENCY_LIMIT = 5
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Iniciando servidor Pix Service...")
    try:
        await setup_browser()
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: Falha ao iniciar o navegador no startup: {e}")
        logger.warning("⚠️ O serviço continuará rodando para debug, mas a geração de Pix falhará até que o navegador seja corrigido.")
    
    yield
    # Shutdown
    logger.info("🛑 Desligando servidor...")
    await shutdown_browser()

app = FastAPI(
    title="Pix Service Automation", 
    description="API robusta para geração de Pix Copia e Cola com Playwright.",
    version="2.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monta a rota para acessar arquivos de debug (screenshots)
app.mount("/debug", StaticFiles(directory="debug"), name="debug")

# --- Modelos de Dados ---
class PixRequest(BaseModel):
    link: str
    email: str = "teste@gmail.com"

class PixResponse(BaseModel):
    success: bool
    pix: str | None = None
    error: str | None = None
    request_id: str
    execution_time: float

# --- Middleware para Logging de Requisições ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(f"[{request_id}] Recebendo requisição: {request.method} {request.url}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"[{request_id}] Concluído em {process_time:.2f}s | Status: {response.status_code}")
    
    response.headers["X-Request-ID"] = request_id
    return response

# --- Rotas ---

@app.post("/gerar-pix", response_model=PixResponse)
async def gerar_pix_endpoint(request: PixRequest):
    req_id = str(uuid.uuid4()) # ID interno para rastreio
    start_time = time.time()
    
    logger.info(f"[{req_id}] Iniciando processamento para: {request.link}")
    
    # Check de concorrência
    if semaphore.locked():
        logger.warning(f"[{req_id}] Fila cheia! Aguardando slot de processamento...")
        
    async with semaphore:
        try:
            # Chama o serviço Playwright
            pix_code = await gerar_pix_playwright(request.link, request.email)
            
            elapsed = time.time() - start_time
            
            if pix_code:
                logger.info(f"[{req_id}] ✅ SUCESSO! Pix gerado em {elapsed:.2f}s")
                return PixResponse(
                    success=True, 
                    pix=pix_code, 
                    request_id=req_id,
                    execution_time=elapsed
                )
            else:
                logger.error(f"[{req_id}] ❌ ERRO: Pix não encontrado após tentativas.")
                return PixResponse(
                    success=False, 
                    error="PIX_NOT_FOUND", 
                    request_id=req_id,
                    execution_time=elapsed
                )
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"[{req_id}] 💥 ERRO CRÍTICO: {str(e)}")
            return PixResponse(
                success=False, 
                error=f"INTERNAL_ERROR: {str(e)}", 
                request_id=req_id,
                execution_time=elapsed
            )

@app.get("/")
def read_root():
    return {
        "message": "Pix Service Online",
        "docs": "/docs",
        "logs": "Acesse a porta :8888 para ver logs em tempo real",
        "monitor": "Acesse a porta :3001 para monitoramento"
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "concurrency_slots_free": semaphore._value}

@app.get("/health/browser")
async def browser_health_check():
    from pix_service import BROWSER_INSTANCE
    status = "connected" if BROWSER_INSTANCE and BROWSER_INSTANCE.is_connected() else "disconnected"
    return {"browser_status": status}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Workers configurados via uvicorn.run para dev, mas no Docker usa CMD
    uvicorn.run(app, host="0.0.0.0", port=port)
