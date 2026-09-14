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

def is_valid_request(text):
    if not text or len(text.strip()) < 3:
        return False

    text_lower = text.lower().strip()
    
    # 1. Ignorar saudações curtas ou mensagens soltas de cortesia
    greetings = [
        "boa noite", "bom dia", "boa tarde", "paz do senhor", "paz de deus",
        "graça e paz", "amém", "amen", "obrigado", "obrigada", "valeu", "olá", "ola",
        "tudo bem", "como vai", "oi", "oie"
    ]
    cleaned = text_lower
    for g in greetings:
        cleaned = cleaned.replace(g, "")
    cleaned = cleaned.strip()

    if len(cleaned) < 5:
        return False
        
    # 2. Ignorar links ou versículos bíblicos soltos sem pedido pessoal
    if "bible.com" in text_lower or text_lower.startswith("salmos ") or text_lower.startswith("provérbios "):
        if not any(w in text_lower for w in ["peço", "peco", "oração", "oracao", "orem", "ajuda", "preciso"]):
            return False

    # 3. Ignorar solicitações comerciais/vagas de emprego que não sejam pedidos de oração
    if any(w in text_lower for w in ["vagas de emprego", "tem vaga", "enviar currículo", "vaga de trabalho"]):
        if not any(w in text_lower for w in ["oração", "oracao", "orar", "deus"]):
            return False

    # 4. Exigir intenção relevante para o sistema
    has_podcast = any(w in text_lower for w in ["podcast", "vencendo o divórcio", "vencendo o divorcio", "divórcio", "divorcio", "casamento", "separação", "separacao", "marido", "esposa", "restauração", "restauracao", "problemas no casamento"])
    has_prayer = any(w in text_lower for w in ["oração", "oracao", "orar", "orem", "peço", "peco", "pedir", "interceda", "colocar na lista", "reza", "rezar"])
    has_health = any(w in text_lower for w in ["hospital", "cirurgia", "câncer", "cancer", "internado", "internada", "doente", "doença", "doenca", "exame", "leito", "uti", "saúde", "saude", "cura", "médico", "medico"])
    has_spiritual = any(w in text_lower for w in ["depressão", "depressao", "ansiedade", "libertação", "libertacao", "suicídio", "suicidio", "vício", "vicio", "angústia", "angustia"])
    has_testimony = any(w in text_lower for w in ["testemunho", "vitória", "vitoria", "abençoou", "abencoou", "graça alcançada", "graca alcancada"])
    has_name = is_valid_person_name(text)

    return has_podcast or has_prayer or has_health or has_spiritual or has_testimony or has_name

# --- REGRAS DE HEURÍSTICA (FALLBACK DE ALTA PRECISÃO) ---
def classify_category(text):
    text_lower = text.lower()
    if any(w in text_lower for w in ["podcast", "vencendo o divórcio", "vencendo o divorcio", "divórcio", "divorcio", "casamento", "separação", "separacao", "marido", "esposa"]):
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

