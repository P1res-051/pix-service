import asyncio
import re
import logging
from playwright.async_api import async_playwright, Page

# Configuração de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def gerar_pix_playwright(url_link: str, email_cliente: str = "teste@gmail.com"):
    """
    Acessa o link de pagamento usando Playwright, preenche email e retorna o Pix Copia e Cola.
    """
    async with async_playwright() as p:
        # Lança o navegador (headless=True para rodar em background)
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            permissions=["clipboard-read", "clipboard-write"]
        )
        page = await context.new_page()
        
        pix_code = None

        try:
            # Aumenta viewport para evitar que elementos fiquem escondidos
            await page.set_viewport_size({"width": 1280, "height": 1024})
            
            logger.info(f"Acessando URL: {url_link}")
            # Timeout de navegação de 60s
            await page.goto(url_link, timeout=60000, wait_until="networkidle")

            # --- PASSO 1: Selecionar PIX ---
            logger.info("Procurando opção PIX...")
            
            # Força o clique no texto "Pix" com seletor mais genérico e JS
            # O Mercado Pago às vezes renderiza Pix dentro de radio buttons ou divs clicáveis
            try:
                # Estratégia Agressiva: Tenta encontrar qualquer coisa escrita Pix e clica via JS direto
                # Isso ignora se o elemento está "coberto" ou "invisível"
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

            await asyncio.sleep(3) # Espera a UI reagir

            # --- PASSO 2: Preencher Email ---
            logger.info("Verificando campo de email...")
            
            # Tenta preencher qualquer campo de email que aparecer, mesmo escondido
            try:
                 # Injeta JS para achar o campo de email e preencher 'na força'
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
                     # Tenta via Playwright normal
                     email_input = page.locator("input[type='email']").or_(page.locator("#user-email-input"))
                     if await email_input.count() > 0:
                        await email_input.first.fill(email_cliente)
                        await email_input.first.press("Enter")
                        logger.info("Email preenchido via Locator.")
                     else:
                        logger.info("Campo de email não encontrado (pode ser opcional).")
            except Exception as e:
                logger.warning(f"Erro no preenchimento de email: {e}")

            await asyncio.sleep(2)

            # --- PASSO 3: Confirmar Pagamento ---
            logger.info("Procurando botão de pagar...")
            
            # Tenta clicar em qualquer botão de submit ou que pareça de confirmação
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
            
            # Aumenta timeout e melhora a busca
            for i in range(20):
                # 1. Busca em inputs/textareas (Value ou Text)
                inputs = await page.locator("input, textarea").all()
                for inp in inputs:
                    try:
                        val = await inp.get_attribute("value")
                        if val and "000201" in val:
                            pix_code = val
                            break
                        txt = await inp.inner_text()
                        if txt and "000201" in txt:
                            pix_code = txt
                            break
                    except:
                        continue
                
                if pix_code:
                    break
                
                # 2. Busca no clipboard (Click no botão de copiar)
                try:
                    # Botão de copiar comum no MP
                    copy_btn = page.locator("span:has-text('Copiar código')").or_(
                        page.locator("button:has-text('Copiar código')")
                    ).or_(
                        page.locator(".clipboard-copy")
                    )
                    
                    if await copy_btn.first.is_visible():
                        await copy_btn.first.click()
                        await asyncio.sleep(0.5)
                        # Lê do clipboard
                        clipboard_content = await page.evaluate("navigator.clipboard.readText()")
                        if clipboard_content and "000201" in clipboard_content:
                            pix_code = clipboard_content
                            logger.info("Pix obtido via Clipboard!")
                            break
                except Exception as e:
                    logger.warning(f"Erro ao tentar ler clipboard: {e}")

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
                
                logger.info(f"Tentativa {i+1}/20 de encontrar Pix...")
                await asyncio.sleep(2)
            
            if pix_code:
                # Limpeza final do código Pix (remover sufixos indesejados se vier do HTML)
                # O padrão BR Code sempre termina antes de tags HTML
                pix_code = pix_code.split("<")[0].strip()
                logger.info("Código Pix encontrado!")
                return pix_code
            else:
                logger.error("Pix não encontrado após tentativas.")
                # Tira screenshot para debug
                await page.screenshot(path="debug_error.png")
                return None

        except Exception as e:
            logger.error(f"Erro no Playwright: {e}")
            await page.screenshot(path="debug_fatal.png")
            return None
        finally:
            await browser.close()

if __name__ == "__main__":
    # Teste local
    link = "https://pagueaqui.top/Y2xpZW50XzQ0NzYy"
    loop = asyncio.get_event_loop()
    codigo = loop.run_until_complete(gerar_pix_playwright(link))
    print(f"Código: {codigo}")
