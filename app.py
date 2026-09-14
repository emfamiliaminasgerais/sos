import os
import re
import json
import base64
import threading
import time
import subprocess
from datetime import datetime
import requests
import pandas as pd
import schedule
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# ReportLab para geração de PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES DO SISTEMA ---
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "my_super_secret_key_123")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "minha_instancia")
ADMIN_NUMBER = os.getenv("ADMIN_NUMBER", "5531992536994")  # Número de destino
DB_FILE = "pedidos_oracao.json"

HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json"
}

# --- CLASSIFICAÇÃO INTELIGENTE DE CATEGORIAS ---
def classify_category(text):
    text_lower = text.lower()
    
    # 1. Subitem: Podcast Vencendo o Divórcio
    if any(w in text_lower for w in ["podcast", "vencendo o divórcio", "vencendo o divorcio"]):
        return "Podcast Divórcio"

    # 2. Saúde & Cura
    if any(w in text_lower for w in ["saúde", "saude", "doença", "doenca", "hospital", "cirurgia", "cura", "médico", "medico", "câncer", "cancer", "dor", "exame", "remédio", "internado", "leito"]):
        return "Saúde"
        
    # 3. Financeiro & Trabalho
    if any(w in text_lower for w in ["emprego", "trabalho", "financeiro", "dívida", "divida", "contas", "porta", "dinheiro", "empresa", "sustento", "salário", "desempregado"]):
        return "Financeiro"
        
    # 4. Espiritual & Conforto
    if any(w in text_lower for w in ["ansiedade", "depressão", "depressao", "paz", "libertação", "libertacao", "vício", "vicio", "fé", "fe", "proteção", "protecao", "salvação", "angústia"]):
        return "Espiritual"
        
    # 5. Agradecimento & Testemunho
    if any(w in text_lower for w in ["agradeço", "agradeco", "obrigado", "obrigada", "vitória", "vitoria", "testemunho", "alcançamos", "alcançado", "graças", "bênção", "bencao"]):
        return "Agradecimento"
        
    return "Pedidos de Oração"

# --- GESTÃO DO BANCO DE DADOS LOCAL E DASHBOARD ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    update_dashboard_data(data)