FIRST_NAMES = {
    'afonso', 'airton', 'alan', 'alberto', 'alcides', 'aldo', 'alessandro', 'alex', 'alexandre',
    'alexandro', 'alfredo', 'alisson', 'allan', 'altair', 'álvaro', 'alvaro', 'amaro', 'amauri', 'amaury',
    'américo', 'americo', 'andré', 'andre', 'anderson', 'angelo', 'ângelo', 'anibal', 'aníbal', 'anselmo',
    'anthony', 'antonio', 'antônio', 'aparecido', 'aroldo', 'arthur', 'artur', 'augusto', 'ayrton', 'baltazar',
    'benedito', 'benjamim', 'benjamin', 'bento', 'bernardo', 'breno', 'bruno', 'caio', 'caique', 'caíque',
    'carlos', 'cássio', 'cassio', 'celso', 'césar', 'cesar', 'cicero', 'cícero', 'claudio', 'cláudio',
    'cleber', 'cléber', 'cleiton', 'clovis', 'clóvis', 'cristian', 'cristiano', 'dagoberto', 'daniel', 'danilo',
    'dario', 'dário', 'davi', 'david', 'deivisson', 'denis', 'dênis', 'diego', 'diogo', 'dionísio', 'dionisio',
    'dirceu', 'douglas', 'eder', 'éder', 'edgard', 'edgar', 'edílson', 'edilson', 'edmar', 'edmilson', 'edmundo',
    'edson', 'eduardo', 'edvaldo', 'elias', 'eliel', 'eliseu', 'emerson', 'emilio', 'emílyo',
    'enoch', 'enzo', 'eric', 'érica', 'ériton', 'ernani', 'ernesto', 'estevão', 'estevao', 'eugênio',
    'eugenio', 'euller', 'evandro', 'everton', 'ezequiel', 'fabiano', 'fábio', 'fabio', 'fabricio', 'fabrício',
    'fausto', 'felipe', 'feliph', 'feliphe', 'felix', 'félix', 'fernando', 'filipe', 'flavio', 'flávio',
    'francisco', 'gabriel', 'geovani', 'geovane', 'geraldo', 'gerson', 'gérson', 'gilberto', 'gilmar', 'gilson',
    'giovani', 'giovanni', 'givanildo', 'glauber', 'guilherme', 'gustavo',
    'haroldo', 'heitor', 'hélio', 'helio', 'henrique', 'hercules', 'hércules', 'hermes', 'hugo', 'iago',
    'ian', 'igor', 'isaac', 'isaias', 'isaías', 'israel', 'itamar', 'ivaldo', 'ivan', 'ivanildo', 'izaias',
    'jacó', 'jaco', 'jacob', 'jaime', 'jair', 'jairo', 'jamil', 'jandir', 'janio', 'jânio', 'jean', 'jeferson',
    'jefferson', 'jesse', 'jessé', 'joab', 'joão', 'joao', 'joaquim', 'joel', 'joeliton', 'jonas',
    'jonatan', 'jonathan', 'jorge', 'josé', 'jose', 'joseph', 'joshua', 'josias', 'josué', 'josue', 'juliano',
    'julio', 'júlio', 'junior', 'júnior', 'jurandir', 'juvenal', 'laércio', 'laercio', 'lauro', 'lázaro', 'lazaro',
    'leandro', 'leo', 'léo', 'leonardo', 'leonel', 'leônidas', 'leonidas', 'leopoldina', 'leopoldo', 'levi',
    'luan', 'lucas', 'luciano', 'lúcio', 'lucio', 'luís', 'luis', 'luiz', 'luka', 'lukas', 'manuel',
    'manoel', 'marcelo', 'márcio', 'marcio', 'marco', 'marcos', 'marcus', 'mário', 'mario', 'mateus', 'matheus',
    'matias', 'maurício', 'mauricio', 'mauro', 'max', 'maxwell', 'miguel', 'moacir', 'moisés', 'moises',
    'murilo', 'natan', 'natanael', 'nathan', 'nelson', 'neto', 'nicolas', 'olavo',
    'orlando', 'oscar', 'osmar', 'osvaldo', 'oswaldo', 'otávio', 'otavio', 'otto', 'pablo', 'paschoal',
    'patricio', 'patrício', 'patrick', 'paulo', 'pedro', 'plínio', 'plinio', 'rafael', 'raimundo',
    'ramon', 'raoni', 'raul', 'reginaldo', 'reinaldo', 'renan', 'renato', 'ricardo', 'richard', 'rivaldo',
    'roberto', 'robson', 'rodolfo', 'rodrigo', 'roger', 'rogério', 'rogerio', 'romário', 'romario', 'romeu',
    'romildo', 'rômulo', 'romulo', 'ronald', 'ronaldo', 'ronan', 'ruberlei', 'rubens', 'rui', 'ruy',
    'samuel', 'saulo', 'sérgio', 'sergio', 'severino', 'silvio', 'sílvio', 'tales', 'tasso', 'tatiana',
    'taylor', 'téo', 'teo', 'teodoro', 'thiago', 'tiago', 'tomás', 'tomas', 'tomaz', 'ulisses', 'vagner',
    'valdir', 'valdo', 'valdemar', 'valdemir', 'valter', 'vanderlei', 'vanderley', 'vicente', 'victor',
    'vinicius', 'vinícius', 'vitor', 'vítor', 'vladimir', 'wagner', 'waldir', 'waldemir', 'walter',
    'wanderley', 'washington', 'weliton', 'wellington', 'wesley', 'willian', 'william', 'wilson', 'yago', 'yuri',
    'abigail', 'adélia', 'adelia', 'adriana', 'agatha', 'ágatha', 'agnes', 'aída', 'aida', 'alessandra',
    'alice', 'alícia', 'alicia', 'aline', 'amalia', 'amália', 'amanda', 'amélia', 'amelia', 'ana', 'analu',
    'andréa', 'andrea', 'andreia', 'andréia', 'andressa', 'angela', 'ângela', 'angelica', 'angélica',
    'anita', 'antonia', 'antônia', 'antonieta', 'aparecida', 'ariane', 'ariel', 'arlete', 'astrid', 'áurea',
    'aurea', 'barbara', 'bárbara', 'beatriz', 'berenice', 'betânia', 'betania', 'benta', 'bernadete', 'bianca',
    'bruna', 'camila', 'carina', 'carla', 'carlota', 'carmen', 'carolina', 'caroline', 'cássia', 'cassia',
    'catarina', 'cátia', 'catia', 'cecília', 'cecilia', 'célia', 'celia', 'celina', 'cibele', 'cila', 'cintia',
    'cíntia', 'clara', 'clarice', 'clarissa', 'cláudia', 'claudia', 'claudete', 'cleide', 'cleo', 'cléo',
    'conceição', 'conceicao', 'cristiana', 'cristiane', 'cristina', 'dagmar', 'daiana', 'daiane', 'dalva',
    'daniela', 'daniele', 'daniella', 'danielle', 'dara', 'daria', 'dária', 'débora', 'debora', 'deise',
    'denise', 'diana', 'diná', 'dina', 'dinalva', 'diva', 'dulce',
    'edna', 'eduarda', 'elaine', 'elena', 'eleonora', 'eliana', 'eliane', 'elisa', 'elisabete', 'elisabeth',
    'elisângela', 'elisangela', 'elza', 'emanuela', 'emanoela', 'emanuelle', 'emília', 'emilia', 'emilly',
    'emily', 'erika', 'érika', 'ester', 'esther', 'eunice', 'eva', 'evangelina', 'evelyn', 'fabiana',
    'fabíola', 'fabiola', 'fátima', 'fatima', 'fernanda', 'flávia', 'flavia', 'flora', 'francisca',
    'gabriela', 'gabriele', 'gabriella', 'gabrielle', 'georgia', 'geórgia', 'geovana', 'geovanna', 'gilda',
    'giovana', 'giovanna', 'gisela', 'gisele', 'gislaine', 'glória', 'gloria', 'graziela',
    'graziele', 'helena', 'helenice', 'heloísa', 'heloisa', 'iara', 'ines', 'inês', 'ingrid',
    'iolanda', 'iracema', 'isabel', 'isabela', 'isabell', 'isabella', 'isabelle', 'isadora', 'isaura',
    'isolda', 'ivana', 'ivone', 'ivonete', 'ivete', 'izabel', 'izabela', 'izabele', 'jacqueline', 'jaqueline',
    'jandira', 'jane', 'janaina', 'janaína', 'janice', 'jessica', 'jéssica', 'joana',
    'josi', 'josiane', 'júlia', 'julia', 'juliana', 'juliane', 'julieta',
    'jurema', 'jussara', 'katia', 'kátia', 'keli', 'kelly', 'laís', 'lais', 'lara', 'larissa', 'laura',
    'lavínia', 'lavinia', 'léa', 'lea', 'leandra', 'leila', 'lelia', 'lélia', 'letícia',
    'leticia', 'lia', 'liana', 'lícia', 'licia', 'lídia', 'lidia', 'lídice', 'lilian', 'lílian',
    'liliana', 'liliane', 'lina', 'linda', 'livia', 'lívia', 'lorena', 'lourdes', 'luana', 'lucia', 'lúcia',
    'luciana', 'luciane', 'luciene', 'lucila', 'lucília', 'lucilia', 'ludmila', 'luísa', 'luisa', 'luiza',
    'luíza', 'luzia', 'madalena', 'magali', 'magda', 'maia', 'maira', 'maíra', 'maísa', 'maisa', 'manuela',
    'manuella', 'mara', 'marcela', 'márcia', 'marcia', 'margarete', 'margarida', 'maria',
    'mariana', 'marilena', 'marilene', 'marilia', 'marília', 'marilu', 'marilza', 'marilze', 'marina',
    'marinez', 'marisa', 'marisete', 'marisol', 'maritza', 'marlene', 'marli', 'marluce', 'marta', 'martha',
    'matilde', 'maura', 'maysa', 'melina', 'melissa', 'mercedes', 'michele', 'michelli', 'michelle', 'milena',
    'mirela', 'mirella', 'miriam', 'míriam', 'mirian', 'mônica', 'monica', 'monique', 'nádia', 'nadia',
    'nadir', 'naiara', 'nair', 'nanci', 'nancy', 'nara', 'natália', 'natalia', 'nathalia', 'nathália',
    'nayara', 'neide', 'neusa', 'neuza', 'nicolli', 'nicolly', 'nilda', 'nilsa', 'nilza', 'noemi', 'noemia',
    'noêmia', 'norma', 'olga', 'olívia', 'olivia', 'otília', 'otilia', 'paloma', 'pamela', 'pâmela',
    'paola', 'paôla', 'patrícia', 'patricia', 'paula', 'paulina', 'priscila', 'priscilla', 'rafaela', 'rafaella',
    'raimunda', 'raquel', 'rayssa', 'rebeca', 'regina', 'renata', 'rita', 'roberta', 'rosana', 'rosângela',
    'rosangela', 'rosani', 'rosaria', 'rosária', 'roseli', 'rosemere', 'rosemary', 'rosemire',
    'rosimere', 'rosimeire', 'rosina', 'ruth', 'sabrina', 'salete', 'samanta', 'samantha', 'samara', 'sandra',
    'sara', 'sarah', 'selma', 'severina', 'shirley', 'silvana', 'sílvia', 'silvia', 'simone', 'socorro',
    'solange', 'sônia', 'sonia', 'sueli', 'suely', 'suzana', 'taís', 'tais', 'taísa', 'taisa',
    'talita', 'tânia', 'tania', 'tatiana', 'tatiane', 'teresa', 'teresinha', 'thereza', 'tereza', 'terezinha',
    'thaís', 'thais', 'thalita', 'vânia', 'vania', 'vanessa', 'verônica', 'veronica', 'vicentina',
    'vitoria', 'vitória', 'vivian', 'viviane', 'waleska', 'wanda', 'wanessa', 'wilma', 'yara', 'yasmin',
    'yasmim', 'zenaide', 'zilá', 'zilda', 'zilma', 'zoraide', 'zulmira', 'dafne', 'gutemberg'
}

