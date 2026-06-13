from flask import Flask, render_template, request, send_file, jsonify
import psycopg2
import tempfile
import os
from datetime import date, timedelta, datetime
from gerador_certificado import gerar_pdf

app = Flask(__name__)

CURSOS = {
    "Angiotomografia": "Angiotomografia",
    "Ressonância Magnética": "Ressonância Magnética",
    "Tomografia 2.0 + Simulador": "Tomografia 2.0 + Simulador"
}

PRODUTOS_HOTMART = {
    "Angiotomografia": "Angiotomografia",
    "Ressonância Magnética": "Ressonância Magnética",
    "Tomografia 2.0 + Simulador": "Tomografia 2.0 + Simulador",
    "Produto test postback2": "Ressonância Magnética"
}


def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "aws-1-us-east-1.pooler.supabase.com"),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres.cwkdffwkkdgdcvwzparh"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT", "5432"),
        sslmode="require"
    )


@app.route("/")
def home():
    return render_template(
        "index.html",
        cursos=CURSOS,
        curso_selecionado=None
    )


@app.route("/curso/<path:curso>")
def pagina_curso(curso):
    if curso not in CURSOS:
        return "Curso não encontrado", 404

    return render_template(
        "index.html",
        cursos=CURSOS,
        curso_selecionado=curso
    )


@app.route("/ressonancia")
def pagina_ressonancia():
    return render_template(
        "index.html",
        cursos=CURSOS,
        curso_selecionado="Ressonância Magnética"
    )


@app.route("/angiotomografia")
def pagina_angiotomografia():
    return render_template(
        "index.html",
        cursos=CURSOS,
        curso_selecionado="Angiotomografia"
    )


@app.route("/tomografia20")
def pagina_tomografia20():
    return render_template(
        "index.html",
        cursos=CURSOS,
        curso_selecionado="Tomografia 2.0 + Simulador"
    )


@app.route("/webhook/hotmart", methods=["POST"])
def webhook_hotmart():
    print("====================================")
    print("WEBHOOK HOTMART RECEBIDO")
    print("JSON:", request.get_json(silent=True))
    print("====================================")

    dados = request.get_json(silent=True)

    if not dados:
        return jsonify({"erro": "JSON inválido ou vazio"}), 400

    evento = dados.get("event")

    if evento != "PURCHASE_APPROVED":
        return jsonify({"status": "evento ignorado", "evento": evento}), 200

    data = dados.get("data", {})

    buyer = data.get("buyer", {})
    product = data.get("product", {})
    purchase = data.get("purchase", {})

    nome = buyer.get("name")
    email = buyer.get("email")
    produto_hotmart = product.get("name")
    data_compra = purchase.get("approved_date") or purchase.get("order_date")

    if isinstance(data_compra, (int, float)):
        data_compra = datetime.fromtimestamp(data_compra / 1000)

    if not nome or not email or not produto_hotmart:
        return jsonify({
            "erro": "nome, email ou produto ausente",
            "nome": nome,
            "email": email,
            "produto": produto_hotmart
        }), 400

    nome = nome.strip()
    email = email.strip().lower()
    produto_hotmart = produto_hotmart.strip()

    curso = PRODUTOS_HOTMART.get(produto_hotmart, produto_hotmart)

    if curso not in CURSOS:
        return jsonify({
            "erro": "curso/produto não reconhecido",
            "produto_hotmart": produto_hotmart,
            "curso_convertido": curso
        }), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id
        FROM alunos_autorizados
        WHERE LOWER(email) = %s AND curso = %s
        LIMIT 1
    """, (email, curso))

    aluno_existente = cursor.fetchone()

    if aluno_existente:
        cursor.execute("""
            UPDATE alunos_autorizados
            SET nome = %s,
                status_pagamento = %s,
                data_compra = COALESCE(%s, data_compra)
            WHERE id = %s
        """, (
            nome,
            "aprovado",
            data_compra,
            aluno_existente[0]
        ))
    else:
        cursor.execute("""
            INSERT INTO alunos_autorizados
            (nome, email, curso, status_pagamento, data_compra)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            nome,
            email,
            curso,
            "aprovado",
            data_compra
        ))

    conexao.commit()

    cursor.close()
    conexao.close()

    return jsonify({
        "status": "aluno autorizado salvo com sucesso",
        "nome": nome,
        "email": email,
        "curso": curso
    }), 200


@app.route("/gerar", methods=["POST"])
def gerar():
    email = request.form["email"].strip().lower()
    curso = request.form["curso"].strip()

    if curso not in CURSOS:
        return "Curso inválido."

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, nome, email, curso
        FROM alunos_autorizados
        WHERE LOWER(email) = %s
        AND curso = %s
        AND status_pagamento = 'aprovado'
        LIMIT 1
    """, (email, curso))

    aluno = cursor.fetchone()

    if not aluno:
        cursor.close()
        conexao.close()
        return "Aluno não encontrado ou não autorizado para este curso."

    aluno_id = aluno[0]
    nome = aluno[1]
    email_banco = aluno[2]
    curso_banco = aluno[3]

    data_final = date.today()
    data_inicio = data_final - timedelta(days=30)

    data_inicio_br = data_inicio.strftime("%d/%m/%Y")
    data_final_br = data_final.strftime("%d/%m/%Y")

    arquivo_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    caminho_pdf = arquivo_temp.name
    arquivo_temp.close()

    out_path, cert_id, data_b64u = gerar_pdf(
        nome_aluno=nome,
        data_inicio=data_inicio_br,
        data_fim=data_final_br,
        output_path=caminho_pdf,
        curso_key=curso_banco
    )

    cursor.execute("""
        INSERT INTO certificados_emitidos
        (aluno_id, nome, email, curso, data_inicio, data_final, codigo_autenticidade)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        aluno_id,
        nome,
        email_banco,
        curso_banco,
        data_inicio,
        data_final,
        cert_id
    ))

    conexao.commit()

    cursor.close()
    conexao.close()

    nome_arquivo = f"certificado_{nome.replace(' ', '_')}.pdf"

    return send_file(
        caminho_pdf,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)
