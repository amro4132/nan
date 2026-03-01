# server.py - سيرفر مع مسار /here لعرض البيانات
# تشغيل: python server.py

from flask import Flask, request, jsonify, render_template_string
import requests
import os
from datetime import datetime

app = Flask(__name__)

# ==================== إعدادات Discord ====================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1477005798855933965/UGo7IuLJ2B-cp00CizKypWijgIOs5_95klXi75FyNw9C0xKSDchP-8Om5kDSRHIoaVbe"

# ==================== تخزين مؤقت للبيانات ====================
received_data = []

# ==================== صفحة رئيسية ====================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "server": "Test Server",
        "time": datetime.now().isoformat(),
        "endpoints": {
            "/": "هذه الصفحة",
            "/api/data (POST)": "استقبال البيانات من العميل",
            "/here (GET)": "عرض كل البيانات المستلمة"
        }
    })

# ==================== مسار عرض البيانات المستلمة ====================
@app.route('/here', methods=['GET'])
def show_data():
    # HTML بسيط لعرض البيانات
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>البيانات المستلمة</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; direction: rtl; background: #f0f0f0; margin: 20px; }
            .container { max-width: 800px; margin: auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
            .data-item { background: #f9f9f9; margin: 10px 0; padding: 15px; border-radius: 5px; border-right: 5px solid #4CAF50; }
            .timestamp { color: #666; font-size: 0.9em; }
            .client { color: #2196F3; font-weight: bold; }
            .content { background: #e8f5e8; padding: 10px; margin-top: 10px; border-radius: 3px; font-family: monospace; }
            .empty { color: #999; text-align: center; padding: 50px; }
            .stats { background: #4CAF50; color: white; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📥 البيانات المستلمة من العملاء</h1>
            <div class="stats">
                <strong>إجمالي الرسائل:</strong> {{ data|length }} | 
                <strong>آخر تحديث:</strong> {{ now }}
            </div>
            
            {% if data %}
                {% for item in data|reverse %}
                <div class="data-item">
                    <div class="timestamp">🕒 {{ item.time }}</div>
                    <div class="client">🖥️ العميل: {{ item.client }}</div>
                    <div class="content">📝 {{ item.content }}</div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty">
                    <h2>🚫 لا توجد بيانات بعد</h2>
                    <p>انتظر حتى يرسل العملاء بياناتهم</p>
                </div>
            {% endif %}
        </div>
    </body>
    </html>
    """
    
    return render_template_string(html_template, data=received_data, now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# ==================== استقبال البيانات ====================
@app.route('/api/data', methods=['POST'])
def receive_data():
    try:
        # استقبال البيانات
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data"}), 400
        
        # استخراج المعلومات
        client_id = data.get('id', 'unknown')
        content = data.get('content', 'No content')
        
        # حفظ البيانات
        received_data.append({
            'client': client_id,
            'content': content,
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # طباعة في الكونسول
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📥 استقبال من {client_id}")
        print(f"📝 المحتوى: {content}")
        print(f"📊 إجمالي الرسائل: {len(received_data)}")
        
        # إرسال إلى Discord
        try:
            discord_msg = f"**📡 تم الاستقبال**\n"
            discord_msg += f"```\n"
            discord_msg += f"العميل: {client_id}\n"
            discord_msg += f"الوقت: {datetime.now().isoformat()}\n"
            discord_msg += f"البيانات: {content}\n"
            discord_msg += f"```"
            
            response = requests.post(DISCORD_WEBHOOK, json={"content": discord_msg})
            if response.status_code == 204 or response.status_code == 200:
                print(f"✅ تم الإرسال إلى Discord")
            else:
                print(f"❌ فشل Discord: {response.status_code}")
        except Exception as e:
            print(f"❌ خطأ Discord: {e}")
        
        return jsonify({
            "status": "success", 
            "received": content,
            "total_messages": len(received_data)
        }), 200
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return jsonify({"error": str(e)}), 500

# ==================== مسح البيانات ====================
@app.route('/clear', methods=['GET'])
def clear_data():
    received_data.clear()
    return jsonify({"status": "cleared", "total": 0})

# ==================== تشغيل السيرفر ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*60)
    print("🚀 سيرفر الاختبار - Test Server")
    print("="*60)
    print(f"📡 Discord Webhook: {DISCORD_WEBHOOK[:50]}...")
    print(f"📍 الرابط الرئيسي: http://localhost:{port}")
    print(f"📍 استقبال البيانات: http://localhost:{port}/api/data (POST)")
    print(f"📍 عرض البيانات: http://localhost:{port}/here (GET)")
    print(f"📍 مسح البيانات: http://localhost:{port}/clear (GET)")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port, debug=True)
