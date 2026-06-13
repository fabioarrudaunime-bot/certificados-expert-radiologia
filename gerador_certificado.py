# gerador_certificado_multicursos.py
# EXPERT RADIOLOGIA - Gerador de certificados com seleção de curso
# Mantém a validação original: Ed25519 + QR Code + payload/base64url + site autenticador.

import os
import sys
import json
import uuid
import base64
import datetime
import io
from pathlib import Path
from typing import Optional, Dict, List

from PIL import Image
import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from nacl import signing
import hashlib

# ========== CONFIGURAÇÕES ==========
APP_NAME = "EXPERT RADIOLOGIA - Certificados"
CARGA_HORARIA_PADRAO = "60 horas"
PROFESSOR = "Fabrício Rodrigues dos Santos"
CNPJ = "59.487.852/0001-06"

# IMPORTANTE:
# Coloque as imagens de fundo na mesma pasta do programa, ou empacote no PyInstaller.
# Você pode trocar os nomes abaixo para os nomes reais das suas imagens.
# Se alguma imagem não existir, o PDF será gerado sem fundo nessa página.
CURSOS: Dict[str, Dict[str, object]] = {
    "Angiotomografia": {
        "nome": "Angiotomografia",
        "carga_horaria": CARGA_HORARIA_PADRAO,
        "background": "fundo_certificado_angiotomografia.png",
        "background_fallback": "fundo_certificado.png",
        "conteudo": [
            "Introdução a angiotomografia",
            "Ferramentas e Workstation",
            "Anatomia, Fisiologia e Patologia",
            "Angiotomografia das artérias pulmonares",
            "Angiotomografia da aorta torácica",
            "Angiotomografia da aorta abdominal",
            "Angiotomografia dos MMSS",
            "Angiotomografia dos MMII",
            "Angiotomografia do Crânio",
            "Angiotomografia do Pescoço",
            "Angiotomografia das art. coronárias",
            "Otimização de protocolos de angiotomografia",
        ],
    },
    "Ressonância Magnética": {
        "nome": "Ressonância Magnética",
        "carga_horaria": CARGA_HORARIA_PADRAO,
        "background": "fundo_certificado_ressonancia.png",
        "background_fallback": "fundo_certificado.png",
        "conteudo": [
            "Introdução ao curso",
            "Princípios básicos",
            "Ponderação e contraste",
            "Formação da imagem",
            "Parâmetros e qualidade da imagem",
            "Sequências de pulso",
            "Aplicando o conhecimento",
            "Conceitos Importantes",
            "Crânio Rotina",
            "Crânio AVC",
            "Crânio Epilepsia",
            "Crânio Demência",
            "Crânio Trauma",
            "Crânio Tumor",
            "Coluna Cervical",
            "Coluna Dorsal",
            "Coluna Lombar",
            "Ombro",
            "Joelho",
        ],
    },
    "Tomografia 2.0 + Simulador": {
        "nome": "Tomografia 2.0 + Simulador",
        "carga_horaria": CARGA_HORARIA_PADRAO,
        "background": "fundo_certificado_tomografia.png",
        "background_fallback": "fundo_certificado.png",
        "conteudo": [
            "Introdução a tomografia",
            "Parâmetros técnicos",
            "Conhecendo o equipamento",
            "Meios de contraste",
            "Treinamento com Simulador de tomografia",
            "Posicionamento na tomografia",
            "Tomografia do Crânio",
            "Tomografia Seios da face",
            "Tomografia da Face",
            "Tomografia da ATM",
            "Tomografia da Mastoide",
            "Tomografia das Órbitas",
            "Tomografia da Hipófise",
            "Tomografia do Pescoço",
            "Tomografia da Coluna Cervical",
            "Tomografia Coluna Torácica",
            "Tomografia Coluna Lombar",
            "Tomografia do Tórax",
            "Tomografia do Abdome",
            "Tomografia do Joelho",
            "Tomografia do Pé/Tornozelo",
            "Tomografia do Ombro",
            "Tomografia do Cotovelo",
            "Tomografia do Punho/Mão",
        ],
    },
}

CURSO_PADRAO = "Angiotomografia"

# Fontes (se tiver TTF modernos/itálicos, coloque-os na pasta e aponte aqui)
FONT_TITULO_ITALICO = None   # ex.: "Montserrat-Italic.ttf"
FONT_TEXTO_ITALICO = None    # ex.: "Inter-Italic.ttf"
FONT_NEGRITO_ITALICO = None  # ex.: "Montserrat-BoldItalic.ttf"