def update_dashboard_data(db):
    dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
    os.makedirs(dashboard_dir, exist_ok=True)
    json_path = os.path.join(dashboard_dir, "data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    
    git_auto_push()

def git_auto_push():
    """Realiza auto-commit e push para o GitHub Pages em background se for um repo git"""
    def push_thread():
        try:
            if os.path.exists(".git"):
                subprocess.run(["git", "add", "dashboard/data.json", "pedidos_oracao.json"], check=False)
                subprocess.run(["git", "commit", "-m", "Auto-update Hub da Central de Atendimento MG"], check=False)
                subprocess.run(["git", "push"], check=False)
        except Exception as e:
            pass
    threading.Thread(target=push_thread, daemon=True).start()

def add_record(sender_number, sender_name, text, names_found):
    db = load_db()
    category = classify_category(text)
    sub_tag = "Podcast Vencendo o Divórcio" if category == "Podcast Divórcio" else category

    record = {
        "id": len(db) + 1,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sender_number": sender_number,
        "sender_name": sender_name or "Desconhecido",
        "text": text,
        "names_found": ", ".join(names_found) if names_found else "Nenhum nome extraído",
        "category": category,
        "sub_tag": sub_tag,
        "status": "Em Atendimento"
    }
    db.append(record)
    save_db(db)
    return record

# --- REGEX E FILTRAGEM DE PEDIDOS DE ORAÇÃO ---
ORACAO_KEYWORDS = [
    r"\boraç[ãa]o\b", r"\borar\b", r"\bora\b", r"\borando\b",
    r"\bintercess[ãa]o\b", r"\binterceder\b", r"\binterceda\b",
    r"\bclamor\b", r"\bpedid[oo]\b", r"\borar por\b", r"\bora por\b",
    r"\bpodcast\b", r"\bdiv[óo]rcio\b", r"\bcasamento\b"
]

def check_prayer_request(text):
    text_lower = text.lower()
    is_prayer = any(re.search(kw, text_lower) for kw in ORACAO_KEYWORDS)
    names = extract_names(text)
    
    if is_prayer or len(names) > 0:
        return True, names
    
    return False, []

def extract_names(text):
    names = set()
    matches = re.findall(
        r'(?:por|pelo|pela|para|irmã|irmão|nome[s]?[:]?)\s+([A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+)*)',
        text
    )
    for m in matches:
        if len(m.strip()) > 2:
            names.add(m.strip())
            
    cap_sequences = re.findall(r'\b([A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+)+)\b', text)
    for seq in cap_sequences:
        if seq.lower() not in ["boa tarde", "bom dia", "boa noite", "peço oração", "por favor"]:
            names.add(seq.strip())

    return list(names)

# --- EVOLUTION API MESSAGING UTILS ---
def clean_number(num):
    cleaned = re.sub(r"\D", "", num)
    if not cleaned.endswith("@s.whatsapp.net"):
        return f"{cleaned}@s.whatsapp.net"
    return cleaned

def send_text(to_number, text):
    jid = clean_number(to_number)
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    payload = {
        "number": jid,
        "text": text
    }
    try:
        res = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        return res.json()
    except Exception as e:
        print(f"Erro ao enviar texto: {e}")
        return None

def send_media(to_number, file_path, mediatype, mimetype, filename, caption=""):
    jid = clean_number(to_number)
    url = f"{EVOLUTION_API_URL}/message/sendMedia/{INSTANCE_NAME}"
    
    with open(file_path, "rb") as f:
        encoded_string = base64.b64encode(f.read()).decode("utf-8")
    
    payload = {
        "number": jid,
        "mediatype": mediatype,
        "mimetype": mimetype,
        "media": f"data:{mimetype};base64,{encoded_string}",
        "fileName": filename,
        "caption": caption
    }
    try:
        res = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        return res.json()
    except Exception as e:
        print(f"Erro ao enviar mídia ({filename}): {e}")
        return None

# --- GERADORES DE RELATÓRIO (EXCEL E PDF) ---
def generate_excel(records, filename):
    data_for_df = []
    for r in records:
        data_for_df.append({
            "ID": r["id"],
            "Data / Hora": r["timestamp"],
            "Remetente": r["sender_name"],
            "Número": r["sender_number"],
            "Categoria": r.get("category", "Pedidos de Oração"),
            "Tag / Origem": r.get("sub_tag", ""),
            "Nomes Identificados": r["names_found"],
            "Mensagem Completa": r["text"]
        })
    df = pd.DataFrame(data_for_df)
    df.to_excel(filename, index=False, engine="openpyxl")

def generate_pdf(records, filename):
    doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor("#0b132b"),
        spaceAfter=12
    )
    story.append(Paragraph("🛡️ Hub da Central de Atendimento MG", title_style))
    
    subtitle_style = ParagraphStyle(
        'SubTitleStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.gray,
        spaceAfter=20
    )
    data_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    story.append(Paragraph(f"Relatório de Atendimentos | Gerado em: {data_str} | Total: {len(records)}", subtitle_style))
    story.append(Spacer(1, 10))

    if not records:
        story.append(Paragraph("Nenhum atendimento registrado até o momento.", styles['Normal']))
    else:
        table_data = [["ID", "Data/Hora", "Remetente", "Categoria", "Nomes", "Mensagem"]]
        for r in records:
            msg_p = Paragraph(r["text"][:120] + ("..." if len(r["text"]) > 120 else ""), styles['Normal'])
            names_p = Paragraph(r["names_found"], styles['Normal'])
            sender_p = Paragraph(f"{r['sender_name']}<br/>{r['sender_number']}", styles['Normal'])
            cat_p = Paragraph(f"<b>{r.get('category', 'Pedidos de Oração')}</b>", styles['Normal'])
            
            table_data.append([
                str(r["id"]),
                r["timestamp"].split(" ")[1] if " " in r["timestamp"] else r["timestamp"],
                sender_p,
                cat_p,
                names_p,
                msg_p
            ])

        t = Table(table_data, colWidths=[25, 55, 100, 80, 95, 190])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0b132b")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t)

    doc.build(story)

