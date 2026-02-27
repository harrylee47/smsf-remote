#!/usr/bin/env python3
"""
SmsForwarder Telegram Bot + Web Frontend
远程控制 Android 手机收发短信、查通话、查电量等
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
import asyncio
import logging
from datetime import datetime

import httpx
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ─── 配置 ───
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SMSF_URL = os.environ.get("SMSF_URL", "https://smsf.of.ci")
SMSF_SECRET = os.environ.get("SMSF_SECRET", "2CjOWZiG3d2YLT4P")
ALLOWED_CHAT_IDS = [int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "5253562355").split(",")]
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/app/data/config.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 持久化配置 ───
def load_config():
    global SMSF_SECRET
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            SMSF_SECRET = cfg.get("secret", SMSF_SECRET)
            logger.info(f"Loaded config from {CONFIG_FILE}")
    except FileNotFoundError:
        pass

def save_config():
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump({"secret": SMSF_SECRET}, f)
    logger.info(f"Saved config to {CONFIG_FILE}")


# ─── SmsForwarder API 签名 ───
def make_sign(timestamp: int, secret: str) -> str:
    """HmacSHA256 签名，与 SmsForwarder 校验签名一致"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return urllib.parse.quote(sign)


async def smsf_request(uri: str, data: dict = None) -> dict:
    """发送请求到 SmsForwarder HttpServer"""
    if data is None:
        data = {}
    ts = int(time.time() * 1000)
    sign = make_sign(ts, SMSF_SECRET)
    payload = {
        "data": data,
        "timestamp": str(ts),
        "sign": sign
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{SMSF_URL}{uri}", json=payload)
        return resp.json()


# ─── 权限检查 ───
def check_auth(update: Update) -> bool:
    return update.effective_chat.id in ALLOWED_CHAT_IDS


# ─── 命令处理 ───
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update):
        return
    await update.message.reply_text(
        "📱 *SmsForwarder 远程控制*\n\n"
        "可用命令：\n"
        "/send `手机号` `内容` — 发短信\n"
        "/sms — 查最近短信\n"
        "/sms `关键字` — 搜索短信\n"
        "/call — 查通话记录\n"
        "/battery — 查电量\n"
        "/contacts `关键字` — 查通讯录\n"
        "/location — 查位置\n"
        "/config — 查设备信息\n"
        "/web — 获取 Web 控制台地址",
        parse_mode="Markdown"
    )


