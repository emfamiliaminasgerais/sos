import os
import requests
import json
import time
from app import check_prayer_request, classify_category, add_record, load_db, save_db, update_dashboard_data
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "my_super_secret_key_123")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "minha_instancia")

HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json"
}

def fetch_all_historical_messages():
    print("🔄 Iniciando varredura do histórico de mensagens da Evolution API...")
    
    # 1. Busca lista de chats/conversas
    url_chats = f"{EVOLUTION_API_URL}/chat/findChats/{INSTANCE_NAME}"
    try:
        res = requests.get(url_chats, headers=HEADERS, timeout=30)
        chats = res.json()
    except Exception as e:
        print(f"Erro ao buscar conversas: {e}")
        chats = []

    print(f"Encontradas {len(chats)} conversas no WhatsApp.")

    processed_count = 0
    added_count = 0

    db = load_db()
    existing_texts = {item["text"].strip() for item in db}

    for chat in chats:
        jid = chat.get("id") or chat.get("remoteJid")
        if not jid or "@g.us" in jid:  # Foco em mensagens individuais
            continue

        # 2. Busca mensagens da conversa
        payload = {
            "where": {
                "key": {
                    "remoteJid": jid
                }
            },
            "limit": 100
        }
        url_msgs = f"{EVOLUTION_API_URL}/chat/findMessages/{INSTANCE_NAME}"
        try:
            res_msgs = requests.post(url_msgs, json=payload, headers=HEADERS, timeout=15)
            msgs = res_msgs.json()
            if isinstance(msgs, dict) and "records" in msgs:
                msgs = msgs["records"]
            elif not isinstance(msgs, list):
                msgs = []
        except Exception:
            msgs = []

        for msg in msgs:
            processed_count += 1
            key = msg.get("key", {})
            from_me = key.get("fromMe", False)

            if not from_me:
                sender_number = jid.split("@")[0]
                push_name = msg.get("pushName") or chat.get("name") or "Contato"
                
                message_content = msg.get("message", {})
                text_content = (
                    message_content.get("conversation") or
                    message_content.get("extendedTextMessage", {}).get("text") or
                    ""
                ).strip()

                if text_content and text_content not in existing_texts:
                    is_prayer, names_found = check_prayer_request(text_content)
                    
                    # Checagem específica para Podcast Vencendo o Divórcio
                    text_lower = text_content.lower()
                    is_podcast = "podcast" in text_lower or "vencendo o divórcio" in text_lower or "vencendo o divorcio" in text_lower
                    is_casamento = "divórcio" in text_lower or "divorcio" in text_lower or "casamento" in text_lower or "separação" in text_lower

                    if is_prayer or is_podcast or is_casamento:
                        add_record(sender_number, push_name, text_content, names_found)
                        existing_texts.add(text_content)
                        added_count += 1

    print(f"\n✅ Varredura concluída!")
    print(f"📊 Mensagens analisadas: {processed_count}")
    print(f"🙏 Pedidos / Casamentos adicionados ao Painel: {added_count}")
    
    # Atualiza o arquivo do Dashboard
    update_dashboard_data(load_db())

if __name__ == "__main__":
    fetch_all_historical_messages()
