from flask import Flask, request, redirect
import paho.mqtt.client as mqtt
from datetime import datetime

app = Flask(__name__)

ultima = "Aguardando dados..."
historico = []
status_acesso = "Aguardando"
ultima_tecla = "-"

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883

def hora_atual():
    return datetime.now().strftime("%H:%M:%S")

def on_connect(client, userdata, flags, rc):
    print("Conectado ao broker")
    client.subscribe("smartaccess/#")

def on_message(client, userdata, msg):
    global ultima, status_acesso, ultima_tecla

    topico = msg.topic
    valor = msg.payload.decode()

    mensagem = f"{topico}: {valor}"
    print(mensagem)

    ultima = mensagem

    if topico == "smartaccess/tecla":
        ultima_tecla = valor

    if topico == "smartaccess/acesso":
        if valor == "OK":
            status_acesso = "ACESSO LIBERADO"
        elif valor == "ERRO":
            status_acesso = "ACESSO NEGADO"
        elif valor == "REMOTO_OK":
            status_acesso = "LIBERADO REMOTAMENTE"

    historico.insert(0, {
        "hora": hora_atual(),
        "topico": topico,
        "valor": valor
    })

    if len(historico) > 20:
        historico.pop()

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.loop_start()

@app.route("/")
def home():
    linhas = ""

    for item in historico:
        classe = ""

        if item["valor"] == "OK" or item["valor"] == "REMOTO_OK":
            classe = "ok"
        elif item["valor"] == "ERRO":
            classe = "erro"

        linhas += f"""
        <tr>
            <td>{item["hora"]}</td>
            <td>{item["topico"]}</td>
            <td class="{classe}">{item["valor"]}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>SmartAccess Dashboard</title>

        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #0f172a;
                color: white;
            }}

            .container {{
                max-width: 1100px;
                margin: auto;
                padding: 30px;
            }}

            h1 {{
                text-align: center;
                font-size: 36px;
                margin-bottom: 30px;
            }}

            .grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }}

            .card {{
                background: #1e293b;
                border-radius: 16px;
                padding: 24px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.35);
            }}

            .card h2 {{
                color: #94a3b8;
                font-size: 16px;
                margin: 0 0 10px;
            }}

            .valor {{
                font-size: 24px;
                font-weight: bold;
            }}

            .ok {{
                color: #22c55e;
                font-weight: bold;
            }}

            .erro {{
                color: #ef4444;
                font-weight: bold;
            }}

            .botoes {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }}

            button {{
                padding: 16px;
                border: none;
                border-radius: 12px;
                font-size: 18px;
                cursor: pointer;
                font-weight: bold;
            }}

            .btn-liberar {{
                background: #22c55e;
                color: #052e16;
            }}

            .btn-liberar:hover {{
                background: #16a34a;
            }}

            .form-senha {{
                background: #1e293b;
                padding: 20px;
                border-radius: 16px;
            }}

            input {{
                width: 100%;
                padding: 14px;
                border-radius: 10px;
                border: none;
                margin-bottom: 12px;
                font-size: 16px;
            }}

            .btn-senha {{
                width: 100%;
                background: #2563eb;
                color: white;
            }}

            .btn-senha:hover {{
                background: #1d4ed8;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: #1e293b;
                border-radius: 16px;
                overflow: hidden;
            }}

            th, td {{
                padding: 14px;
                text-align: left;
                border-bottom: 1px solid #334155;
            }}

            th {{
                background: #334155;
                color: #cbd5e1;
            }}

            .alerta {{
                padding: 16px;
                border-radius: 12px;
                margin-bottom: 20px;
                font-weight: bold;
                text-align: center;
            }}

            .alerta-ok {{
                background: #14532d;
                color: #bbf7d0;
            }}

            .alerta-erro {{
                background: #7f1d1d;
                color: #fecaca;
            }}

            .footer {{
                text-align: center;
                margin-top: 30px;
                color: #94a3b8;
            }}
        </style>

        <meta http-equiv="refresh" content="2">
    </head>

    <body>
        <div class="container">
            <h1>🔐 SmartAccess IoT Dashboard</h1>

            <div class="grid">
                <div class="card">
                    <h2>Status do acesso</h2>
                    <div class="valor">{status_acesso}</div>
                </div>

                <div class="card">
                    <h2>Última tecla</h2>
                    <div class="valor">{ultima_tecla}</div>
                </div>

                <div class="card">
                    <h2>Último evento</h2>
                    <div class="valor">{ultima}</div>
                </div>
            </div>

            {"<div class='alerta alerta-erro'>⚠️ Tentativa de acesso negada!</div>" if status_acesso == "ACESSO NEGADO" else ""}
            {"<div class='alerta alerta-ok'>✅ Acesso liberado com sucesso!</div>" if status_acesso == "ACESSO LIBERADO" else ""}
            {"<div class='alerta alerta-ok'>🌐 Acesso liberado remotamente!</div>" if status_acesso == "LIBERADO REMOTAMENTE" else ""}

            <div class="botoes">
                <form action="/liberar" method="post">
                    <button class="btn-liberar" type="submit">Liberar acesso remotamente</button>
                </form>

                <div class="form-senha">
                    <form action="/senha" method="post">
                        <input type="text" name="nova_senha" placeholder="Nova senha" required>
                        <button class="btn-senha" type="submit">Alterar senha</button>
                    </form>
                </div>
            </div>

            <h2>Histórico de eventos</h2>

            <table>
                <thead>
                    <tr>
                        <th>Hora</th>
                        <th>Tópico</th>
                        <th>Valor</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas}
                </tbody>
            </table>

            <div class="footer">
                ESP32 + MQTT + Python + Web
            </div>
        </div>
    </body>
    </html>
    """

    return html

@app.route("/liberar", methods=["POST"])
def liberar():
    mqtt_client.publish("smartaccess/comando", "LIBERAR")
    return redirect("/")

@app.route("/senha", methods=["POST"])
def alterar_senha():
    nova_senha = request.form.get("nova_senha")

    if nova_senha:
        mqtt_client.publish("smartaccess/senha", nova_senha)

    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)