async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送短信: /send 手机号 内容"""
    if not check_auth(update):
        return
    
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("用法: `/send 手机号 短信内容`", parse_mode="Markdown")
        return
    
    phone = args[0]
    content = " ".join(args[1:])
    
    try:
        result = await smsf_request("/sms/send", {
            "sim_slot": 2,  # SIM卡2（中国卡）
            "phone_numbers": phone,
            "msg_content": content
        })
        if result.get("code") == 200:
            await update.message.reply_text(f"✅ 短信已发送\n📞 {phone}\n💬 {content}")
        else:
            await update.message.reply_text(f"❌ 发送失败: {result.get('msg', '未知错误')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询短信: /sms [关键字]"""
    if not check_auth(update):
        return
    
    keyword = " ".join(context.args) if context.args else ""
    data = {
        "type": 1,  # 1=收件箱
        "page_num": 1,
        "page_size": 10,
    }
    if keyword:
        data["keyword"] = keyword
    
    try:
        result = await smsf_request("/sms/query", data)
        if result.get("code") == 200:
            messages = result.get("data", [])
            if not messages:
                await update.message.reply_text("📭 没有找到短信")
                return
            
            text = "📬 *最近短信*\n\n"
            for msg in messages[:10]:
                dt = datetime.fromtimestamp(msg["date"] / 1000)
                direction = "📥" if msg.get("type") == 1 else "📤"
                text += (
                    f"{direction} *{msg.get('name', msg['number'])}*\n"
                    f"   {msg['number']}\n"
                    f"   {msg['content'][:80]}\n"
                    f"   🕐 {dt.strftime('%m/%d %H:%M')}\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_sms_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询已发送短信: /sent"""
    if not check_auth(update):
        return
    
    try:
        result = await smsf_request("/sms/query", {
            "type": 2,  # 2=发件箱
            "page_num": 1,
            "page_size": 10,
        })
        if result.get("code") == 200:
            messages = result.get("data", [])
            if not messages:
                await update.message.reply_text("📭 没有已发送短信")
                return
            
            text = "📤 *已发送短信*\n\n"
            for msg in messages[:10]:
                dt = datetime.fromtimestamp(msg["date"] / 1000)
                text += (
                    f"📤 *{msg.get('name', msg['number'])}*\n"
                    f"   {msg['number']}\n"
                    f"   {msg['content'][:80]}\n"
                    f"   🕐 {dt.strftime('%m/%d %H:%M')}\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询通话记录: /call"""
    if not check_auth(update):
        return
    
    try:
        result = await smsf_request("/call/query", {
            "type": 0,  # 0=所有
            "page_num": 1,
            "page_size": 10,
        })
        if result.get("code") == 200:
            calls = result.get("data", [])
            if not calls:
                await update.message.reply_text("📭 没有通话记录")
                return
            
            text = "📞 *通话记录*\n\n"
            type_map = {1: "📲 来电", 2: "📱 去电", 3: "❌ 未接"}
            for call in calls[:10]:
                dt = datetime.fromtimestamp(call["dateLong"] / 1000)
                call_type = type_map.get(call.get("type"), "📞 通话")
                duration = call.get("duration", 0)
                mins, secs = divmod(duration, 60)
                text += (
                    f"{call_type} {call['number']}\n"
                    f"   ⏱ {mins}分{secs}秒 | 🕐 {dt.strftime('%m/%d %H:%M')}\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_battery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询电量: /battery"""
    if not check_auth(update):
        return
    
    try:
        result = await smsf_request("/battery/query")
        if result.get("code") == 200:
            d = result["data"]
            status_emoji = "🔌" if "充电" in d.get("status", "") else "🔋"
            await update.message.reply_text(
                f"{status_emoji} *电池状态*\n\n"
                f"电量: {d.get('level', '?')}\n"
                f"状态: {d.get('status', '?')}\n"
                f"健康: {d.get('health', '?')}\n"
                f"电源: {d.get('plugged', '?')}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询通讯录: /contacts 关键字"""
    if not check_auth(update):
        return
    
    if not context.args:
        await update.message.reply_text("用法: `/contacts 姓名或号码`", parse_mode="Markdown")
        return
    
    keyword = " ".join(context.args)
    data = {}
    if keyword.isdigit():
        data["phone_number"] = keyword
    else:
        data["name"] = keyword
    
    try:
        result = await smsf_request("/contact/query", data)
        if result.get("code") == 200:
            contacts = result.get("data", [])
            if not contacts:
                await update.message.reply_text("📭 没有找到联系人")
                return
            
            text = "👥 *通讯录*\n\n"
            for c in contacts[:20]:
                text += f"👤 {c.get('name', '?')} — {c.get('phone_number', '?')}\n"
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询位置: /location"""
    if not check_auth(update):
        return
    
    try:
        result = await smsf_request("/location/query")
        if result.get("code") == 200:
            d = result["data"]
            lat = d.get("latitude", 0)
            lon = d.get("longitude", 0)
            await update.message.reply_text(
                f"📍 *设备位置*\n\n"
                f"地址: {d.get('address', '未知')}\n"
                f"坐标: {lat}, {lon}\n"
                f"来源: {d.get('provider', '?')}\n"
                f"时间: {d.get('time', '?')}\n\n"
                f"[Google Maps](https://maps.google.com/?q={lat},{lon})",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询设备信息: /config"""
    if not check_auth(update):
        return
    
    try:
        result = await smsf_request("/config/query")
        if result.get("code") == 200:
            d = result["data"]
            text = f"⚙️ *设备信息*\n\n"
            text += f"设备: {d.get('extra_device_mark', '?')}\n"
            text += f"SIM1: {d.get('extra_sim1', '无')}\n"
            text += f"SIM2: {d.get('extra_sim2', '无')}\n\n"
            text += "*已开启功能:*\n"
            features = {
                "enable_api_sms_send": "📤 远程发短信",
                "enable_api_sms_query": "📬 远程查短信",
                "enable_api_call_query": "📞 远程查通话",
                "enable_api_contact_query": "👥 远程查通讯录",
                "enable_api_battery_query": "🔋 远程查电量",
                "enable_api_wol": "💻 远程WOL",
            }
            for key, name in features.items():
                status = "✅" if d.get(key) else "❌"
                text += f"  {status} {name}\n"
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ 查询失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"❌ 请求失败: {e}")


async def cmd_sign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """更新签名密钥: /sign 新密钥"""
    if not check_auth(update):
        return
    global SMSF_SECRET
    if not context.args:
        await update.message.reply_text(
            f"🔑 当前密钥: `{SMSF_SECRET}`\n\n"
            f"更新: `/sign 新密钥`",
            parse_mode="Markdown"
        )
        return
    SMSF_SECRET = context.args[0]
    save_config()
    # 测试连接
    try:
        result = await smsf_request("/config/query")
        if result.get("code") == 200:
            await update.message.reply_text(f"✅ 密钥已更新，连接成功\n设备: {result['data'].get('extra_device_mark', '?')}")
        else:
            await update.message.reply_text(f"⚠️ 密钥已更新，但连接失败: {result.get('msg')}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 密钥已更新，但连接失败: {e}")


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取 Web 控制台地址"""
    if not check_auth(update):
        return
    await update.message.reply_text(
        f"🌐 *Web 控制台*\n\n"
        f"地址: {SMSF_URL}\n"
        f"签名密钥: `{SMSF_SECRET}`",
        parse_mode="Markdown"
    )


async def post_init(app: Application):
    """设置 Bot 命令菜单"""
    commands = [
        BotCommand("send", "发短信 /send 手机号 内容"),
        BotCommand("sms", "查收件箱 /sms [关键字]"),
        BotCommand("sent", "查已发送"),
        BotCommand("call", "查通话记录"),
        BotCommand("battery", "查电量"),
        BotCommand("contacts", "查通讯录 /contacts 关键字"),
        BotCommand("location", "查位置"),
        BotCommand("config", "查设备信息"),
        BotCommand("sign", "查看/更新签名密钥"),
        BotCommand("web", "Web 控制台地址"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set")
        sys.exit(1)
    
    load_config()
    
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(CommandHandler("sms", cmd_sms))
    app.add_handler(CommandHandler("sent", cmd_sms_sent))
    app.add_handler(CommandHandler("call", cmd_call))
    app.add_handler(CommandHandler("battery", cmd_battery))
    app.add_handler(CommandHandler("contacts", cmd_contacts))
    app.add_handler(CommandHandler("location", cmd_location))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("sign", cmd_sign))
    app.add_handler(CommandHandler("web", cmd_web))
    
    logger.info(f"Starting bot... SMSF_URL={SMSF_URL}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