INVALID_WORDS = {
    'bahia', 'minas', 'goiás', 'goias', 'paraná', 'parana', 'amazonas', 'piauí', 'piaui', 'pernambuco',
    'mato', 'sergipe', 'roraima', 'distrito', 'região', 'regiao', 'norte', 'sul', 'leste', 'oeste',
    'rondônia', 'rondonia', 'tocantins', 'amapá', 'amapa', 'alagoas', 'espírito', 'espirito', 'santo',
    'santa', 'são', 'sao', 'rio', 'mercado', 'mercadinho', 'quitanda', 'hortifruti', 'limpeza', 'unidade',
    'prefeitura', 'governo', 'hospital', 'vila', 'bairro', 'rua', 'avenida', 'praça', 'praca', 'cidade',
    'cigarro', 'oração', 'oracao', 'fogo', 'sobre', 'you', 'what', 'horas', 'janeiro', 'fevereiro',
    'março', 'marco', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro',
    'dezembro', 'pedra', 'princesa', 'boa', 'santana', 'bom', 'bernardino', 'campo', 'bonsucesso',
    'verdelandia', 'mogi', 'juiz', 'teófilo', 'teofilo', 'sou', 'país', 'pais', 'brasil', 'argentina',
    'áfrica', 'africa', 'mercearia', 'enfermagem', 'unidade', 'penha', 'centro', 'sudeste', 'nordeste',
    'federal', 'macaé', 'macae', 'matias', 'taquaraçu', 'taquaracu', 'sabará', 'sabara', 'neves', 'lagoas',
    'moura', 'leopoldina', 'ibirité', 'ibiritê', 'confins', 'bocaiúva', 'bocaiuva', 'oliveira', 'santa clara',
    'belo horizonte', 'uberlândia', 'uberlandia', 'juiz de fora', 'contagem', 'betim', 'montes claros',
    'ipatinga', 'governador valadares', 'sete lagoas', 'deus', 'senhor', 'jesus', 'cristo', 'bispo', 'pastor',
    'dr', 'doutor', 'prof', 'professor', 'professora', 'deputado', 'prefeito', 'vereador', 'bolsonaro', 'caiado', 'chagas',
    'contato', 'whatsapp', 'peço', 'peco', 'silva', 'angola', 'estadual', 'municipal', 'hospital', 'coronel',
    'dra', 'dora', 'ubs', 'upa', 'clínica', 'clinica', 'araruama', 'itaboraí', 'itaborai', 'manilha',
    'rj', 'mg', 'sp', 'chamo', 'nome', 'endocrinologia', 'posto',
    'gostaria', 'pedido', 'pedir', 'horário', 'horario', 'igreja', 'disponível', 'disponivel', 'cura', 'saúde', 'saude',
    'diarréia', 'diarreia', 'pneumonia', 'colonoscopia', 'calafrios', 'dor', 'idoso', 'diabética', 'diabetica', 'garganta', 'corpo', 'inflamada',
    'ruy barbosa', 'césar maia', 'cesar maia', 'almino afonso', 'jorge canella'
}

