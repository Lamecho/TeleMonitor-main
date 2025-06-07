import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
import telethon

def validate_session_string(session_string):
    """验证会话字符串是否可用"""
    try:
        # 移除所有空白字符
        session_string = ''.join(session_string.split())
        
        # 创建测试客户端
        test_client = TelegramClient(
            StringSession(session_string),
            int(os.getenv('API_ID')),
            os.getenv('API_HASH'),
            device_model="Windows 10",
            system_version="Windows 10",
            app_version="1.0",
            lang_code="zh-CN"
        )
        
        # 尝试连接并验证
        with test_client:
            print("\n=== 会话验证信息 ===")
            print(f"Telethon版本: {telethon.__version__}")
            me = test_client.get_me()
            print(f"账号信息: {me.first_name} (@{me.username})")
            print(f"用户ID: {me.id}")
            print("连接测试: 成功")
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

with TelegramClient(
    StringSession(),
    api_id,
    api_hash,
    device_model="Windows 10",
    system_version="Windows 10",
    app_version="1.0",
    lang_code="zh-CN"
) as client:
    # 获取会话字符串
    session_string = client.session.save()
    
    # 验证会话字符串
    is_valid, result = validate_session_string(session_string)
    
    if not is_valid:
        print(f"\n❌ 警告: 生成的会话字符串无效")
        print(f"错误信息: {result}")
        print("\n请重新运行脚本生成新的会话字符串")
        exit(1)

    print("\n✅ 会话字符串验证通过!")
    print("\n=== 你的会话字符串（单行格式）===")
    print(result)
    print("\n=== 验证结果 ===")
    print("✓ 会话字符串格式正确")
    print("✓ 连接测试成功")
    print("✓ 账号验证通过")
    print(f"✓ 字符串长度: {len(result)}")
    
    print("\n=== 环境变量设置说明 ===")
    print("1. 复制上面的单行字符串（确保完整复制，不要有换行）")
    print("2. 在Render的环境变量设置中：")
    print("   - 名称: USER_SESSION_STRING")
    print("   - 值: 粘贴刚才复制的字符串")
    print("\n注意：")
    print("- 确保复制时不要包含任何换行符或额外的空格")
    print("- 确保包含所有的等号")
    print("- 设置后请重新部署应用")


