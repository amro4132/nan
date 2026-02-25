import os, requests
from flask import Flask, request, jsonify

app = Flask(__name__)
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')
API_SECRET_KEY = "ALPHA_SECRET_2026"

@app.route('/gate', methods=['POST'])
def gate():
    if request.headers.get('X-Auth-Token') != API_SECRET_KEY:
        return jsonify({"status": "unauthorized"}), 403
    data = request.json
    payload = {
        "username": "Sovereign Sentinel v2",
        "embeds": [{"title": "📦 استلام بيانات", "description": data.get('content', ''), "color": 15158332}]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
