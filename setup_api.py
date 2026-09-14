import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
API_KEY = os.getenv("EVOLUTION_API_KEY", "my_super_secret_key_123")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "minha_instancia")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://host.docker.internal:5000/webhook")

headers = {
    "apikey": API_KEY,
    "Content-Type": "application/json"
}

def setup():
    print(f"1. Criando/Verificando instância '{INSTANCE_NAME}'...")
    create_payload = {
        "instanceName": INSTANCE_NAME,
        "token": API_KEY,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS"
    }
    res = requests.post(f"{API_URL}/instance/create", json=create_payload, headers=headers)
    print("Resposta Instância:", res.text)

    print(f"2. Configurando Webhook para '{WEBHOOK_URL}'...")
    webhook_payload = {
        "webhook": {
            "enabled": True,
            "url": WEBHOOK_URL,
            "webhook_by_events": False,
            "events": ["MESSAGES_UPSERT"]
        }
    }
    res = requests.post(f"{API_URL}/webhook/set/{INSTANCE_NAME}", json=webhook_payload, headers=headers)
    print("Resposta Webhook:", res.text)

if __name__ == "__main__":
    setup()
