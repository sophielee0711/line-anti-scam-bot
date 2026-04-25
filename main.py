from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent
import os
import re

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

# 詐騙關鍵字清單
SCAM_KEYWORDS = [
    "報名", "課程", "投資", "獲利", "賺錢", "月入", "被動收入",
    "加入我們", "限時", "名額有限", "保證獲利", "穩定收益",
    "直銷", "老師帶單", "跟單", "下單", "操盤", "飆股",
    "免費體驗", "試用", "點擊連結", "掃碼", "立即加入"
]

# 可疑連結 pattern
URL_PATTERN = re.compile(
    r'(https?://|www\.|(bit\.ly|goo\.gl|tinyurl|reurl|pse\.is|lihi)\S+)',
    re.IGNORECASE
)

def is_suspicious(text):
    text_lower = text.lower()
    has_url = bool(URL_PATTERN.search(text))
    has_keyword = any(kw in text for kw in SCAM_KEYWORDS)
    return has_url or has_keyword, has_url, has_keyword

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 只處理群組訊息
    if event.source.type not in ['group', 'room']:
        return

    text = event.message.text
    user_id = event.source.user_id
    group_id = event.source.group_id if event.source.type == 'group' else event.source.room_id

    suspicious, has_url, has_keyword = is_suspicious(text)

    if suspicious:
        try:
            profile = line_bot_api.get_group_member_profile(group_id, user_id)
            name = profile.display_name
        except:
            name = "某成員"

        warning_parts = []
        if has_url:
            warning_parts.append("包含連結")
        if has_keyword:
            warning_parts.append("包含可疑關鍵字")

        warning = (
            f"⚠️【防詐警報】⚠️\n"
            f"偵測到 {name} 發送可疑訊息！\n"
            f"原因：{'、'.join(warning_parts)}\n\n"
            f"請管理員注意！如確認為廣告或詐騙，請手動移除該成員。\n"
            f"🚫 請勿點擊任何不明連結！"
        )

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=warning)
        )

@handler.add(JoinEvent)
def handle_join(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="大家好！我是李氏小管家防詐機器人 🛡️\n我會自動偵測可疑連結和詐騙關鍵字，保護大家的安全！"
        )
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
