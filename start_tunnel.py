import time
from pyngrok import ngrok
import requests
import sys

def start_tunnel():
    try:
        # Desconecta túneis existentes para evitar conflito
        ngrok.kill()
        
        # Cria o túnel na porta 8000
        # bind_tls=True garante HTTPS
        public_url = ngrok.connect(8000, bind_tls=True).public_url
        print("\n" + "="*50)
        print(" TÚNEL NGROK ATIVO! ")
        print("="*50)
        print(f"URL PÚBLICA PARA O N8N: {public_url}/gerar-pix")
        print("="*50 + "\n")
        
        # Mantém o script rodando
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nEncerrando túnel...")
        ngrok.kill()
        sys.exit(0)
    except Exception as e:
        print(f"Erro ao criar túnel: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_tunnel()