def is_valid_person_name(name_str):
    cleaned = name_str.strip()
    # Strip list item prefixes like '108. Sandra', 'S2. João' (only numbers or letter+digits prefix)
    cleaned = re.sub(r'^\s*\d+[\.\)]?\s*', '', cleaned)
    cleaned = re.sub(r'^\s*[A-Za-z]\d+[\.\)]?\s*', '', cleaned)
    words = [w.lower().strip('.,!?:;"\'()[]{}') for w in cleaned.split()]
    if not words or len(cleaned) < 2:
        return False
    
    for w in words:
        if w in INVALID_WORDS or w.isdigit():
            return False
            
    first = words[0]
    if first in FIRST_NAMES:
        return True

    if len(words) >= 2 and len(first) >= 3:
        first_orig = cleaned.split()[0].strip('.,!?:;"\'()[]{}')
        if first_orig and (first_orig[0].isupper() or first_orig.isupper()):
            return True

    return False

def extract_names(text, push_name=''):
    names = set()
    
    # Pre-process lines to strip list prefixes (e.g., '108. Sandra Gonçalves', '20. Altair Lopes')
    clean_lines = []
    for line in text.splitlines():
        sub_line = re.sub(r'^\s*\d+[\.\)]?\s*', '', line).strip()
        sub_line = re.sub(r'^\s*[A-Za-z]\d+[\.\)]?\s*', '', sub_line).strip()
        if sub_line:
            clean_lines.append(sub_line)
    
    clean_text = "\n".join(clean_lines)

    # 1. Meu nome é / e [Nome]
    m_name = re.search(r'\bmeu\s+nome\s+[eé:]?\s*([A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+)*)', clean_text, re.IGNORECASE)
    if m_name:
        cand = m_name.group(1).strip()
        if is_valid_person_name(cand):
            names.add(cand)

    # 2. Preposições de indicação de nome
    matches = re.findall(r'(?:por|pelo|pela|para|p/|de|irmã|irmão|nome[s]?[:]?)\s+([A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+)*)', clean_text)
    for m in matches:
        cand = m.strip()
        if is_valid_person_name(cand):
            names.add(cand)

    # 3. Nomes próprios compostos no texto
    cap_sequences = re.findall(r'\b([A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÏÓÒÔÕÚÜÇ][a-záàâãéèêíïóòôõúüç]+)+)\b', clean_text)
    for seq in cap_sequences:
        cand = seq.strip()
        if is_valid_person_name(cand):
            names.add(cand)

    # 4. Nomes simples em linhas únicas (ex: em listas de oração)
    for line in clean_lines:
        cand = line.strip()
        if is_valid_person_name(cand):
            names.add(cand)

    # 5. Fallback: se a mensagem é um pedido pessoal e push_name for um nome real válido
    if not names and push_name and is_valid_person_name(push_name):
        if any(w in text.lower() for w in ['mim', 'minha', 'meu', 'peço', 'peco', 'oracao', 'oração']):
            names.add(push_name)

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
                files_to_add = [f for f in ["dashboard/data.json", "data.json", "pedidos_oracao.json"] if os.path.exists(f)]
                if files_to_add:
                    subprocess.run(["git", "add"] + files_to_add, check=False)
                    subprocess.run(["git", "commit", "-m", "Auto-update Hub da Central de Atendimento MG"], check=False)
                    subprocess.run(["git", "push"], check=False)
        except Exception:
            pass
    threading.Thread(target=push_thread, daemon=True).start()