# --- ROTINA DE ENVIO DE RELATÓRIO ---
def trigger_report_delivery(target_number=ADMIN_NUMBER):
    records = load_db()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    excel_file = f"relatorio_atendimentos_{today_str}.xlsx"
    pdf_file = f"relatorio_atendimentos_{today_str}.pdf"

    generate_excel(records, excel_file)
    generate_pdf(records, pdf_file)

    send_text(
        target_number,
        f"🛡️ *HUB DA CENTRAL DE ATENDIMENTO MG*\n\n"
        f"📅 *Data:* {datetime.now().strftime('%d/%m/%Y')}\n"
        f"🔢 *Total de Atendimentos:* {len(records)}\n\n"
        f"Segue em anexo o relatório oficial em formatos PDF e Excel."
    )

    send_media(target_number, pdf_file, "document", "application/pdf", pdf_file, "📄 Relatório em PDF")
    send_media(target_number, excel_file, "document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", excel_file, "📊 Relatório em Excel")

# --- WEBHOOK PRINCIPAL ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"status": "error"}), 400

    event = data.get("event")
    if event == "messages.upsert":
        msg_data = data.get("data", {})
        key = msg_data.get("key", {})
        from_me = key.get("fromMe", False)

        if not from_me:
            remote_jid = key.get("remoteJid", "")
            sender_number = remote_jid.split("@")[0]
            push_name = msg_data.get("pushName", "Contato")
            
            message = msg_data.get("message", {})
            text_content = (
                message.get("conversation") or
                message.get("extendedTextMessage", {}).get("text") or
                ""
            ).strip()

            print(f"📩 [Mensagem Recebida] De: {push_name} ({sender_number}) | Texto: {text_content}")

            # Comando para gerar relatório sob demanda (/relatorio)
            if text_content.lower() in ["/relatorio", "!relatorio", "relatorio"]:
                print(f"⚡ Solicitado relatório por {sender_number}")
                threading.Thread(target=trigger_report_delivery, args=(sender_number,)).start()
                return jsonify({"status": "success", "action": "report_triggered"}), 200

            # Filtragem de Pedidos de Oração / Nomes
            is_prayer, names_found = check_prayer_request(text_content)

            if is_prayer:
                print(f"🙏 [ATENDIMENTO FILTRADO] Nomes: {names_found}")
                
                # 1. Salva no banco de dados local & atualiza dashboard
                record = add_record(sender_number, push_name, text_content, names_found)

                # 2. Encaminha notificação para o número de administração (5531992536994)
                podcast_badge = " 🎙️ *[PODCAST VENCENDO O DIVÓRCIO]*" if record['category'] == "Podcast Divórcio" else ""
                notification_text = (
                    f"🛡️ *HUB DA CENTRAL DE ATENDIMENTO MG*{podcast_badge}\n\n"
                    f"👤 *Remetente:* {push_name} ({sender_number})\n"
                    f"🏷️ *Nomes Detectados:* {record['names_found']}\n"
                    f"📁 *Categoria:* {record['category']}\n\n"
                    f"💬 *Mensagem Original:*\n\"{text_content}\""
                )
                send_text(ADMIN_NUMBER, notification_text)

    return jsonify({"status": "success"}), 200

# --- SCHEDULER DE TAREFAS ÀS 15:00 ---
def run_scheduler():
    schedule.every().day.at("15:00").do(trigger_report_delivery)
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    update_dashboard_data(load_db())

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Hub da Central de Atendimento MG rodando na porta {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
