import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()
API_ID=22533598
API_HASH="f3f6997f26bb83ab2b1e04819c7af8ea"
# 源频道（用逗号分隔多个频道）
SOURCE_CHANNELS = "@hahaha54354"
# 目标频道
TARGET_CHANNEL = "@lucifer6969aaa"
class Config:
    # Telegram 配置
    TELEGRAM_API_ID = API_ID
    TELEGRAM_API_HASH = API_HASH
    SESSION_NAME = 'crow_session'
    DEFAULT_CHANNEL = os.getenv('DEFAULT_CHANNEL', '@NewQuark')

    # 代理配置
    # PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
    PROXY_ENABLED = False
    PROXY_TYPE = os.getenv('PROXY_TYPE', 'http')
    PROXY_ADDRESS = os.getenv('PROXY_ADDRESS', '127.0.0.1')
    PROXY_PORT = int(os.getenv('PROXY_PORT', 7890))

config = Config()