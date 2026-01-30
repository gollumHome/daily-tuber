import os
from dotenv import load_dotenv

# 加载本地 .env 文件 (如果存在)
# GitHub Actions 环境下没有这个文件，不会报错，只是什么都不做
load_dotenv(override=True)


# 1. 住宅代理 (专门给 IPRoyal 下载 YouTube 使用)
RESIDENTIAL_PROXY = os.getenv("RESIDENTIAL_PROXY")

# 2. 本地代理 (专门给 Gemini AI 使用)
# 对应 .env 中的 LOCAL_PROXY
LOCAL_PROXY = os.getenv("LOCAL_PROXY")

# 2. API Key (从环境变量读取更安全，也适配 GitHub Secrets)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")

# 3. 频道列表
CHANNELS = {
    # 币圈频道 (Crypto)
    "分析师舒琴谈比特币": {"id": "UC45uU-M3pHzHncZ5PvG_7iw", "tag": "crypto"},
    "墨染": {"id": "UCJFC7-e0PJ0ucBKhXt2luzg", "tag": "crypto"},
    "加密克里斯": {"id": "UCZhLquM_48SdeVztN0C-jvg", "tag": "crypto"},
    "加密伊奇狗哥": {"id": "UCblYscdPMB3q8cTiW_td0eg", "tag": "crypto"},
    "mrblock 區塊先生": {"id": "UCN2hSM8fBcvZBa8OOKc24eg", "tag": "crypto"},



    # # 美股/宏观频道 (Stock)
    "PowerUpGammas": {"id": "UCTb0BeBF6L7l2JsebTauH0Q", "tag": "stock"},
    "视野环球财经": {"id": "UCFQsi7WaF5X41tcuOryDk8w", "tag": "stock"},
    "LEI": {"id": "UCZyTcQHJGKkGeotf0vWA7Rg", "tag": "stock"},
    "NaNa说美股": {"id": "UCFhJ8ZFg9W4kLwFTBBNIjOw", "tag": "stock"},
    "老李玩钱": {"id": "UCo2gxyermsLBSCxFHvJs0Zg", "tag": "stock"},
    "牛顿师兄": {"id": "UCveCI6CK6oPtuy24YH9ii9g", "tag": "stock"},
    "阿泽讲技术(美股)": {"id": "UCNupOgpUJvBf3dC_Smz5Y2Q", "tag": "stock"},
    "Money or Life 美股频道": {"id": "UC9cfcOuTT9rYkyUimMjLxuw", "tag": "stock"}
 
}

Hg_HOURS = 24
TEMP_DIR = "temp_media"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
