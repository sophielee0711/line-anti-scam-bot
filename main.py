from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    MemberJoinedEvent
)
import os, re, json

app = Flask(__name__)
line_bot_api = LineBotApi(os.environ.get("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("CHANNEL_SECRET"))

# ===== 設定你的 User ID =====
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID", "")

# ===== 名單儲存（記憶體，重啟會清空） =====
whitelist = set()
blacklist = set()

# ===== 詐騙關鍵字 =====
SCAM_KEYWORDS = [
    "報名", "課程", "投資", "獲利", "賺錢", "月入", "被動收入",
    "加入我們", "限時", "名額有限", "保證獲利", "穩定收益",
    "直銷", "老師帶單", "跟單", "下單", "操盤", "飆股",
    "免費體驗", "試用", "點擊連結", "掃碼", "立即加入"
]

URL_PATTERN = re.compile(
    r'(https?://|www\.|(bit\.ly|goo\.gl|tinyurl|reurl|pse\.is|lihi)\S+)',
    re.IGNORECASE
)

def is_suspicious(text):
    has_url = bool(URL_PATTERN.search(text))
    has_keyword = any(kw in text for kw in SCAM_KEYWORDS)
    return has_url or has_keyword, has_url, has_keyword

def notify_admin(message):
    if ADMIN_USER_ID:
        try:
            line_bot_api.push_message(
                ADMIN_USER_ID,
                TextSendMessage(text=message)
            )
        except Exception as e:
            print(f"通知管理員失敗: {e}")

def get_name(group_id, user_id, source_type):
    try:
        if source_type == 'group':
            profile = line_bot_api.get_group_member_profile(group_id, user_id)
        else:
            profile = line_bot_api.get_room_member_profile(group_id, user_id)
        return profile.display_name
    except:
        return user_id
@app.route("/", methods=['GET'])
def home():
    return 'OK', 200
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# ===== 處理文字訊息 =====
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    source_type = event.source.type

    print(f"userId: {user_id}")  # 印出 User ID

    # 管理員私訊指令
    if source_type == 'user':
        if text.startswith("/白名單加入 "):
            uid = text.replace("/白名單加入 ", "").strip()
            whitelist.add(uid)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已將 {uid} 加入白名單"))
        elif text.startswith("/白名單移除 "):
            uid = text.replace("/白名單移除 ", "").strip()
            whitelist.discard(uid)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已將 {uid} 移出白名單"))
        elif text.startswith("/黑名單加入 "):
            uid = text.replace("/黑名單加入 ", "").strip()
            blacklist.add(uid)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已將 {uid} 加入黑名單"))
        elif text.startswith("/黑名單移除 "):
            uid = text.replace("/黑名單移除 ", "").strip()
            blacklist.discard(uid)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已將 {uid} 移出黑名單"))
        elif text == "/名單查詢":
            msg = f"📋 白名單：{len(whitelist)} 人\n{chr(10).join(whitelist) or '（空）'}\n\n🚫 黑名單：{len(blacklist)} 人\n{chr(10).join(blacklist) or '（空）'}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        elif text == "/我的ID":
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"你的 User ID 是：\n{user_id}"))
        return

    # 群組訊息處理
    if source_type not in ['group', 'room']:
        return

    group_id = event.source.group_id if source_type == 'group' else event.source.room_id

    # 白名單直接跳過
    if user_id in whitelist:
        return

    # 黑名單成員發訊息
    if user_id in blacklist:
        name = get_name(group_id, user_id, source_type)
        notify_admin(f"🚨【黑名單警報】\n「{name}」正在群組發訊息！\nUser ID：{user_id}\n請盡快手動踢除！")
        return

    # 偵測可疑訊息
    suspicious, has_url, has_keyword = is_suspicious(text)
    if suspicious:
        name = get_name(group_id, user_id, source_type)
        reasons = []
        if has_url:
            reasons.append("包含連結")
        if has_keyword:
            reasons.append("包含可疑關鍵字")

        # 群組警告
        if has_url:
            warning_msg = "⚠️【防詐提醒】\n有人分享了連結，請謹慎確認來源！\n🚫 請勿輕易點擊不明連結！"
        else:
            warning_msg = "⚠️【防詐提醒】\n偵測到可疑內容，請大家注意！\n🚫 如有疑慮請向管理員反映！"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=warning_msg)
        )

        # 私訊管理員
        notify_admin(f"⚠️【可疑訊息通知】\n發送者：{name}\nUser ID：{user_id}\n原因：{'、'.join(reasons)}\n內容：{text[:100]}")

# ===== 黑名單成員加入群組 =====
@handler.add(MemberJoinedEvent)
def handle_member_join(event):
    members = event.joined.members
    source_type = event.source.type
    group_id = event.source.group_id if source_type == 'group' else event.source.room_id

    for member in members:
        user_id = member.user_id
        if user_id in blacklist:
            name = get_name(group_id, user_id, source_type)
            notify_admin(f"🚨【黑名單加入警報】\n「{name}」剛剛加入群組！\nUser ID：{user_id}\n請盡快手動踢除！")

# ===== Bot 加入群組 =====

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