BASE_VALIDATION_URL = "https://fabioarrudaunime-bot.github.io/expert.radiologia1/"

# QR menor
QR_BOX_SIZE = 8
QR_BORDER = 2
QR_PIXEL_SIZE_FRONT = 85   # px ~ points

# Chave pública que está no seu site autenticador.
# O programa vai conferir se a chave privada usada para assinar corresponde a esta chave pública.
EXPECTED_PUBLIC_KEY_B64 = "9P5bnY6DIc4P6WesVhQ4mT+PJOKJ9ccQYRG8NH2Dc2g="
PRIVATE_KEY_NAME = "private_key.ed25519"
PUBLIC_KEY_NAME = "public_key.ed25519"


def app_dir() -> Path:
    """Pasta real do programa, funcionando em .py e em .exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = app_dir()
OUT_DIR = APP_DIR / "certificados"
OUT_DIR.mkdir(exist_ok=True)

# ========== SUPORTE A EXECUTÁVEL ==========


def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base, rel_path)

# ========== CHAVES ==========


def _key_candidates():
    """Procura as chaves na pasta do programa e também na pasta atual do terminal."""
    paths = []
    for base in [APP_DIR, Path.cwd()]:
        priv = base / PRIVATE_KEY_NAME
        pub = base / PUBLIC_KEY_NAME
        if (priv, pub) not in paths:
            paths.append((priv, pub))
    return paths


def ensure_keys():
    """
    Mantido apenas para compatibilidade, mas agora NÃO gera chave nova automaticamente.

    Motivo: seu site autenticador já tem uma chave pública fixa. Se o programa gerar
    outra chave privada, o PDF será assinado com uma chave diferente e o site mostrará
    'assinatura não confere'.
    """
    for priv_path, pub_path in _key_candidates():
        if priv_path.exists() and pub_path.exists():
            return priv_path, pub_path

    raise FileNotFoundError(
        "Não encontrei private_key.ed25519 e public_key.ed25519.\n\n"
        "Para o site autenticador funcionar sem alteração, coloque os arquivos de chave "
        "na mesma pasta deste programa ou na pasta onde você está executando o comando.\n\n"
        "Importante: a chave privada precisa corresponder à chave pública já colocada no site."
    )


def load_keys():
    priv_path, pub_path = ensure_keys()

    priv_b64 = priv_path.read_text(encoding="utf-8").strip()
    signing_key = signing.SigningKey(base64.b64decode(priv_b64))
    verify_key = signing_key.verify_key

    generated_pub_b64 = base64.b64encode(bytes(verify_key)).decode("utf-8")

    # Atualiza/cria o public_key.ed25519 ao lado da chave privada, se necessário.
    try:
        pub_path.write_text(generated_pub_b64, encoding="utf-8")
    except Exception:
        pass

    if generated_pub_b64 != EXPECTED_PUBLIC_KEY_B64:
        raise ValueError(
            "A chave privada encontrada NÃO corresponde à chave pública do site autenticador.\n\n"
            f"Chave pública gerada pela sua private_key: {generated_pub_b64}\n"
            f"Chave pública que está no site: {EXPECTED_PUBLIC_KEY_B64}\n\n"
            "Para não mexer no site, use a private_key.ed25519 correta, ou então substitua "
            "a chave pública do site por essa chave gerada."
        )

    return signing_key, verify_key

# ========== ASSINATURA ==========


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def b64url_decode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def compact_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def sign_payload(signing_key: signing.SigningKey, payload: dict) -> str:
    data = compact_json(payload).encode("utf-8")
    sig = signing_key.sign(data).signature
    return b64url(sig)


def short_code(signature_b64url: str) -> str:
    raw = b64url_decode(signature_b64url)
    digest = hashlib.sha256(raw).digest()
    return base64.b32encode(digest).decode("utf-8").replace("=", "")[:10]

# ========== HELPERS ==========


def get_curso_config(curso_key: str) -> Dict[str, object]:
    if curso_key not in CURSOS:
        raise ValueError("Curso inválido. Selecione um curso cadastrado.")
    return CURSOS[curso_key]


def get_background_path(curso_cfg: Dict[str, object]) -> str:
    """Retorna APENAS o fundo específico do curso.

    Na versão Flask, não usamos fallback para evitar gerar certificado
    com o modelo antigo por engano.
    """
    bg = str(curso_cfg.get("background", "") or "")
    if not bg:
        raise FileNotFoundError(
            "Nenhuma imagem de fundo configurada para este curso.")
    if not os.path.exists(resource_path(bg)):
        raise FileNotFoundError(
            f"Imagem de fundo não encontrada: {bg}\n"
            "Coloque essa imagem na mesma pasta do app.py/gerador_certificado.py."
        )
    return bg


def build_validation_url(data_b64u: str) -> Optional[str]:
    base = (BASE_VALIDATION_URL or "").strip()
    if base.lower().startswith("http"):
        base = base.rstrip("/") + "/"
        return f"{base}?data={data_b64u}"
    return None


def register_fonts():
    if FONT_TITULO_ITALICO and os.path.exists(resource_path(FONT_TITULO_ITALICO)):
        pdfmetrics.registerFont(
            TTFont("TitItalic", resource_path(FONT_TITULO_ITALICO)))
    if FONT_TEXTO_ITALICO and os.path.exists(resource_path(FONT_TEXTO_ITALICO)):
        pdfmetrics.registerFont(
            TTFont("TxtItalic", resource_path(FONT_TEXTO_ITALICO)))
    if FONT_NEGRITO_ITALICO and os.path.exists(resource_path(FONT_NEGRITO_ITALICO)):
        pdfmetrics.registerFont(
            TTFont("BoldItalic", resource_path(FONT_NEGRITO_ITALICO)))


def font_exists(name: str) -> bool:
    return name in pdfmetrics.getRegisteredFontNames()


def draw_background(c, bg_path: str, page_w: float, page_h: float):
    bg_full = resource_path(bg_path)
    if not bg_path or not os.path.exists(bg_full):
        return
    img = Image.open(bg_full).convert("RGB")
    img = img.resize((int(page_w), int(page_h)), Image.LANCZOS)
    c.drawImage(ImageReader(img), 0, 0, width=page_w,
                height=page_h, mask='auto')


def make_qr_image(data: str) -> Image.Image:
    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=QR_BOX_SIZE, border=QR_BORDER
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def validar_data_br(data: str, nome_campo: str) -> str:
    data = data.strip()
    try:
        datetime.datetime.strptime(data, "%d/%m/%Y")
    except ValueError:
        raise ValueError(f"{nome_campo} inválida. Use o formato DD/MM/AAAA.")
    return data


# ---- Quebra de linha com largura em pontos + centralização

def wrap_text(text: str, font_name: str, font_size: int, max_width: float):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(test, font_name, font_size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_center_wrapped(c: canvas.Canvas, text: str, font_name: str, font_size: int,
                        x_center: float, y_start: float, max_width: float, leading: float) -> float:
    c.setFont(font_name, font_size)
    lines = wrap_text(text, font_name, font_size, max_width)
    y = y_start
    for line in lines:
        c.drawCentredString(x_center, y, line)
        y -= leading
    return y


def split_two_columns(items: List[str]):
    meio = (len(items) + 1) // 2
    return items[:meio], items[meio:]

# ========== LAYOUT DA FRENTE ==========


def draw_front(c: canvas.Canvas, page_w: float, page_h: float,
               nome_aluno: str, data_inicio: str, data_fim: str,
               cert_id: str, codigo_curto: str,
               qr_img: Image.Image, curso_cfg: Dict[str, object]):
    safe = 45
    branco = colors.white
    x_center = page_w / 2
    content_width = page_w - 2*safe

    curso_nome = str(curso_cfg["nome"])
    carga_horaria = str(curso_cfg.get("carga_horaria", CARGA_HORARIA_PADRAO))

    # Definições de fontes (itálico)
    title_font = "TitItalic" if font_exists(
        "TitItalic") else "Helvetica-Oblique"
    body_font = "TxtItalic" if font_exists(
        "TxtItalic") else "Helvetica-Oblique"
    name_font = "BoldItalic" if font_exists("BoldItalic") else body_font

    # Pré-calcular blocos
    preface_text = "Certificamos que, para os devidos fins, o aluno(a)"
    main_text = (
        f"concluiu o curso {curso_nome}, ministrado por {PROFESSOR}, "
        f"realizado no período de {data_inicio} a {data_fim}, "
        f"com carga horária de {carga_horaria}"
    )
    pre_lines = wrap_text(preface_text, body_font, 20, content_width)
    name_lines = wrap_text(nome_aluno,    name_font, 36, content_width)
    main_lines = wrap_text(main_text,     body_font, 20, content_width)

    # Métricas de altura
    leading_pref = 26
    leading_name = 38
    leading_main = 26
    gap1 = 10
    gap2 = 8
    block_height = (len(pre_lines)*leading_pref) + gap1 + (len(name_lines)
                                                           * leading_name) + gap2 + (len(main_lines)*leading_main)

    # Centro vertical do bloco "Certificamos..."
    block_center_y = page_h / 2
    y_block_top = block_center_y + (block_height / 2)

    # TÍTULO acima do bloco
    TITLE_ABOVE_OFFSET = 70
    c.setFillColor(branco)
    c.setFont(title_font, 48)
    c.drawCentredString(x_center, y_block_top +
                        TITLE_ABOVE_OFFSET, "CERTIFICADO")

    # Bloco central
    y = y_block_top
    c.setFont(body_font, 20)
    for line in pre_lines:
        c.drawCentredString(x_center, y, line)
        y -= leading_pref

    y -= gap1
    c.setFont(name_font, 36)
    for line in name_lines:
        c.drawCentredString(x_center, y, line)
        y -= leading_name

    y -= gap2
    c.setFont(body_font, 20)
    for line in main_lines:
        c.drawCentredString(x_center, y, line)
        y -= leading_main

    # Rodapé inferior esquerdo
    c.setFont(body_font, 11)
    left_x = safe
    foot_y = 52
    c.drawString(left_x,  foot_y + 24, f"CNPJ: {CNPJ}")
    c.drawString(left_x,  foot_y + 10, f"ID do certificado: {cert_id}")
    c.drawString(left_x,  foot_y - 4,
                 f"Código de autenticidade: {codigo_curto}")

    # QR no rodapé direito
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_w = QR_PIXEL_SIZE_FRONT
    qr_h = QR_PIXEL_SIZE_FRONT
    qr_x = page_w - qr_w - safe - 105
    qr_y = safe - 10
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, qr_w, qr_h, mask='auto')
    c.setFont(body_font, 10)
    c.drawCentredString(qr_x + qr_w/2, qr_y + qr_h + 10, "Valide com QR Code")


# ========== LAYOUT DO VERSO ==========

def draw_back(c: canvas.Canvas, page_w: float, page_h: float, curso_cfg: Dict[str, object]):
    safe = 45
    branco = colors.white
    title_font = "TitItalic" if font_exists(
        "TitItalic") else "Helvetica-Oblique"
    list_font = "TxtItalic" if font_exists(
        "TxtItalic") else "Helvetica-Oblique"

    conteudo = list(curso_cfg.get("conteudo", []))
    conteudo_esq, conteudo_dir = split_two_columns(conteudo)

    c.setFillColor(branco)
    c.setFont(title_font, 28)
    c.drawString(safe, page_h - 120, "CONTEÚDO PROGRAMÁTICO")

    c.setFont(list_font, 16)
    col_gap = 40
    col_w = (page_w - 2*safe - col_gap) / 2.0
    x_left = safe
    x_right = safe + col_w + col_gap
    y_start = page_h - 185

    # Ajusta levemente o espaçamento conforme a quantidade de itens.
    max_items_col = max(len(conteudo_esq), len(conteudo_dir), 1)
    available_h = y_start - 55
    line_h = min(26, max(19, available_h / max_items_col))

    bullet = u"\u2022 "
    y = y_start
    for item in conteudo_esq:
        c.drawString(x_left, y, f"{bullet}{item}")
        y -= line_h

    y = y_start
    for item in conteudo_dir:
        c.drawString(x_right, y, f"{bullet}{item}")
        y -= line_h

# ========== GERAÇÃO DO PDF ==========


def sanitize_filename_component(s: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = ''.join(ch for ch in s if ch not in invalid)
    return ' '.join(cleaned.split())


def gerar_pdf(nome_aluno: str, data_inicio: str, data_fim: str,
              output_path: Optional[str] = None, curso_key: str = CURSO_PADRAO):
    curso_cfg = get_curso_config(curso_key)
    curso_nome = str(curso_cfg["nome"])
    carga_horaria = str(curso_cfg.get("carga_horaria", CARGA_HORARIA_PADRAO))
    horas_num = ''.join(ch for ch in carga_horaria if ch.isdigit()) or "60"

    signing_key, _ = load_keys()
    cert_id = str(uuid.uuid4())
    data_inicio = validar_data_br(data_inicio, "Data de início")
    data_fim = validar_data_br(data_fim, "Data de fim")
    data_conclusao = f"{data_inicio} a {data_fim}"

    # Mantém compatibilidade com o site autenticador antigo:
    # o campo "d" continua sendo a data de conclusão,
    # mas agora recebe o período completo do curso.
    # A validação continua a mesma; apenas o campo "c" muda conforme o curso escolhido.
    payload = {"v": 1, "id": cert_id, "n": nome_aluno,
               "c": curso_nome, "d": data_conclusao, "hrs": horas_num}
    assinatura = sign_payload(signing_key, payload)
    codigo_curto = short_code(assinatura)

    data_pack = compact_json({**payload, "s": assinatura})
    data_b64u = b64url(data_pack.encode("utf-8"))
    url_valid = build_validation_url(data_b64u)
    qr_payload = url_valid if url_valid else data_pack
    qr_img = make_qr_image(qr_payload)

    page_w, page_h = landscape(A4)
    nome_clean = sanitize_filename_component(nome_aluno)
    curso_clean = sanitize_filename_component(curso_nome)
    out_name = f"certificado {curso_clean} - {nome_clean}.pdf"

    if output_path:
        out_path = Path(output_path)
        if out_path.suffix.lower() != ".pdf":
            out_path = out_path.with_suffix(".pdf")
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = OUT_DIR / out_name

    c = canvas.Canvas(str(out_path), pagesize=(page_w, page_h))
    c.setAuthor("EXPERT RADIOLOGIA")
    c.setTitle(f"Certificado - {curso_nome} - {nome_aluno}")
    c.setSubject("Certificado de Conclusão")
    c.setKeywords(compact_json({"data": payload, "sig": assinatura}))

    register_fonts()
    bg_path = get_background_path(curso_cfg)

    # Frente
    draw_background(c, bg_path, page_w, page_h)
    draw_front(c, page_w, page_h, nome_aluno,
               data_inicio, data_fim, cert_id, codigo_curto, qr_img, curso_cfg)
    c.showPage()

    # Verso
    draw_background(c, bg_path, page_w, page_h)
    draw_back(c, page_w, page_h, curso_cfg)
    c.showPage()

    c.save()

    print("\nManifest entry (opcional):")
    print(json.dumps({"id": cert_id, "code": codigo_curto,
          "data": data_b64u, "curso": curso_nome}, ensure_ascii=False))

    return out_path, cert_id, data_b64u

# ========== GERAÇÃO EM MEMÓRIA PARA FLASK ==========


def gerar_pdf_memoria(nome_aluno: str, data_inicio: str, data_fim: str, curso_key: str = CURSO_PADRAO):
    """Gera o certificado em memória para download pelo Flask.

    Esta função mantém a mesma lógica do gerar_pdf original:
    - Ed25519
    - payload/base64url
    - QR Code de validação
    - código curto de autenticidade
    - frente e verso
    - conteúdo programático

    Retorna: (buffer_pdf, cert_id, data_b64u, codigo_curto)
    """
    curso_cfg = get_curso_config(curso_key)
    curso_nome = str(curso_cfg["nome"])
    carga_horaria = str(curso_cfg.get("carga_horaria", CARGA_HORARIA_PADRAO))
    horas_num = ''.join(ch for ch in carga_horaria if ch.isdigit()) or "60"

    signing_key, _ = load_keys()
    cert_id = str(uuid.uuid4())
    data_inicio = validar_data_br(data_inicio, "Data de início")
    data_fim = validar_data_br(data_fim, "Data de fim")
    data_conclusao = f"{data_inicio} a {data_fim}"

    payload = {"v": 1, "id": cert_id, "n": nome_aluno,
               "c": curso_nome, "d": data_conclusao, "hrs": horas_num}
    assinatura = sign_payload(signing_key, payload)
    codigo_curto = short_code(assinatura)

    data_pack = compact_json({**payload, "s": assinatura})
    data_b64u = b64url(data_pack.encode("utf-8"))
    url_valid = build_validation_url(data_b64u)
    qr_payload = url_valid if url_valid else data_pack
    qr_img = make_qr_image(qr_payload)

    page_w, page_h = landscape(A4)
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
    c.setAuthor("EXPERT RADIOLOGIA")
    c.setTitle(f"Certificado - {curso_nome} - {nome_aluno}")
    c.setSubject("Certificado de Conclusão")
    c.setKeywords(compact_json({"data": payload, "sig": assinatura}))

    register_fonts()
    bg_path = get_background_path(curso_cfg)

    # Frente
    draw_background(c, bg_path, page_w, page_h)
    draw_front(c, page_w, page_h, nome_aluno,
               data_inicio, data_fim, cert_id, codigo_curto, qr_img, curso_cfg)
    c.showPage()

    # Verso
    draw_background(c, bg_path, page_w, page_h)
    draw_back(c, page_w, page_h, curso_cfg)
    c.showPage()

    c.save()
    buffer.seek(0)
    return buffer, cert_id, data_b64u, codigo_curto
