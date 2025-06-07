import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取API凭据
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')

if not api_id or not api_hash:
    print("错误: 请确保在.env文件中设置了API_ID和API_HASH")
    exit(1)

print("开始生成会话字符串...")

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n=== 你的会话字符串 ===\n")
    print(client.session.save())
    print("\n=== 会话字符串结束 ===\n")
    print("请复制上面的字符串（确保完整复制，包括所有字符）")
    print("然后将其设置为环境变量 USER_SESSION_STRING") 