def format_phone_number(raw_num):
    if not raw_num or not isinstance(raw_num, str):
        return ""
    digits = "".join(filter(str.isdigit, raw_num))
    if len(digits) > 13: # LID ID do WhatsApp
        return ""
    if digits.startswith("55") and len(digits) in (12, 13):
        ddd = digits[2:4]
        num = digits[4:]
        if len(num) == 9:
            return f"+55 ({ddd}) {num[:5]}-{num[5:]}"
        elif len(num) == 8:
            return f"+55 ({ddd}) {num[:4]}-{num[4:]}"
    elif len(digits) in (10, 11):
        ddd = digits[:2]
        num = digits[2:]
        if len(num) == 9:
            return f"({ddd}) {num[:5]}-{num[5:]}"
        elif len(num) == 8:
            return f"({ddd}) {num[:4]}-{num[4:]}"
    return raw_num if digits else ""

def clean_sender_info(remote_jid, push_name, contact_map=None):
    clean_id = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    mapped_name = ""
    mapped_phone = ""

    if contact_map:
        cinfo = contact_map.get(remote_jid) or contact_map.get(clean_id)
        if cinfo:
            mapped_name = cinfo.get("name", "")
            mapped_phone = cinfo.get("phone", "")

    best_name = push_name if (push_name and push_name != "Contato" and not push_name.isdigit() and len(push_name) < 35) else mapped_name
    if not best_name or best_name.isdigit() or (len(best_name) > 13 and best_name.isdigit()):
        best_name = "Contato WhatsApp"

    phone_src = mapped_phone or clean_id
    formatted_phone = format_phone_number(phone_src)
    
    if not formatted_phone:
        formatted_phone = formatted_phone if formatted_phone else "Contato WhatsApp"

    return best_name, formatted_phone

