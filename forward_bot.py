import os
import asyncio
import sys
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import Message
from loguru import logger
from dotenv import load_dotenv

API_ID=22533598
API_HASH="f3f6997f26bb83ab2b1e04819c7af8ea"
# 源频道（用逗号分隔多个频道）
SOURCE_CHANNELS = "@hahaha54354"
# 目标频道
TARGET_CHANNEL = "@lucifer6969aaa"

# 加载环境变量
load_dotenv()

# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "forward_bot_{time}.log",
    rotation="500 MB",
    retention="10 days",
    level="INFO"
)

class MessageForwarder:
    def __init__(self):
        self.api_id = API_ID
        self.api_hash = API_HASH
        self.source_channels = SOURCE_CHANNELS.split(',')
        self.target_channel = TARGET_CHANNEL
        self.client = None


    def _setup_client(self):
        """设置 Telegram 客户端"""
        try:
            self.client = TelegramClient(
                'forwarder_session',
                self.api_id,
                self.api_hash
            )
            
            # 注册消息处理器
            @self.client.on(events.NewMessage(chats=self.source_channels))
            async def message_handler(event: events.NewMessage.Event):
                try:
                    await self._forward_message(event.message)
                except Exception as e:
                    logger.error(f"转发消息时出错: {e}")

        except Exception as e:
            logger.error(f"设置客户端时出错: {e}")
            raise

    async def _forward_message(self, message: Message):
        """转发消息到目标频道"""
        try:
            # 获取源频道信息
            chat = await message.get_chat()
            source_channel = f"@{chat.username}" if chat.username else str(chat.id)
            
            # 构建转发消息
            forward_text = (
                f"🔄 转发自: {source_channel}\n"
                f"⏰ 原始时间: {message.date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*30}\n\n"
                f"{message.text}"
            )
            
            # 转发消息
            sent_message = await self.client.send_message(
                self.target_channel,
                forward_text,
                file=message.media if message.media else None
            )
            
            logger.info(
                f"消息已转发 - 从 {source_channel} 到 {self.target_channel}"
                f" | 消息 ID: {sent_message.id}"
            )
            
        except Exception as e:
            logger.error(f"转发消息时出错: {e}")
            raise

    async def start(self):
        """启动转发器"""
        try:
            logger.info("正在启动消息转发器...")
            logger.info(f"源频道: {', '.join(self.source_channels)}")
            logger.info(f"目标频道: {self.target_channel}")
            
            await self.client.start()
            logger.info("客户端已连接")
            
            # 保持运行
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"运行时出错: {e}")
            raise
        finally:
            if self.client:
                await self.client.disconnect()
                logger.info("客户端已断开连接")

def main():
    """主函数"""
        # 创建并运行转发器
        forwarder = MessageForwarder()
        asyncio.run(forwarder.start())
    # # try:
    # #     # 检查必要的环境变量
    # #     required_vars = ['API_ID', 'API_HASH', 'SOURCE_CHANNELS', 'TARGET_CHANNEL']
    # #     missing_vars = [var for var in required_vars if not os.getenv(var)]
    # #
    # #     if missing_vars:
    # #         logger.error(f"缺少必要的环境变量: {', '.join(missing_vars)}")
    # #         sys.exit(1)
    #
    #     # 设置 Windows 事件循环策略
    #     if sys.platform.startswith('win'):
    #         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    #
    #     # 创建并运行转发器
    #     forwarder = MessageForwarder()
    #     asyncio.run(forwarder.start())
    #
    # # except KeyboardInterrupt:
    # #     logger.info("程序被用户中断")
    # # except Exception as e:
    # #     logger.error(f"程序运行出错: {e}")
    # #     sys.exit(1)

if __name__ == "__main__":
    main() 