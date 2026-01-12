import asyncio
import re
import logging
from playwright.async_api import async_playwright, Browser, Playwright

# Configuração de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Globais para reutilização do navegador
PLAYWRIGHT_INSTANCE: Playwright = None
BROWSER_INSTANCE: Browser = None
BROWSER_LOCK = asyncio.Lock()

async def setup_browser():
    """Inicializa o navegador globalmente."""
    global PLAYWRIGHT_INSTANCE, BROWSER_INSTANCE
    async with BROWSER_LOCK:
        if BROWSER_INSTANCE is None:
            logger.info("Inicializando navegador global...")
            PLAYWRIGHT_INSTANCE = await async_playwright().start()
            BROWSER_INSTANCE = await PLAYWRIGHT_INSTANCE.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage" # Importante para Docker/VPS com pouca RAM
                ]
            )
            logger.info("Navegador global inicializado com sucesso.")

async def shutdown_browser():
    """Fecha o navegador global."""
    global PLAYWRIGHT_INSTANCE, BROWSER_INSTANCE
    async with BROWSER_LOCK:
        if BROWSER_INSTANCE:
            await BROWSER_INSTANCE.close()
            BROWSER_INSTANCE = None
        if PLAYWRIGHT_INSTANCE:
            await PLAYWRIGHT_INSTANCE.stop()
            PLAYWRIGHT_INSTANCE = None
        logger.info("Navegador global encerrado.")

async def get_browser():
    """Retorna a instância do navegador, recriando se necessário."""
    global BROWSER_INSTANCE
    if BROWSER_INSTANCE is None or not BROWSER_INSTANCE.is_connected():
        logger.warning("Navegador desconectado ou não iniciado. Tentando reconectar...")
        await setup_browser()
    return BROWSER_INSTANCE

