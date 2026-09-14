import requests
import os
import time
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
        
        base64_qr = data.get("base64") or data.get("code")
        if response.status_code == 200 and base64_qr:
            if "," in base64_qr:
                base64_qr = base64_qr.split(",")[1]
            
            update_qr_html(base64_qr)
            print("[OK] QR Code atualizado com sucesso em qr.html!")
        elif data.get("instance", {}).get("state") == "open" or data.get("status") == "CONNECTED" or data.get("state") == "open":
            print("[OK] A instancia ja esta CONECTADA ao WhatsApp!")
            return True
        else:
            print("Resposta da Evolution API:", data)
            return False
    except Exception as e:
        print(f"Erro ao buscar QR Code: {e}")
        return False

def update_qr_html(base64_qr):
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Conectar Novo WhatsApp - QR Code</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body {{ font-family: sans-serif; text-align: center; padding: 40px; background-color: #0b132b; color: #ffffff; }}
        .qr-container {{ margin-top: 20px; }}
        img {{ border: 4px solid #25D366; padding: 12px; border-radius: 16px; background: white; max-width: 300px; }}
        .card {{ background: #1c2541; padding: 30px; border-radius: 12px; display: inline-block; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }}
        h1 {{ color: #25D366; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>📲 Conectar WhatsApp</h1>
        <p><b>Instância:</b> {INSTANCE_NAME}</p>
        <p>Abra o WhatsApp no celular &gt; <b>Aparelhos Conectados</b> &gt; <b>Conectar Aparelho</b></p>
        <div class="qr-container">
            <img src="data:image/png;base64,{base64_qr}" alt="WhatsApp QR Code">
        </div>
        <p><small style="color: #94a3b8;">🔄 Atualizado automaticamente. Mantenha esta aba aberta ao escanear.</small></p>
    </div>
</body>
</html>"""
    with open("qr.html", "w", encoding="utf-8") as f:
        f.write(html_content)

if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv or "-l" in sys.argv:
        print("Starting QR auto-refresh loop (press Ctrl+C to stop)...")
        while True:
            is_connected = get_qr()
            if is_connected:
                print("WhatsApp conectado com sucesso!")
                break
            time.sleep(8)
    else:
        get_qr()

