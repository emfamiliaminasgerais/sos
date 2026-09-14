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

# Google Gemini AI para Classificação Passiva de Pano de Fundo
import google.generativeai as genai

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
DB_FILE = "pedidos_oracao.json"

HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json"
}

# --- CONFIGURAÇÃO DA IA GEMINI (PASSIVA DE PANO DE FUNDO) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
else:
    gemini_model = None

def ai_background_classifier(sender_name, text_content):
    """
    IA PASSIVA DE PANO DE FUNDO:
    - Jamais envia respostas ou notificações no WhatsApp (100% via Dashboard Web).
    - Analisa a mensagem recebida para classificar com precisão semântica.
    """
    if not gemini_model:
        return None

    prompt = f"""
    Você é um classificador PASSIVO em segundo plano do Hub da Central de Atendimento MG.
    Sua ÚNICA função é analisar a mensagem recebida e retornar a classificação em formato JSON.
    VOCÊ NUNCA DEVE GERAR RESPOSTA PARA O USUÁRIO DO WHATSAPP OU ENVIAR NOTIFICAÇÃO. APENAS CLASSIFIQUE.

    Mensagem Recebida de {sender_name}:
    "{text_content}"

    Regras de Classificação:
    1. eh_relevante: true se for pedido de oração, relato de problema no casamento, menção ao podcast, problema de saúde, financeiro, espiritual ou agradecimento. false se for apenas saudações soltas ou spam.
    2. categoria: Escolha EXATAMENTE uma:
       - "Podcast Divórcio" (se mencionou 'Podcast Vencendo o Divórcio', vídeos ou problemas no casamento)
       - "Pedidos de Oração" (pedidos gerais de oração ou auxílio)
       - "Saúde" (pedidos de cura, exames, cirurgias, internamentos)
       - "Financeiro" (emprego, dívidas, provisão)
       - "Espiritual" (libertação, ansiedade, depressão, fé)
       - "Agradecimento" (testemunhos, agradecimentos, vitórias)
    3. nomes_para_oracao: Array com os nomes das pessoas mencionadas no texto para a lista de oração.
    4. resumo: Resumo curto de 1 frase da situação.

    Retorne APENAS o JSON no formato:
    {{
        "eh_relevante": true,
        "categoria": "Podcast Divórcio",
        "nomes_para_oracao": ["Maria Silva", "Roberto Silva"],
        "resumo": "Assistiu o podcast e pediu oração para o casamento com problemas."
    }}
    """

    try:
        response = gemini_model.generate_content(prompt)
        text_resp = response.text.strip()
        if text_resp.startswith("```"):
            text_resp = re.sub(r"^```[a-z]*\n?", "", text_resp)
            text_resp = re.sub(r"\n?```$", "", text_resp)
        
        parsed = json.loads(text_resp)
        return parsed
    except Exception as e:
        print(f"⚠️ Erro ao consultar IA Gemini em background: {e}")
        return None

# --- REGRAS DE HEURÍSTICA (FALLBACK) ---
def classify_category(text):
    text_lower = text.lower()
    if any(w in text_lower for w in ["podcast", "vencendo o divórcio", "vencendo o divorcio"]):
        return "Podcast Divórcio"
    if any(w in text_lower for w in ["saúde", "saude", "doença", "doenca", "hospital", "cirurgia", "cura", "médico", "medico", "câncer", "cancer", "dor", "exame", "remédio", "internado", "leito"]):
        return "Saúde"
    if any(w in text_lower for w in ["emprego", "trabalho", "financeiro", "dívida", "divida", "contas", "porta", "dinheiro", "empresa", "sustento", "salário", "desempregado"]):
        return "Financeiro"
    if any(w in text_lower for w in ["ansiedade", "depressão", "depressao", "paz", "libertação", "libertacao", "vício", "vicio", "fé", "fe", "proteção", "protecao", "salvação", "angústia"]):
        return "Espiritual"
    if any(w in text_lower for w in ["agradeço", "agradeco", "obrigado", "obrigada", "vitória", "vitoria", "testemunho", "alcançamos", "alcançado", "graças", "bênção", "bencao"]):
        return "Agradecimento"
    return "Pedidos de Oração"

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

# --- GESTÃO DO BANCO DE DADOS LOCAL E DASHBOARD WEB ---
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
    
    # Atualiza em dashboard/data.json e na raiz /data.json para GitHub Pages
    json_path = os.path.join(dashboard_dir, "data.json")
    root_json_path = os.path.join(os.path.dirname(__file__), "data.json")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    with open(root_json_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)
    
    git_auto_push()

def git_auto_push():
    """Realiza auto-commit e push para o GitHub Pages em background"""
    def push_thread():
        try:
            if os.path.exists(".git"):
                subprocess.run(["git", "add", "dashboard/data.json", "data.json", "pedidos_oracao.json"], check=False)
                subprocess.run(["git", "commit", "-m", "Auto-update Hub da Central de Atendimento MG"], check=False)
                subprocess.run(["git", "push"], check=False)
        except Exception as e:
            pass
    threading.Thread(target=push_thread, daemon=True).start()

def add_record(sender_number, sender_name, text, category, names_found, summary=""):
    db = load_db()
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
        "summary": summary,
        "status": "Em Atendimento"
    }
    db.append(record)
    save_db(db)
    return record

# --- GERADORES DE RELATÓRIO (EXCEL E PDF DISPONÍVEIS VIA DASHBOARD) ---
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
            "Resumo IA": r.get("summary", ""),
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

# --- WEBHOOK PRINCIPAL (100% VIA DASHBOARD WEB - SEM NOTIFICAÇÕES WHATSAPP) ---
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

        # O BOT NUNCA RESPONDE AO USUÁRIO NEM ENVIA MENSAGENS DE NOTIFICAÇÃO (TUDO 100% VIA DASHBOARD WEB)
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

            # --- PROCESSAMENTO PASSIVO EM BACKGROUND VIA IA ---
            def process_incoming_message():
                ai_result = ai_background_classifier(push_name, text_content)

                if ai_result:
                    if not ai_result.get("eh_relevante", True):
                        print(f"⏭️ Mensagem considerada irrelevante/spam pela IA: {text_content}")
                        return
                    
                    category = ai_result.get("categoria", classify_category(text_content))
                    names = ai_result.get("nomes_para_oracao", extract_names(text_content))
                    summary = ai_result.get("resumo", "")
                else:
                    category = classify_category(text_content)
                    names = extract_names(text_content)
                    summary = ""

                print(f"🧠 [IA PASSIVA] Categoria: {category} | Nomes: {names} | Resumo: {summary}")

                # Salva no banco de dados local & atualiza dashboard web no ar
                add_record(sender_number, push_name, text_content, category, names, summary)

            # Roda em background para não travar a resposta da API
            threading.Thread(target=process_incoming_message, daemon=True).start()

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    update_dashboard_data(load_db())

    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Hub da Central de Atendimento MG (100% Via Dashboard Web) rodando na porta {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
