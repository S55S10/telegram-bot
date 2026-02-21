import json
import time
import requests
import os

TOKEN = "8202773408:AAGLbNJDAUWQ-5KjvPc7aZaRO4k29XZKG0Y"
API = f"https://api.telegram.org/bot{TOKEN}"

with open("/home/Ahmad3308/mysite/questions.json", "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)["questions"]

TOTAL = len(QUESTIONS)
TIME_LIMIT = 600
SAVE_FILE = "/home/Ahmad3308/mysite/user_progress.json"

def load_users():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users():
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

def ensure_keys(chat_id):
    if chat_id not in users:
        users[chat_id] = {}

    user = users[chat_id]

    if "index" not in user: user["index"] = 0
    if "score" not in user: user["score"] = 0
    if "start_from" not in user: user["start_from"] = 0
    if "lastTime" not in user: user["lastTime"] = time.time()
    if "waiting_jump" not in user: user["waiting_jump"] = False

    save_users()

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{API}/sendMessage", json=payload)

def send_controls(chat_id):
    markup = {
        "inline_keyboard": [
            [{"text": "🔄 بدء الاختبار من جديد", "callback_data": "new"}],
            [{"text": "➡️ الانتقال إلى سؤال", "callback_data": "jump"}],
            [{"text": "🛑 إيقاف الاختبار", "callback_data": "stop"}]
        ]
    }
    send_message(chat_id, "اختر:", markup)

def send_question(chat_id):
    ensure_keys(chat_id)
    user = users[chat_id]
    idx = user["index"]
    q = QUESTIONS[idx]

    if q["type"] == "multiple_choice":
        keyboard = [[{"text": opt, "callback_data": f"ans:{i+1}"}] for i, opt in enumerate(q["options"])]
    else:
        keyboard = [[
            {"text": "صح", "callback_data": "ans:1"},
            {"text": "خطأ", "callback_data": "ans:0"}
        ]]

    markup = {"inline_keyboard": keyboard}
    send_message(chat_id, f"سؤال ({idx+1}/{TOTAL}):\n\n{q['question']}", markup)

def start_new(chat_id):
    users[chat_id] = {
        "index": 0,
        "score": 0,
        "start_from": 0,
        "lastTime": time.time(),
        "waiting_jump": False
    }
    save_users()
    send_question(chat_id)

def jump_to(chat_id, number):
    ensure_keys(chat_id)

    number -= 1
    if number < 0 or number >= TOTAL:
        send_message(chat_id, "❌ رقم السؤال غير صحيح")
        return

    users[chat_id]["index"] = number
    users[chat_id]["start_from"] = number
    users[chat_id]["waiting_jump"] = False
    users[chat_id]["lastTime"] = time.time()
    save_users()
    send_question(chat_id)

def next_question(chat_id):
    ensure_keys(chat_id)
    user = users[chat_id]
    user["index"] += 1

    if user["index"] >= TOTAL:
        answered = user["index"] - user["start_from"]
        send_message(chat_id, f"🎉 انتهى الاختبار!\nنتيجتك: {user['score']} من {answered}")
        del users[chat_id]
        save_users()
        return

    save_users()
    send_question(chat_id)

# ---------------------------------------------------------
# 🔥 دالة الإجابة الجديدة مع تمييز الاختيارات + الحل
# ---------------------------------------------------------
def process_answer(chat_id, ans):
    ensure_keys(chat_id)
    user = users[chat_id]
    idx = user["index"]
    q = QUESTIONS[idx]

    now = time.time()
    if now - user["lastTime"] > TIME_LIMIT:
        answered = user["index"] - user["start_from"]
        send_message(chat_id, f"⏳ انتهى الوقت!\nنتيجتك: {user['score']} من {answered}")
        del users[chat_id]
        save_users()
        return

    user["lastTime"] = now

    # تحديد الإجابة الصحيحة
    if q["type"] == "multiple_choice":
        correct = q["answer"]
        correct_text = q["options"][correct - 1]
        is_correct = (int(ans) == correct)
    else:
        correct = 1 if q["answer"] else 0
        correct_text = "صح" if q["answer"] else "خطأ"
        is_correct = (int(ans) == correct)

    # حساب النتيجة
    if is_correct:
        user["score"] += 1
        result_msg = "✅ إجابة صحيحة"
    else:
        result_msg = "❌ إجابة خاطئة"

    # إعادة إرسال السؤال مع تمييز الإجابات
    review = f"🔍 مراجعة السؤال ({idx+1}/{TOTAL}):\n\n{q['question']}\n\n"

    if q["type"] == "multiple_choice":
        for i, opt in enumerate(q["options"], start=1):
            mark = ""
            if i == int(ans):
                mark = "🔸 (اختياري)"
            if i == correct:
                mark = "✔ (الإجابة الصحيحة)"
            review += f"- {opt} {mark}\n"
    else:
        user_choice = "صح" if ans == "1" else "خطأ"
        correct_choice = correct_text

        review += f"- اختيارك: {user_choice}\n"
        review += f"- الإجابة الصحيحة: {correct_choice}\n"

    # إضافة الشرح إن وجد
    if "solution" in q:
        review += f"\n📘 الشرح:\n{q['solution']}"
    elif "explanation" in q:
        review += f"\n📘 الشرح:\n{q['explanation']}"

    send_message(chat_id, f"{result_msg}\n\n{review}")

    next_question(chat_id)

# ---------------------------------------------------------

def get_updates(offset=None):
    return requests.get(f"{API}/getUpdates", params={"timeout": 100, "offset": offset}).json()

def run_bot():
    print("Bot is running CLEAN FIXED VERSION...")
    offset = None

    while True:
        updates = get_updates(offset)

        if "result" in updates:
            for update in updates["result"]:
                offset = update["update_id"] + 1

                if "message" in update:
                    chat_id = str(update["message"]["chat"]["id"])
                    text = update["message"].get("text", "").strip()

                    ensure_keys(chat_id)

                    if users[chat_id]["waiting_jump"]:
                        if text.isdigit():
                            jump_to(chat_id, int(text))
                        else:
                            send_message(chat_id, "❌ اكتب رقم فقط")
                        continue

                    send_controls(chat_id)
                    continue

                if "callback_query" in update:
                    chat_id = str(update["callback_query"]["message"]["chat"]["id"])
                    data = update["callback_query"]["data"]

                    ensure_keys(chat_id)

                    if data == "new":
                        start_new(chat_id)
                        continue

                    if data == "jump":
                        users[chat_id]["waiting_jump"] = True
                        save_users()
                        send_message(chat_id, "اكتب رقم السؤال الذي تريد الانتقال إليه:")
                        continue

                    if data == "stop":
                        user = users[chat_id]
                        answered = user["index"] - user["start_from"]
                        send_message(chat_id, f"تم إيقاف الاختبار.\nنتيجتك: {user['score']} من {answered}")
                        del users[chat_id]
                        save_users()
                        continue

                    if data.startswith("ans:"):
                        ans = data.split(":")[1]
                        process_answer(chat_id, ans)
                        continue

run_bot()