def sanitize_str(s):
    if not s or not isinstance(s, str):
        return str(s) if s is not None else ""
    return s.replace("\x00", "").replace("\r", "").strip()

def add_record(sender_number, sender_name, text, category, names_found, summary="", message_timestamp=None):
    db = load_db()
    sub_tag = "Podcast Vencendo o Divórcio" if category == "Podcast Divórcio" else category

    clean_text = sanitize_str(text)
    clean_sender_name = sanitize_str(sender_name) or "Contato WhatsApp"
    clean_sender_number = sanitize_str(sender_number)
    clean_summary = sanitize_str(summary)

    if isinstance(names_found, list):
        clean_names = ", ".join([sanitize_str(n) for n in names_found if sanitize_str(n)])
    else:
        clean_names = sanitize_str(names_found)

    msg_dt = None
    if message_timestamp:
        try:
            ts = float(message_timestamp)
            if ts > 1e11:
                ts = ts / 1000.0
            msg_dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            msg_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if not msg_dt:
        msg_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record = {
        "id": len(db) + 1,
        "timestamp": msg_dt,
        "sender_number": clean_sender_number,
        "sender_name": clean_sender_name,
        "text": clean_text,
        "names_found": clean_names if clean_names else "Nenhum nome extraído",
        "category": category,
        "sub_tag": sub_tag,
        "summary": clean_summary,
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
            raw_ts = msg_data.get("messageTimestamp")
            
            message = msg_data.get("message", {})
            text_content = (
                message.get("conversation") or
                message.get("extendedTextMessage", {}).get("text") or
                ""
            ).strip()

            print(f"📩 [Mensagem Recebida] De: {push_name} ({sender_number}) | Texto: {text_content}")

            # --- PROCESSAMENTO PASSIVO EM BACKGROUND VIA IA ---
            def process_incoming_message(msg_ts):
                ai_result = ai_background_classifier(push_name, text_content)

                if ai_result:
                    if not ai_result.get("eh_relevante", True):
                        print(f"⏭️ Mensagem considerada irrelevante/spam pela IA: {text_content}")
                        return
                    
                    category = ai_result.get("categoria", classify_category(text_content))
                    names = ai_result.get("nomes_para_oracao", extract_names(text_content))
                    summary = ai_result.get("resumo", "")
                else:
                    if not is_valid_request(text_content):
                        print(f"⏭️ Mensagem desconsiderada (saudação ou irrelevante): {text_content}")
                        return
                    category = classify_category(text_content)
                    names = extract_names(text_content)
                    summary = ""

                print(f"🧠 [IA PASSIVA] Categoria: {category} | Nomes: {names} | Resumo: {summary}")

                # Salva no banco de dados local & atualiza dashboard web no ar
                add_record(sender_number, push_name, text_content, category, names, summary, message_timestamp=msg_ts)

            # Roda em background para não travar a resposta da API
            threading.Thread(target=process_incoming_message, args=(raw_ts,), daemon=True).start()

    return jsonify({"status": "success"}), 200

def auto_sync_loop(interval_seconds=20):
    """Roda a cada 20s para verificar se chegaram novas mensagens no WhatsApp e sincronizar no GitHub Pages"""
    import subprocess
    while True:
        try:
            time.sleep(interval_seconds)
            url_msgs = f"{EVOLUTION_API_URL}/chat/findMessages/{INSTANCE_NAME}"
            res = requests.post(url_msgs, json={"limit": 50, "page": 1}, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    msgs = data.get("messages", {}).get("records", [])
                    contact_map = load_contact_map()
                    db = load_db()
                    existing_texts = {item["text"].strip() for item in db if "text" in item}
                    new_added = False

                    for msg in msgs:
                        key = msg.get("key", {})
                        if not key.get("fromMe", False):
                            remote_jid = key.get("remoteJid", "")
                            push_name = msg.get("pushName") or ""
                            sender_name, sender_phone = clean_sender_info(remote_jid, push_name, contact_map)
                            
                            message_content = msg.get("message")
                            if not isinstance(message_content, dict):
                                continue
                            
                            text_content = (
                                message_content.get("conversation") or
                                message_content.get("extendedTextMessage", {}).get("text") or
                                ""
                            ).strip()
                            clean_txt = sanitize_str(text_content)

                            if clean_txt and clean_txt not in existing_texts:
                                if is_valid_request(clean_txt):
                                    cat = classify_category(clean_txt)
                                    nms = extract_names(clean_txt, sender_name)
                                    raw_ts = msg.get("messageTimestamp")
                                    sub_tag = "Podcast Vencendo o Divórcio" if cat == "Podcast Divórcio" else cat
                                    
                                    clean_names = ", ".join([sanitize_str(n) for n in nms if sanitize_str(n)]) if isinstance(nms, list) else sanitize_str(nms)
                                    
                                    msg_dt = None
                                    if raw_ts:
                                        try:
                                            ts_val = float(raw_ts)
                                            if ts_val > 1e11: ts_val = ts_val / 1000.0
                                            msg_dt = datetime.fromtimestamp(ts_val).strftime("%Y-%m-%d %H:%M:%S")
                                        except Exception:
                                            msg_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    if not msg_dt:
                                        msg_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                                    rec = {
                                        "id": len(db) + 1,
                                        "timestamp": msg_dt,
                                        "sender_number": sanitize_str(sender_phone),
                                        "sender_name": sanitize_str(sender_name) or "Contato WhatsApp",
                                        "text": clean_txt,
                                        "names_found": clean_names if clean_names else "Nenhum nome extraído",
                                        "category": cat,
                                        "sub_tag": sub_tag,
                                        "summary": "",
                                        "status": "Em Atendimento"
                                    }
                                    db.append(rec)
                                    existing_texts.add(clean_txt)
                                    new_added = True

                    if new_added:
                        db.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                        for i, item in enumerate(db, 1): item['id'] = i
                        save_db(db)
                        update_dashboard_data(db)
                        print(f"🔄 [AUTO-SYNC 20s] Novos nomes capturados! Atualizando GitHub Pages...")
                        subprocess.run(["git", "add", "data.json", "dashboard/data.json", "pedidos_oracao.json"], cwd="C:/Projetos/Whatsapp", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.run(["git", "commit", "-m", "Auto-sync 20s: novos pedidos de oracao"], cwd="C:/Projetos/Whatsapp", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.run(["git", "push", "origin", "main"], cwd="C:/Projetos/Whatsapp", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print(f"✅ [AUTO-SYNC 20s] GitHub Pages atualizado no ar!")
        except Exception as e:
            print(f"⚠️ [AUTO-SYNC ERR]: {e}")

if __name__ == "__main__":
    update_dashboard_data(load_db())

    # Inicia rotina de sincronização automática de 20s em background
    threading.Thread(target=auto_sync_loop, args=(20,), daemon=True).start()

    port = int(os.getenv("PORT", 5000))
    print(f"[START] Hub da Central de Atendimento MG (Auto-sync 20s Ativo) rodando na porta {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
