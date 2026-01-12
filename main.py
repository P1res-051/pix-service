from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pix_service import gerar_pix_playwright, setup_browser, shutdown_browser
from contextlib import asynccontextmanager
import uvicorn
import logging
import os
import asyncio

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Garante que a pasta de debug existe
os.makedirs("debug", exist_ok=True)

# Limite de concorrência (ajustar conforme RAM da VPS)
# 5 workers simultâneos = ~500MB RAM (seguro para VPS 2GB+)
CONCURRENCY_LIMIT = 5
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Iniciando servidor e navegador...")
    await setup_browser()
    yield
    # Shutdown
    logger.info("Desligando servidor e navegador...")
    await shutdown_browser()

app = FastAPI(
    title="Gerador Pix Service", 
    description="API para gerar Pix Copia e Cola via automação",
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

class PixRequest(BaseModel):
    link: str
    email: str = "teste@gmail.com"

class PixResponse(BaseModel):
    success: bool
    pix: str | None = None
    error: str | None = None

@app.post("/gerar-pix", response_model=PixResponse)
async def gerar_pix_endpoint(request: PixRequest):
    logger.info(f"Recebendo pedido: {request.link} | {request.email}")
    
    # Usa o semáforo para limitar execuções simultâneas e evitar crash da VPS
    if semaphore.locked():
        logger.warning("Servidor ocupado. Aguardando vaga na fila...")
        
    async with semaphore:
        try:
            # Chama o serviço Playwright
            pix_code = await gerar_pix_playwright(request.link, request.email)
            
            if pix_code:
                return PixResponse(success=True, pix=pix_code)
            else:
                return PixResponse(success=False, error="PIX_NOT_FOUND")
                
        except Exception as e:
            logger.error(f"Erro interno: {e}")
            return PixResponse(success=False, error=str(e))

@app.get("/")
def read_root():
    return {"message": "Serviço Gerador Pix está rodando! Use POST /gerar-pix para gerar códigos."}

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    # Pega a porta da variável de ambiente (obrigatório para Render/Heroku)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