async def gerar_pix_playwright(url_link: str, email_cliente: str = "teste@gmail.com"):
    """
    Acessa o link de pagamento usando Playwright (contexto isolado), preenche email e retorna o Pix Copia e Cola.
    Tenta até 3 vezes em caso de erro.
    """
    MAX_RETRIES = 3
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"--- Tentativa {attempt + 1}/{MAX_RETRIES} para {url_link} ---")
            
            browser = await get_browser()
            if not browser:
                logger.error("Falha fatal: Não foi possível obter instância do navegador.")
                return None

            # Cria contexto isolado (leve e rápido)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                permissions=["clipboard-read", "clipboard-write"],
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1,
                ignore_https_errors=True,
                java_script_enabled=True,
                locale="pt-BR"
            )
            
            # Bloqueia recursos inúteis para economizar dados/RAM
            await context.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff,woff2}", lambda route: route.abort())
            
            page = await context.new_page()
            pix_code = None

            try:
                # --- ESTRATÉGIA DE REDE: Interceptar resposta JSON com Pix ---
                pix_code_network = []
                
                async def handle_response(response):
                    try:
                        if response.request.method == "POST" and ("000201" in response.url or "json" in response.headers.get("content-type", "")):
                            try:
                                json_data = await response.json()
                                dump = str(json_data)
                                if "000201" in dump:
                                    match = re.search(r"(000201[a-zA-Z0-9\s\.\-\*@:]+)", dump)
                                    if match:
                                        candidate = match.group(1).replace(" ", "").replace("\n", "")
                                        if len(candidate) > 50:
                                            pix_code_network.append(candidate)
                                            logger.info("Pix capturado via Network Response!")
                            except:
                                pass
                    except:
                        pass
                
                page.on("response", handle_response)
                
                logger.info(f"Acessando URL: {url_link}")
                # Timeout de navegação de 40s
                try:
                    await page.goto(url_link, timeout=40000, wait_until="domcontentloaded")
                except Exception as e:
                    logger.warning(f"Timeout ou erro ao carregar página: {e}")
                    # Continua mesmo se der timeout, pois elementos podem já estar lá

                # --- PASSO 1: Selecionar PIX ---
                logger.info("Procurando opção PIX...")
                
                try:
                    # Estratégia Agressiva: Tenta encontrar qualquer coisa escrita Pix e clica via JS direto
                    found_pix = await page.evaluate("""
                        () => {
                            const elements = [...document.querySelectorAll('span, div, label, p')];
                            const pixEl = elements.find(el => el.innerText.includes('Pix') && el.innerText.length < 20);
                            if (pixEl) {
                                pixEl.click();
                                return true;
                            }
                            return false;
                        }
                    """)
                    
                    if found_pix:
                        logger.info("Clicado em 'Pix' via JS (busca textual).")
                    else:
                        # Tenta via localizadores normais se o JS falhar
                        pix_element = page.locator("text=Pix").first
                        if await pix_element.count() > 0:
                            await pix_element.click(force=True)
                            logger.info("Clicado em 'Pix' (locator force).")
                except Exception as e:
                    logger.warning(f"Erro ao clicar no Pix: {e}")

                await asyncio.sleep(2) # Espera a UI reagir

                # --- PASSO 2: Preencher Email ---
                logger.info("Verificando campo de email...")
                
                try:
                    # Estratégia Híbrida: Click + Type (Humano) para disparar eventos corretamente
                    email_input = page.locator("input[type='email']").or_(
                        page.locator("#user-email-input")
                    ).or_(
                        page.locator("input[placeholder*='email']")
                    ).or_(
                        page.locator("input[placeholder*='Ex.:']")
                    )
                    
                    if await email_input.count() > 0:
                        # Foca e digita como um humano
                        await email_input.first.click()
                        await asyncio.sleep(0.5)
                        await email_input.first.fill("") # Limpa
                        await page.keyboard.type(email_cliente, delay=50) # Digita com delay
                        await asyncio.sleep(0.5)
                        await page.keyboard.press("Tab") # Sai do campo para validar
                        logger.info("Email preenchido via Keyboard Type (Simulação Humana).")
                        
                        # Verificação de segurança: O erro sumiu?
                        if await page.locator("text=Preencha este campo").is_visible():
                                logger.warning("Validação de email falhou. Tentando forçar via JS...")
                                # Fallback JS Force
                                await page.evaluate(f"""
                                (email) => {{
                                    const input = document.querySelector('input[type="email"]');
                                    if (input) {{
                                        input.value = email;
                                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                                    }}
                                }}
                                """, email_cliente)
                    else:
                            # Se não achou locator, tenta JS Direto
                            logger.info("Locator de email não encontrado, tentando JS direto...")
                            email_filled = await page.evaluate(f"""
                            (email) => {{
                                const input = document.querySelector('input[type="email"]') || document.querySelector('#user-email-input');
                                if (input) {{
                                    input.value = email;
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                                return false;
                            }}
                            """, email_cliente)
                            
                            if email_filled:
                                logger.info(f"Email {email_cliente} preenchido via JS Direto.")
                                await page.keyboard.press("Enter")
                            else:
                                logger.info("Campo de email não encontrado (pode ser opcional).")
                except Exception as e:
                    logger.warning(f"Erro no preenchimento de email: {e}")

                await asyncio.sleep(2)

                # --- PASSO 3: Confirmar Pagamento ---
                logger.info("Procurando botão de pagar...")
                
                try:
                    # Estratégia JS: Busca botões "Pagar" ou "Gerar Pix" e clica sem dó
                    clicked_pay = await page.evaluate("""
                        () => {
                                const btns = [...document.querySelectorAll('button, input[type="submit"], .andes-button')];
                                const target = btns.find(b => 
                                    (b.innerText && (b.innerText.includes('Pagar') || b.innerText.includes('Gerar') || b.innerText.includes('Criar Pix'))) ||
                                    (b.value && (b.value.includes('Pagar') || b.value.includes('Gerar')))
                                );
                                if (target) {
                                    target.click();
                                    return true;
                                }
                                return false;
                        }
                    """)
                    
                    if clicked_pay:
                        logger.info("Botão de pagamento clicado via JS.")
                    else:
                        # Fallback Playwright Locator
                        submit_btn = page.locator("button[type='submit']").or_(
                            page.locator("button:has-text('Pagar')")
                        ).or_(
                            page.locator(".andes-button--loud")
                        )
                        if await submit_btn.count() > 0:
                            await submit_btn.first.click(force=True)
                            logger.info("Botão de pagamento clicado (locator).")
                            
                except Exception as e:
                    logger.warning(f"Erro ao clicar em pagar: {e}")

                # --- PASSO 4: Capturar Código Pix ---
                logger.info("Aguardando código Pix...")
                
                for i in range(25): # Aumentado para 25 tentativas
                    # 0. Checa se já pegamos via Network
                    if pix_code_network:
                        pix_code = pix_code_network[0]
                        logger.info("Pix recuperado via Network Interception!")
                        break

                    # 1. Busca em inputs/textareas (Value ou Text)
                    inputs = await page.locator("input, textarea").all()
                    for inp in inputs:
                        try:
                            if await inp.is_visible():
                                val = await inp.get_attribute("value")
                                if val and "000201" in val:
                                    pix_code = val
                                    logger.info("Pix encontrado em Input Value")
                                    break
                                txt = await inp.inner_text()
                                if txt and "000201" in txt:
                                    pix_code = txt
                                    logger.info("Pix encontrado em Input Text")
                                    break
                        except:
                            continue
                    
                    if pix_code:
                        break
                    
                    # 2. Busca no clipboard (Click no botão de copiar)
                    try:
                        # Botão de copiar comum no MP - expandido para outros seletores comuns
                        copy_btns = await page.locator("button, span, div, a").filter(has_text=re.compile(r"Copiar|Copy", re.IGNORECASE)).all()
                        
                        for btn in copy_btns:
                            if await btn.is_visible():
                                # Clica e lê
                                await btn.click()
                                await asyncio.sleep(0.5)
                                clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                                if clipboard_content and "000201" in clipboard_content:
                                    pix_code = clipboard_content
                                    logger.info("Pix obtido via Clipboard (Botão Genérico)!")
                                    break
                        if pix_code: break

                    except Exception as e:
                        pass

                    # 3. Busca no texto visível da página (inner_text é melhor que content) e em Iframes
                    try:
                        # Busca no frame principal
                        text_content = await page.inner_text("body")
                        if "000201" in text_content:
                            match = re.search(r"(000201[a-zA-Z0-9\s\.\-\*@:]+)", text_content)
                            if match:
                                candidate = match.group(1).replace(" ", "").replace("\n", "")
                                if len(candidate) > 50:
                                    pix_code = candidate
                                    logger.info("Pix encontrado no texto do body (main frame)!")
                                    break
                        
                        # Busca em todos os iframes (comum em checkouts)
                        for frame in page.frames:
                            try:
                                frame_text = await frame.inner_text("body")
                                if "000201" in frame_text:
                                    match = re.search(r"(000201[a-zA-Z0-9\s\.\-\*@:]+)", frame_text)
                                    if match:
                                        candidate = match.group(1).replace(" ", "").replace("\n", "")
                                        if len(candidate) > 50:
                                            pix_code = candidate
                                            logger.info(f"Pix encontrado no texto de um Iframe ({frame.name})!")
                                            break
                            except:
                                continue
                        if pix_code:
                            break

                    except Exception as e:
                            logger.warning(f"Erro ao buscar texto no body: {e}")
                    
                    logger.info(f"Tentativa {i+1}/25 de encontrar Pix...")
                    await asyncio.sleep(2)
                
                if pix_code:
                    # Limpeza final do código Pix
                    pix_code = pix_code.strip()
                    # Se houver sujeira HTML no final, corta
                    if "<" in pix_code:
                        pix_code = pix_code.split("<")[0]
                    # Remove aspas extras que podem vir do JSON/String
                    pix_code = pix_code.replace('"', '').replace("'", "")
                    
                    logger.info(f"Código Pix encontrado: {pix_code[:20]}...")
                    return pix_code
                else:
                    logger.error("Pix não encontrado após tentativas.")
                    # Dump do HTML para debug no log
                    try:
                        content = await page.content()
                        with open("debug/debug_dump.html", "w", encoding="utf-8") as f:
                            f.write(content)
                            
                        logger.info("--- DUMP DO CONTEÚDO DA PÁGINA (BODY) ---")
                        body_text = await page.inner_text("body")
                        logger.info(body_text[:5000]) # Loga os primeiros 5000 chars do texto visível
                        
                        # Loga iframes também
                        for frame in page.frames:
                            try:
                                if frame.name:
                                    logger.info(f"--- FRAME: {frame.name} ---")
                                    logger.info((await frame.inner_text("body"))[:1000])
                            except: pass
                            
                        logger.info("...")
                    except:
                        pass
                    
                    # Tira screenshot para debug
                    try:
                        await page.screenshot(path="debug/debug_error.png")
                    except: pass
                    
                    # Se não achou na última tentativa, retorna None
                    if attempt == MAX_RETRIES - 1:
                        return None
                    else:
                        logger.info("Reiniciando tentativa...")
                        continue

            except Exception as e:
                logger.error(f"Erro no Playwright: {e}")
                try:
                    await page.screenshot(path="debug/debug_fatal.png")
                except: pass
                
                # Se for erro fatal (ex: browser crash), reinicia o browser
                if "Target closed" in str(e) or "Connection closed" in str(e):
                     logger.critical("Detectado crash do navegador. Reiniciando serviço do browser...")
                     await shutdown_browser()
                     await setup_browser()

                if attempt == MAX_RETRIES - 1:
                    return None
            finally:
                # Fecha apenas a página e o contexto, MANTENDO o navegador aberto
                await page.close()
                await context.close()


if __name__ == "__main__":
    # Teste local precisa inicializar o navegador manualmente
    async def main():
        await setup_browser()
        link = "https://pagueaqui.top/Y2xpZW50XzQ0NzYy"
        codigo = await gerar_pix_playwright(link)
        print(f"Código: {codigo}")
        await shutdown_browser()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
