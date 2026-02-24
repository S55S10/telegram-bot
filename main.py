import json
import time
import requests
import os
from flask import Flask, request

app = Flask(__name__)

TOKEN = "8202773408:AAGLbNJDAUWQ-5KjvPc7aZaRO4k29XZKG0Y"
API = f"https://api.telegram.org/bot{TOKEN}"

QUESTIONS_FILE = "questions.json"
SAVE_FILE = "user_progress.json"

# تحميل الأسئلة
with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

TOTAL = len(QUESTIONS)
TIME_LIMIT = 600  # 10 دقائق


# ------------------ إدارة المستخدمين ------------------

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
    user.setdefault("index", 0)
    user.setdefault("score", 0)
    user.setdefault("start_from", 0)
    user.setdefault("lastTime", time.time())
    user.setdefault("waiting_jump", False)
    user.setdefault("last_message_id", None)

    save_users()


# ------------------ إرسال الرسائل ------------------

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return requests.post(f"{API}/sendMessage", json=payload).json()


def answer_callback(callback_id):
    requests.post(f"{API}/answerCallbackQuery", json={
        "callback_query_id": callback_id
    })


# ------------------ لوحة التحكم ------------------

def send_controls(chat_id):
    markup = {
        "inline_keyboard": [
            [{"text": "🔄 بدء الاختبار من جديد", "callback_data": "new"}],
            [{"text": "➡️ الانتقال إلى سؤال", "callback_data": "jump"}],
            [{"text": "🛑 إيقاف الاختبار", "callback_data": "stop"}]
        ]
    }
    send_message(chat_id, "اختر:", markup)


# ------------------ إرسال السؤال ------------------

def send_question(chat_id):
    ensure_keys(chat_id)
    user = users[chat_id]
    idx = user["index"]

    if idx >= TOTAL:
        return

    q = QUESTIONS[idx]

    if q["type"] == "multiple_choice":
        keyboard = [
            [{"text": opt, "callback_data": f"ans:{i+1}"}]
            for i, opt in enumerate(q["options"])
        ]
    else:
        keyboard = [[
            {"text": "صح", "callback_data": "ans:1"},
            {"text": "خطأ", "callback_data": "ans:0"}
        ]]

    markup = {"inline_keyboard": keyboard}

    res = requests.post(f"{API}/sendMessage", json={
        "chat_id": chat_id,
        "text": f"سؤال ({idx+1}/{TOTAL}):\n\n{q['question']}",
        "reply_markup": markup
    }).json()

    if res.get("ok"):
        users[chat_id]["last_message_id"] = res["result"]["message_id"]
        save_users()


# ------------------ بدء اختبار جديد ------------------

def start_new(chat_id):
    users[chat_id] = {
        "index": 0,
        "score": 0,
        "start_from": 0,
        "lastTime": time.time(),
        "waiting_jump": False,
        "last_message_id": None
    }
    save_users()
    send_question(chat_id)


# ------------------ الانتقال لسؤال ------------------

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


# ------------------ السؤال التالي ------------------

def next_question(chat_id):
    ensure_keys(chat_id)
    user = users[chat_id]
    user["index"] += 1

    if user["index"] >= TOTAL:
        answered = user["index"] - user["start_from"]
        send_message(chat_id, f"🎉 انتهى الاختبار!\nنتيجتك: {user['score']} من {answered}")
        users.pop(chat_id, None)
        save_users()
        return

    save_users()
    send_question(chat_id)


# ------------------ معالجة الإجابة ------------------

def process_answer(chat_id, ans):
    ensure_keys(chat_id)
    user = users[chat_id]
    idx = user["index"]

    if idx >= TOTAL:
        return

    q = QUESTIONS[idx]

    now = time.time()
    if now - user["lastTime"] > TIME_LIMIT:
        answered = user["index"] - user["start_from"]
        send_message(chat_id, f"⏳ انتهى الوقت!\nنتيجتك: {user['score']} من {answered}")
        users.pop(chat_id, None)
        save_users()
        return

    user["lastTime"] = now

    # تحديد الإجابة الصحيحة
    if q["type"] == "multiple_choice":
        correct = q["answer"]
        is_correct = (int(ans) == correct)
    else:
        correct = 1 if q["answer"] else 0
        is_correct = (int(ans) == correct)

    if is_correct:
        user["score"] += 1

    # تعديل الأزرار
    keyboard = []

    if q["type"] == "multiple_choice":
        for i, opt in enumerate(q["options"], start=1):
            if i == correct:
                text = f"{opt} ✔️"
            elif i == int(ans):
                text = f"{opt} ❌"
            else:
                text = opt
            keyboard.append([{"text": text, "callback_data": "done"}])
    else:
        keyboard = [[
            {"text": f"صح {'✔️' if correct == 1 else ''}", "callback_data": "done"},
            {"text": f"خطأ {'✔️' if correct == 0 else ''}", "callback_data": "done"}
        ]]

    try:
        requests.post(f"{API}/editMessageReplyMarkup", json={
            "chat_id": chat_id,
            "message_id": user["last_message_id"],
            "reply_markup": {"inline_keyboard": keyboard}
        })
    except:
        pass

    next_question(chat_id)


# ------------------ Webhook ------------------

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "").strip()

        ensure_keys(chat_id)

        if users[chat_id]["waiting_jump"]:
            if text.isdigit():
                jump_to(chat_id, int(text))
            else:
                send_message(chat_id, "❌ اكتب رقم فقط")
            return "ok"

        send_controls(chat_id)
        return "ok"

    if "callback_query" in update:
        chat_id = str(update["callback_query"]["message"]["chat"]["id"])
        data = update["callback_query"]["data"]
        callback_id = update["callback_query"]["id"]

        answer_callback(callback_id)
        ensure_keys(chat_id)

        if data == "new":
            start_new(chat_id)
        elif data == "jump":
            users[chat_id]["waiting_jump"] = True
            save_users()
            send_message(chat_id, "اكتب رقم السؤال الذي تريد الانتقال إليه:")
        elif data == "stop":
            user = users[chat_id]
            answered = user["index"] - user["start_from"]
            send_message(chat_id, f"تم إيقاف الاختبار.\nنتيجتك: {user['score']} من {answered}")
            users.pop(chat_id, None)
            save_users()
        elif data.startswith("ans:"):
            ans = data.split(":")[1]
            process_answer(chat_id, ans)

        return "ok"

    return "ok"


if __name__ == "__main__":
    app.run()
