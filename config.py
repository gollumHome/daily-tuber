import os
from dotenv import load_dotenv

# 加载本地 .env 文件 (如果存在)
# GitHub Actions 环境下没有这个文件，不会报错，只是什么都不做
load_dotenv()


# ================= 配置区 =================

# 1. 代理配置 (核心修改)
# 本地在 .env 里填 HTTP_PROXY，云端不填即可自动识别
PROXY_URL = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")

# 2. API Key (从环境变量读取更安全，也适配 GitHub Secrets)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")

# 3. 频道列表 (建议把 JSON 字符串存入环境变量，或者依然写死在这里)
CHANNELS = {
    "墨染": "UCJFC7-e0PJ0ucBKhXt2luzg",
}

Hg_HOURS = 24
TEMP_DIR = "temp_media"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)