import os
import base64
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv


def validate_session_string(session_string):
    """验证会话字符串格式是否正确"""
    try:
        # 移除所有空白字符
        session_string = ''.join(session_string.split())

        # 确保字符串长度是4的倍数
        padding_needed = len(session_string) % 4
        if padding_needed:
            session_string += '=' * (4 - padding_needed)

        # 尝试解码
        base64.urlsafe_b64decode(session_string)
        return True, session_string
    except Exception as e:
        return False, str(e)


# 加载环境变量
load_dotenv()

# 获取API凭据
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')

if not api_id or not api_hash:
    print("错误: 请确保在.env文件中设置了API_ID和API_HASH")
    exit(1)

try:
    api_id = int(api_id)
except ValueError:
    print("错误: API_ID 必须是一个数字")
    exit(1)

print("开始生成会话字符串...")

with TelegramClient(StringSession(), api_id, api_hash) as client:
    # 获取会话字符串
    session_string = client.session.save()

    # 验证会话字符串
    is_valid, cleaned_string = validate_session_string(session_string)

    if not is_valid:
        print(f"警告: 生成的会话字符串可能有问题: {cleaned_string}")
        exit(1)

    print("\n=== 你的会话字符串（单行格式）===")
    print(cleaned_string)
    print("\n=== 验证结果 ===")
    print("✓ 会话字符串格式验证通过")
    print("✓ 字符串长度:", len(cleaned_string))
    print("✓ Base64解码测试通过")

    print("\n=== 环境变量设置说明 ===")
    print("1. 复制上面的单行字符串（确保完整复制，不要有换行）")
    print("2. 在Render的环境变量设置中：")
    print("   - 名称: USER_SESSION_STRING")
    print("   - 值: 粘贴刚才复制的字符串")
    print("\n注意：确保复制时不要包含任何换行符或额外的空格！")