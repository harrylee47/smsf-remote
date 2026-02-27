# 📱 SmsForwarder Remote

A sleek Telegram Bot + Web UI for remotely controlling [SmsForwarder](https://github.com/pppscn/SmsForwarder) on your Android phone.

**Send & receive SMS, check call logs, battery status, and more — all from Telegram or a beautiful dark-mode web interface.**

![Web UI](https://img.shields.io/badge/Web_UI-Dark_Mode-0f0f0f?style=flat-square&logo=html5) ![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=flat-square&logo=telegram) ![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker) ![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

## ✨ Features

### 🤖 Telegram Bot
| Command | Description |
|---------|-------------|
| `/send 号码 内容` | Send SMS remotely |
| `/sms [keyword]` | Search inbox |
| `/sent` | View sent messages |
| `/call` | Call history |
| `/battery` | Battery status |
| `/contacts keyword` | Search contacts |
| `/location` | Device location |
| `/config` | Device info & capabilities |
| `/sign [key]` | View/update signing key (persisted) |
| `/web` | Get web console URL |

### 🌐 Web Frontend
- 📥 Inbox / 📤 Sent messages browser
- ✏️ Send SMS with SIM card selector (auto-detects carrier names)
- 📞 Call history with type badges (incoming/outgoing/missed)
- 🔋 Battery status widget
- ⚙️ Device info dashboard
- 🔐 HmacSHA256 signature authentication
- 💾 Auto-saves server URL & key to localStorage
- 🌙 Dark mode UI, mobile-optimized

## 🏗️ Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Your Phone  │     │   Your Server   │     │  Android Phone   │
│  (Telegram)  │────▶│   (Bot + Web)   │────▶│  (SmsForwarder)  │
│  (Browser)   │     │   Docker/frps   │     │  HttpServer/frpc │
└──────────────┘     └─────────────────┘     └──────────────────┘
```

- **Telegram Bot** runs on your server, polls for commands, calls SmsForwarder's HTTP API
- **Web Frontend** served via nginx/OpenResty, calls API directly from browser
- **SmsForwarder** on Android exposes HTTP API, connected via frp tunnel (or direct)

## 🚀 Quick Start

### Prerequisites
- An Android phone with [SmsForwarder](https://github.com/pppscn/SmsForwarder) installed & HttpServer enabled
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Docker & Docker Compose on your server
- Network connectivity to SmsForwarder's HttpServer (direct IP, frp, or Tailscale)

### 1. Clone & Configure

```bash
git clone https://github.com/rikouu/smsf-remote.git
cd smsf-remote
```

### 2. Set Environment Variables

```bash
export BOT_TOKEN="your-telegram-bot-token"
```

Edit `docker-compose.yml` to customize:

```yaml
environment:
  - BOT_TOKEN=${BOT_TOKEN}
  - SMSF_URL=https://your-smsf-domain.com   # SmsForwarder HttpServer URL
  - SMSF_SECRET=your-signing-key             # HmacSHA256 signing key
  - ALLOWED_CHAT_IDS=123456789               # Your Telegram chat ID
```

### 3. Deploy

```bash
docker compose up -d --build
```

### 4. Web Frontend

Serve `index.html` via any web server (nginx, OpenResty, etc.) with HTTPS.

> ⚠️ HTTPS is **required** for the web frontend — `crypto.subtle` (used for HmacSHA256 signing) only works in secure contexts.

**Nginx example:**
```nginx
# API requests → SmsForwarder (via frp or direct)
location ~ ^/(sms|call|contact|battery|config|clone|wol|location)/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host your-domain.com;
}

# Static frontend
location / {
    root /path/to/smsf-remote;
    index index.html;
}
```

## 🔐 Authentication

SmsForwarder uses **HmacSHA256 signature verification**:

```
sign = urlEncode(base64(hmacSHA256(key=secret, message=timestamp + "\n" + secret)))
```

- Set the signing key in SmsForwarder → Active Control → Server → Security → "校验签名"
- Use the same key in bot config (`SMSF_SECRET`) and web frontend
- Bot supports runtime key updates via `/sign newkey` (persisted to disk)

## 🌐 Network Setup with frp

If your Android phone is behind NAT (no public IP), use [frp](https://github.com/fatedier/frp) to tunnel:

**Server (frps):**
```toml
bindPort = 7000
vhostHTTPPort = 8080
auth.method = "token"
auth.token = "your-token"
```

**SmsForwarder (frpc):**
```toml
serverAddr = "your-server-ip"
serverPort = 7000
auth.method = "token"
auth.token = "your-token"

[[proxies]]
name = "smsf"
type = "http"
localPort = 8999
customDomains = ["your-domain.com"]
```

## 📁 Project Structure

```
├── bot.py              # Telegram bot
├── index.html          # Web frontend (single file)
├── Dockerfile          # Bot container
├── docker-compose.yml  # Deployment config
├── data/               # Persisted config (auto-created)
│   └── config.json     # Signing key storage
└── README.md
```

## 📝 API Reference

Based on [SmsForwarder HTTP API](https://github.com/pppscn/SmsForwarder/wiki/%E9%99%84%E5%BD%952%EF%BC%9A%E4%B8%BB%E5%8A%A8%E8%AF%B7%E6%B1%82(%E8%BF%9C%E7%A8%8B%E6%8E%A7%E5%88%B6)):

| Endpoint | Description |
|----------|-------------|
| `POST /sms/send` | Send SMS |
| `POST /sms/query` | Query SMS |
| `POST /call/query` | Query call logs |
| `POST /contact/query` | Query contacts |
| `POST /battery/query` | Query battery |
| `POST /config/query` | Query device config |
| `POST /location/query` | Query location |

## 🙏 Credits

- [SmsForwarder](https://github.com/pppscn/SmsForwarder) by pppscn — the Android app that makes this all possible
- [SmsForwarder-Web-Client](https://github.com/CTCD/SmsForwarder-Web-Client) — original web client inspiration

## 📄 License

MIT
