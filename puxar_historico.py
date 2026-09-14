import os
import requests
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from app import (
    ai_background_classifier,
    is_valid_request,
    classify_category,
    extract_names,
    load_db,
    save_db,
    update_dashboard_data,
    format_phone_number,
    clean_sender_info,
    sanitize_str
)

load_dotenv()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "my_super_secret_key_123")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "minha_instancia")

HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json"
}

def load_contact_map():
    """Carrega lista de conversas da Evolution API para resolver LIDs -> Nomes e Telefones reais"""
    contact_map = {}
    url_chats = f"{EVOLUTION_API_URL}/chat/findChats/{INSTANCE_NAME}"
    try:
        res = requests.post(url_chats, json={}, headers=HEADERS, timeout=30)
        chats = res.json()
        if isinstance(chats, list):
            for c in chats:
                jid = c.get("remoteJid") or c.get("id") or ""
                name = c.get("name") or c.get("pushName") or ""
                if jid and name:
                    clean_id = jid.split("@")[0]
                    contact_map[jid] = {"name": name, "phone": clean_id}
                    contact_map[clean_id] = {"name": name, "phone": clean_id}
    except Exception as e:
        print(f"[WARN] Erro ao carregar mapa de contatos: {e}")
    return contact_map

def fetch_all_historical_messages(max_pages=500):
    print(f"[INFO] Iniciando varredura COMPLETA de todo o histórico do WhatsApp (até {max_pages} páginas)...")
    
    contact_map = load_contact_map()
    print(f"[INFO] Mapeados {len(contact_map)} contatos salvos da Evolution API.")

    db = load_db()
    existing_texts = {item["text"].strip() for item in db if "text" in item}

    processed_count = 0
    added_count = 0

    url_msgs = f"{EVOLUTION_API_URL}/chat/findMessages/{INSTANCE_NAME}"

    for page in range(1, max_pages + 1):
        if page % 25 == 0 or page == 1:
            print(f"[PAGE] Lendo página {page} de {max_pages} (Processados: {processed_count} | Adicionados: {added_count})...")
            
        payload = {
            "limit": 100,
            "page": page
        }
        
        try:
            res = requests.post(url_msgs, json=payload, headers=HEADERS, timeout=20)
            if res.status_code != 200:
                print(f"[WARN] Status {res.status_code} na página {page}")
                break
            
            data = res.json()
            if not isinstance(data, dict):
                print(f"[INFO] Fim da paginação na página {page}.")
                break
            msgs = data.get("messages", {}).get("records", [])
            if not msgs:
                print(f"[INFO] Nenhuma mensagem adicional na página {page}. Varredura completa finalizada!")
                break

            for msg in msgs:
                processed_count += 1
                key = msg.get("key", {})
                from_me = key.get("fromMe", False)

                if not from_me:
                    remote_jid = key.get("remoteJid", "")
                    push_name = msg.get("pushName") or ""
                    
                    sender_name, sender_phone = clean_sender_info(remote_jid, push_name, contact_map)

                    message_content = msg.get("message", {})
                    text_content = (
                        message_content.get("conversation") or
                        message_content.get("extendedTextMessage", {}).get("text") or
                        ""
                    ).strip()

                    clean_txt = sanitize_str(text_content)

                    if clean_txt and clean_txt not in existing_texts:
                        # 1. Tenta classificar via IA Gemini de pano de fundo se API Key estiver configurada
                        ai_result = ai_background_classifier(sender_name, clean_txt)

                        if ai_result:
                            if not ai_result.get("eh_relevante", True):
                                continue
                            category = ai_result.get("categoria", classify_category(clean_txt))
                            names = ai_result.get("nomes_para_oracao", extract_names(clean_txt, sender_name))
                            summary = ai_result.get("resumo", "")
                        else:
                            # 2. Filtro rigoroso de intenção e contexto
                            if not is_valid_request(clean_txt):
                                continue

                            category = classify_category(clean_txt)
                            names = extract_names(clean_txt, sender_name)
                            summary = ""

                        sub_tag = "Podcast Vencendo o Divórcio" if category == "Podcast Divórcio" else category
                        
                        if isinstance(names, list):
                            clean_names = ", ".join([sanitize_str(n) for n in names if sanitize_str(n)])
                        else:
                            clean_names = sanitize_str(names)

                        raw_ts = msg.get("messageTimestamp")
                        if raw_ts:
                            try:
                                if raw_ts > 1e11:
                                    raw_ts = raw_ts / 1000
                                msg_dt = datetime.fromtimestamp(raw_ts).strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                msg_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            msg_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        record = {
                            "id": len(db) + 1,
                            "timestamp": msg_dt,
                            "sender_number": sanitize_str(sender_phone),
                            "sender_name": sanitize_str(sender_name) or "Contato WhatsApp",
                            "text": clean_txt,
                            "names_found": clean_names if clean_names else "Nenhum nome extraído",
                            "category": category,
                            "sub_tag": sub_tag,
                            "summary": sanitize_str(summary),
                            "status": "Em Atendimento"
                        }
                        db.append(record)
                        existing_texts.add(clean_txt)
                        added_count += 1

        except Exception as e:
            print(f"[ERROR] Falha na página {page}: {e}")
            break

    print(f"\n[OK] Varredura TOTAL concluída com sucesso!")
    print(f"[STAT] Total de mensagens analisadas: {processed_count}")
    print(f"[STAT] Registros de oração/atendimento extraídos: {added_count}")
    
    # Salva o banco de dados e atualiza o Dashboard uma única vez ao final
    save_db(db)

if __name__ == "__main__":
    import sys
    pages = 500
    if len(sys.argv) > 1:
        try:
            pages = int(sys.argv[1])
        except ValueError:
            pass
    fetch_all_historical_messages(pages)
