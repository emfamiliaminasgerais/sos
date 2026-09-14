import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
API_KEY = os.getenv("EVOLUTION_API_KEY", "my_super_secret_key_123")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "minha_instancia")

headers = {
    "apikey": API_KEY
}

def get_qr():
    print(f"Buscando QR Code para a instância: {INSTANCE_NAME}...")
    try:
        response = requests.get(f"{API_URL}/instance/connect/{INSTANCE_NAME}", headers=headers)
        data = response.json()
        
        if response.status_code == 200 and "base64" in data:
            base64_qr = data["base64"]
            if "," in base64_qr:
                base64_qr = base64_qr.split(",")[1]
            
            update_qr_html(base64_qr)
            print("QR Code atualizado em qr.html. Abra o arquivo no navegador.")
        elif data.get("instance", {}).get("state") == "open" or data.get("status") == "CONNECTED":
            print("A instância já está conectada ao WhatsApp!")
        else:
            print("Resposta da Evolution API:", data)
    except Exception as e:
        print(f"Erro ao buscar QR Code: {e}")

def update_qr_html(base64_qr):
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Conectar Novo WhatsApp - QR Code</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body {{ font-family: sans-serif; text-align: center; padding: 50px; background-color: #f4f4f9; color: #333; }}
        .qr-container {{ margin-top: 20px; }}
        img {{ border: 2px solid #25D366; padding: 10px; border-radius: 12px; background: white; }}
    </style>
</head>
<body>
    <h1>Conectar WhatsApp (Evolution API)</h1>
    <p>Escaneie o QR Code com o seu novo número do WhatsApp</p>
    <p><b>Instância:</b> {INSTANCE_NAME}</p>
    <div class="qr-container">
        <img src="data:image/png;base64,{base64_qr}" alt="WhatsApp QR Code">
    </div>
    <p><small>Atualiza automaticamente a cada 10 segundos</small></p>
</body>
</html>"""
    with open("qr.html", "w", encoding="utf-8") as f:
        f.write(html_content)

if __name__ == "__main__":
    get_qr()
