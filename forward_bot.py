import os
import asyncio
import re
import sys
import signal
from datetime import datetime, timedelta
import time
import pytz
from collections import defaultdict
from telethon import TelegramClient, events
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument
from loguru import logger
from dotenv import load_dotenv
from telethon.errors import FloodWaitError, PeerFloodError
from anti_ban_config import AntiBanConfig, AntiBanStrategies
import queue
import threading
from flask import Flask, jsonify
import nest_asyncio
from waitress import serve
import aiohttp
import random
import json
from urllib.parse import urlparse
from telethon.sessions import StringSession

# 启用嵌套事件循环
nest_asyncio.apply()

# 加载环境变量
load_dotenv()

# 设置时区
beijing_tz = pytz.timezone("Asia/Shanghai")

# 源频道和目标频道配置
SOURCE_CHANNELS = ['@CHATROOMA777', '@bqs666',
                   "@yuanchengbangong", "@YCSL588", "@HHJason123", "@shuangxiugognzuo",
                   "@haiwaiIt", "@huhulc500", "@utgroupjob", "@ferm_yiyi", "@warming111",
                   "@keepondoing33", "@sus_hhll", "@PAZP7", "@Winnieachr", "@HR_PURR",
                   "@zhaopin_jishu", "@PMGAME9OFF6OBGAME", "@makatizhipinz", "@yuancheng_job",
                   "@remote_cn", "@yuanchenggongzuoOB", "@taiwanjobstreet", "@MLXYZP"
                   ]

TARGET_CHANNEL = ["@CHATROOMA999"]
KEYWORDS_CHANNEL_1 = ["@miaowu333"]
KEYWORDS_CHANNEL_2 = ["@yuancheng5551"]
LOGS_CHANNEL = ["@logsme333"]

# Flask 应用
app = Flask(__name__)
app.config.update(
    ENV='production',
    DEBUG=False,
    TESTING=False,
    SECRET_KEY=os.urandom(24)
)


@app.route('/')
def home():
    from flask import jsonify
    return jsonify({
        'status': 'success',
        'message': 'Telegram Bot is running!',
        'timestamp': datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
    }), 200


def run_flask():
    """运行生产级别的 Flask 服务器"""
    try:
        # 使用环境变量中的端口，如果没有则默认使用3000
        port = int(os.getenv('PORT', 3000))
        serve(app, host='0.0.0.0', port=port, threads=2)
    except Exception as e:
        logger.error(f"Flask 服务器启动失败: {e}")
        # 如果 waitress 失败，回退到开发服务器
        port = int(os.getenv('PORT', 3000))
        app.run(host='0.0.0.0', port=port)


def patcher(record):
    beijing_now = datetime.now(
        pytz.timezone("Asia/Shanghai")).strftime("%m-%d %H:%M:%S")
    record["extra"]["beijing_time"] = beijing_now


# 清除默认 logger
logger.remove()

# 设置 patcher（动态注入北京时间）
logger = logger.patch(patcher)

try:
    # 控制台日志输出
    logger.add(
        sys.stderr,
        format="<green>{extra[beijing_time]}</green> | <level>{level:<8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        enqueue=True,
        catch=True,
        diagnose=True
    )

    # 创建日志文件夹
    os.makedirs("logs", exist_ok=True)
    beijing_now_str = datetime.now(
        pytz.timezone("Asia/Shanghai")).strftime("%m-%d//%H:%M")

    # 文件日志输出
    logger.add(
        f"logs/hrbot_{beijing_now_str}.log",
        rotation="300 MB",
        retention="3 days",
        level="DEBUG",
        encoding="utf-8",
        enqueue=True,
        catch=True,
        diagnose=True,
        format="<green>{extra[beijing_time]}</green> | <level>{level:<8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
except Exception as e:
    print(f"日志配置出错: {e}")
    logger.add(sys.stderr, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# 全局日志处理器实例
telegram_log_handler = None


def telegram_log_sink(message):
    """自定义日志输出到Telegram"""
    global telegram_log_handler
    if telegram_log_handler:
        # 格式化日志消息
        formatted_message = message.rstrip('\n')
        telegram_log_handler.send_log(formatted_message)


# 自定义Telegram日志处理器
class TelegramLogHandler:
    def __init__(self, client, channel):
        self.client = client  # Bot客户端
        self.channel = channel
        self.log_queue = queue.Queue()
        self.is_running = False
        self.batch_size = 5  # 每次发送的最大日志条数
        self.batch_timeout = 3  # 批量发送超时时间（秒）
        self.last_send_time = time.time()
        self.cleaner_thread = None
        self.last_cleanup_time = time.time()

    async def start(self):
        """启动日志发送器"""
        try:
            self.is_running = True

            # 启动日志发送任务
            asyncio.create_task(self._send_logs())

            # 启动清理线程
            self.cleaner_thread = threading.Thread(target=self._run_cleaner, daemon=True)
            self.cleaner_thread.start()

            # logger.info("Telegram日志处理器启动成功")
        except Exception as e:
            logger.error(f"启动Telegram日志处理器失败: {e}")

    def _run_cleaner(self):
        """定期清理日志队列"""
        while self.is_running:
            try:
                current_time = time.time()
                # 每4小时清理一次
                if current_time - self.last_cleanup_time > 14400:
                    self._cleanup_old_logs()
                    self.last_cleanup_time = current_time
                time.sleep(600)  # 每10分钟检查一次
            except Exception as e:
                logger.error(f"日志清理器出错: {e}")
                time.sleep(600)

    def _cleanup_old_logs(self):
        """清理队列中的旧日志"""
        try:
            queue_size = self.log_queue.qsize()
            if queue_size > 1000:  # 如果队列太大，保留最新的1000条
                logger.info(f"开始清理日志队列，当前大小: {queue_size}")
                new_queue = queue.Queue()
                # 保留最新的1000条日志
                logs = []
                while not self.log_queue.empty():
                    try:
                        logs.append(self.log_queue.get_nowait())
                    except queue.Empty:
                        break
                for log in logs[-1000:]:
                    new_queue.put(log)
                self.log_queue = new_queue
                logger.info(f"日志队列清理完成，新大小: {self.log_queue.qsize()}")
        except Exception as e:
            logger.error(f"清理日志队列时出错: {e}")

    async def _send_logs(self):
        """发送日志消息到Telegram频道"""
        logger.debug("日志发送任务已启动")
        batch_logs = []
        while self.is_running:
            try:
                # 尝试从队列获取消息
                try:
                    # 立即获取所有可用的消息
                    while True:
                        message = self.log_queue.get_nowait()
                        batch_logs.append(message)
                        logger.debug(f"从队列获取到消息，当前批次大小: {len(batch_logs)}")
                except queue.Empty:
                    # 队列为空时继续处理
                    if batch_logs:
                        logger.debug(f"队列为空，当前批次中有 {len(batch_logs)} 条消息待发送")
                    pass

                current_time = time.time()
                # 如果有日志且(达到批次大小或超过超时时间)，则发送
                if batch_logs and (len(batch_logs) >= self.batch_size or
                                   current_time - self.last_send_time > self.batch_timeout):
                    try:
                        logger.debug(f"准备发送 {len(batch_logs)} 条日志消息")
                        # 组合日志消息
                        combined_message = "📋 **系统日志**\n```\n"
                        combined_message += "\n".join(batch_logs)
                        combined_message += "\n```"

                        if self.client and self.client.is_connected():
                            await self.client.send_message(self.channel, combined_message)
                            logger.debug(f"成功发送了 {len(batch_logs)} 条日志消息")
                            self.last_send_time = current_time
                            batch_logs = []
                    except Exception as e:
                        logger.error(f"发送日志到Telegram失败: {e}")
                        await asyncio.sleep(2)

                # 短暂等待后继续检查
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"日志处理器出错: {e}")
                await asyncio.sleep(2)

    def send_log(self, message):
        """添加日志消息到队列"""
        try:
            # 格式化日志消息
            formatted_message = message.rstrip('\n')
            self.log_queue.put_nowait(formatted_message)
            logger.debug(f"日志已加入队列，当前队列大小: {self.log_queue.qsize()}")
        except queue.Full:
            logger.error("日志队列已满，消息丢失")

    def stop(self):
        """停止日志发送器"""
        self.is_running = False
        if self.cleaner_thread and self.cleaner_thread.is_alive():
            self.cleaner_thread.join(timeout=1)

        # 发送剩余的日志
        if hasattr(self, 'client') and self.client and self.client.is_connected():
            remaining_logs = []
            while not self.log_queue.empty():
                try:
                    remaining_logs.append(self.log_queue.get_nowait())
                except queue.Empty:
                    break

            if remaining_logs:
                combined_message = "📋 **系统日志（最终批次）**\n```\n"
                combined_message += "\n".join(remaining_logs)
                combined_message += "\n```"

                async def send_final_logs():
                    try:
                        await self.client.send_message(self.channel, combined_message)
                    except Exception as e:
                        logger.error(f"发送最终日志批次失败: {e}")

                # 创建新的事件循环来发送最后的日志
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(send_final_logs())
                loop.close()


class MessageForwarder:
    def __init__(self):
        self.api_id = int(os.getenv("API_ID"))
        self.api_hash = os.getenv("API_HASH")
        self.bot_token = os.getenv("BOT_TOKEN")
        self.anti_ban_config = AntiBanConfig()
        self.anti_ban_strategies = AntiBanStrategies()
        self.source_channels = SOURCE_CHANNELS
        self.target_channel = TARGET_CHANNEL
        self.user_client = None
        self.bot_client = None
        self.message_delays = defaultdict(float)
        self.is_listening = True
        self.pause_until = None
        self.processed_messages = set()
        self.message_lock = asyncio.Lock()
        self.telegram_log_handler = None
        self.start_time = datetime.now(pytz.timezone("Asia/Shanghai"))
        self.last_message_received = None
        self.total_messages_processed = 0
        self.running = True
        self.tasks = []

        # User-Agent池
        self.user_agents = [
            # Chrome
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Firefox
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0',
            # Safari
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            # Edge
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        ]

        # 更新为实际浏览器的请求头配置
        self.browser_profile = {
            ':authority': 'amazing-vast-pirate.glitch.me',
            ':method': 'GET',
            ':scheme': 'https',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cache-control': 'max-age=0',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
        }

        # 初始化基础请求头
        self.base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5,zh-CN;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'DNT': '1',
        }

        # 初始化事件循环
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        self._setup_clients()

    def _get_random_headers(self):
        """获取随机的请求头"""
        headers = self.base_headers.copy()
        headers['User-Agent'] = random.choice(self.user_agents)

        # 随机添加一些额外的请求头
        if random.random() > 0.5:
            headers['Sec-CH-UA'] = '"Chromium";v="120", "Google Chrome";v="120", "Not=A?Brand";v="99"'
            headers['Sec-CH-UA-Mobile'] = '?0'
            headers['Sec-CH-UA-Platform'] = '"Windows"'

        return headers

    def _get_browser_profile(self):
        """获取完整的浏览器配置"""
        profile = self.browser_profile.copy()

        # 添加通用头部
        profile.update({
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
            'Cache-Control': 'max-age=0',
        })

        # 随机添加一些额外头部
        if random.random() > 0.5:
            profile.update({
                'DNT': '1',
                'Pragma': 'no-cache'
            })

        return profile

    def _setup_clients(self):
        """设置 Telegram 客户端"""
        try:
            # 从环境变量获取会话字符串
            user_session = os.getenv('USER_SESSION_STRING')
            if not user_session:
                raise ValueError("需要在环境变量中设置 USER_SESSION_STRING")

            # 清理会话字符串
            user_session = ''.join(user_session.split())  # 移除所有空白字符
            
            # 确保字符串长度是4的倍数
            padding_needed = len(user_session) % 4
            if padding_needed:
                user_session += '=' * (4 - padding_needed)

            logger.info("正在初始化用户客户端...")
            
            # 用户账号客户端
            self.user_client = TelegramClient(
                StringSession(user_session),
                self.api_id,
                self.api_hash,
                device_model="Windows 10",
                system_version="Windows 10",
                app_version="1.0",
                lang_code="zh-CN",
                system_lang_code="zh-CN"
            )

            # 尝试连接并验证会话
            logger.info("正在验证会话...")
            self.user_client.connect()
            if not self.user_client.is_user_authorized():
                raise ValueError("会话未授权，请重新生成会话字符串")
            
            me = self.user_client.get_me()
            logger.info(f"会话验证成功: {me.first_name} (@{me.username})")

            logger.info("正在初始化Bot客户端...")
            
            # Bot客户端
            self.bot_client = TelegramClient(
                None,  # 不需要会话文件
                self.api_id,
                self.api_hash,
                device_model="Windows 10",
                system_version="Windows 10",
                app_version="1.0",
                lang_code="zh-CN",
                system_lang_code="zh-CN"
            )

            # 设置消息处理器
            @self.user_client.on(events.NewMessage())
            async def debug_message_handler(event: events.NewMessage.Event):
                try:
                    message = event.message
                    chat = await message.get_chat()
                    channel_name = f"@{chat.username}" if chat.username else str(chat.id)

                    logger.debug(f"收到新消息，来自: {channel_name}")
                    logger.debug(f"消息内容: {message.text[:100] if message.text else '无文本'}")

                    if channel_name in self.source_channels:
                        message_id = f"{channel_name}:{message.id}"
                        async with self.message_lock:
                            if message_id in self.processed_messages:
                                logger.info(f"跳过重复消息: {message_id}")
                                return

                            self.processed_messages.add(message_id)
                            if len(self.processed_messages) > 1000:
                                self.processed_messages = set(list(self.processed_messages)[-1000:])

                        logger.success(f"******* 已收到目标频道 {channel_name} 的新消息 *******")
                        await self._process_message(message, channel_name)
                    else:
                        logger.debug(f"跳过非目标频道的消息: {channel_name}")

                except Exception as e:
                    logger.error(f"消息处理出错: {str(e)}")
                    import traceback
                    logger.error(f"错误堆栈: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"设置客户端时出错: {str(e)}")
            raise

    async def check_url_access(self, url):
        """检查URL是否可访问"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            # 获取基础请求头配置
            headers = self.browser_profile.copy()

            # 更新domain相关的头部
            headers[':authority'] = domain
            headers[':path'] = parsed_url.path or '/'

            # 移除pseudo headers，因为aiohttp会自动处理这些
            pseudo_headers = [':authority', ':method', ':path', ':scheme']
            headers = {k: v for k, v in headers.items() if k not in pseudo_headers}

            logger.debug(f"尝试访问URL: {url}")
            logger.debug(f"使用请求头: {json.dumps(headers, indent=2)}")

            # 配置 aiohttp 客户端选项
            conn = aiohttp.TCPConnector(ssl=False)  # 禁用SSL验证
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
                try:
                    async with session.get(url, headers=headers, allow_redirects=True) as response:
                        logger.debug(f"响应状态码: {response.status}")
                        logger.debug(f"响应头: {json.dumps(dict(response.headers), indent=2)}")

                        if response.status == 403:
                            logger.error(f"访问被拒绝(403 Forbidden): {url}")
                            return False
                        elif response.status == 200:
                            logger.info(f"成功访问URL: {url}")
                            return True
                        else:
                            logger.warning(f"收到非预期状态码: {response.status}")
                            return False

                except aiohttp.ClientError as e:
                    logger.error(f"请求出错: {str(e)}")
                    return False

        except Exception as e:
            logger.error(f"URL访问检查过程中发生未知错误: {str(e)}")
            return False

    async def _process_message(self, message, channel_name):
        """处理消息的统一方法"""
        message_id = f"{channel_name}:{message.id}"
        try:
            # 如果消息中包含URL，先检查可访问性
            if message.text:
                urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                                  message.text)
                for url in urls:
                    if not await self.check_url_access(url):
                        logger.warning(f"URL {url} 不可访问，将在消息中标注")
                        message.text = message.text.replace(url, f"{url} [⚠️访问受限]")

            # 添加工作时间和安全时间检查的详细日志
            is_work_time = self.anti_ban_strategies.is_work_time()
            is_safe_time = self.anti_ban_strategies.is_safe_time()
            can_send = self.anti_ban_strategies.can_send_message()

            # 获取当前时间用于日志显示
            current_time = datetime.now(beijing_tz)
            current_hour = current_time.hour
            is_weekend = current_time.weekday() >= 5
            in_work_hours = 9 <= current_hour <= 18

            # 详细记录时间和限制状态
            logger.info("🕒 消息处理状态检查:")
            if in_work_hours:
                if is_weekend:
                    logger.info("  • 当前是周末工作时间(9:00-18:00): " + (
                        "✅ 随机通过" if is_work_time else "❌ 随机跳过(50%概率)"))
                else:
                    logger.info("  • 当前是工作日工作时间(9:00-18:00): ✅ 正常处理")
            else:
                logger.info("  • 当前是非工作时间: " + ("✅ 随机通过" if is_work_time else "❌ 随机跳过(30%概率)"))
            logger.info(f"  • 安全时间(7:00-23:00): {'✅' if is_safe_time else '❌'}")
            logger.info(f"  • 发送限制检查: {'✅' if can_send else '❌'}")

            # 跳过系统日志消息
            if message.text and "📋 **系统日志**" in message.text:
                logger.info("⚪ [SKIP] 跳过系统日志消息")
                return

            # 检查是否应该处理这条消息
            if not is_work_time:
                if in_work_hours and is_weekend:
                    logger.info(f"❌ 周末工作时间消息随机跳过，当前时间: {current_time.strftime('%H:%M')}")
                else:
                    logger.info(f"❌ 非工作时间消息随机跳过，当前时间: {current_time.strftime('%H:%M')}")
                return

            if not is_safe_time:
                logger.warning(f"❌ 不在安全时间范围内(7:00-23:00)，当前时间: {current_time.strftime('%H:%M')}")
                return

            # 如果所有检查都通过，继续处理消息
            logger.success("✅ 所有安全检查通过，开始处理消息")
            logger.info(f"🎯 [PROCESSING] 监听频道 {channel_name} 有新消息，开始处理")

            # 获取基本消息信息
            # logger.info(f"🔔 监听到新消息！消息ID: {message.id}")
            # logger.info(f"👤 发送者ID: {message.sender_id}")
            logger.info(f"📅 消息时间: {message.date}")
            logger.info(f"📝 消息预览: {(message.text or '无文本')[:20]}...")

            chat = await message.get_chat()
            source_channel = f"@{chat.username}" if chat.username else str(chat.id)
            beijing_time = message.date.replace(tzinfo=pytz.UTC).astimezone(beijing_tz)

            # 改进消息文本清理逻辑
            def clean_text(text):
                if not text:
                    return ""
                # 移除不可见字符但保留基本格式
                text = ''.join(char for char in text if char.isprintable() or char in '\n\t')
                # 清理多余的空白字符
                text = re.sub(r'\s+', ' ', text).strip()
                # 清理URL但保留显示文本
                text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '',
                              text)
                return text

            cleaned_text = clean_text(message.text or '')

            # 构建转发消息，确保文本非空
            header = (
                f"🔄 转发自: {source_channel}\n"
                f"⏰ 时间: {beijing_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'=' * 30}"
            )

            body = cleaned_text if cleaned_text else "（无文本内容）"
            forward_text = f"{header}\n\n{body}"

            # 检查消息长度
            if len(forward_text) > 4096:  # Telegram消息长度限制
                forward_text = forward_text[:4093] + "..."

            # 获取自适应延迟
            delay = self.anti_ban_strategies.get_adaptive_delay()
            logger.info(f"等待 {delay:.2f} 秒后发送消息")
            await asyncio.sleep(delay)
            logger.info("延迟等待完成，开始发送消息")

            # 检查Bot客户端连接状态
            if not self.bot_client.is_connected():
                logger.error("❌ Bot客户端未连接，无法发送消息")
                return

            # 发送主消息
            try:
                logger.info(f"开始发送主消息到 {self.target_channel[0]}")
                # 使用parse_mode=None避免意外的格式化问题
                await self.bot_client.send_message(
                    self.target_channel[0],
                    forward_text,
                    parse_mode=None,  # 禁用消息格式化
                    link_preview=False  # 禁用链接预览
                )
                logger.success(f"✅ 成功转发消息到 {self.target_channel[0]}")
            except Exception as e:
                logger.error(f"❌ 发送主消息失败: {str(e)}")
                if "invalid bounds" in str(e).lower():
                    # 如果是实体边界问题，尝试只发送纯文本
                    try:
                        logger.info("尝试发送纯文本消息...")
                        await self.bot_client.send_message(
                            self.target_channel[0],
                            forward_text,
                            parse_mode=None,
                            formatting_entities=[],
                            link_preview=False
                        )
                        logger.success("✅ 使用纯文本模式成功发送消息")
                    except Exception as pure_text_error:
                        logger.error(f"❌ 纯文本发送也失败: {str(pure_text_error)}")
                        async with self.message_lock:
                            self.processed_messages.discard(message_id)
                        raise
                else:
                    async with self.message_lock:
                        self.processed_messages.discard(message_id)
                    raise

            # 转发媒体消息
            if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                try:
                    logger.info("开始转发媒体消息")
                    await asyncio.sleep(delay * 0.3)  # 媒体消息额外延迟

                    # 检查媒体类型
                    media_type = "未知"
                    if isinstance(message.media, MessageMediaPhoto):
                        media_type = "图片"
                    elif isinstance(message.media, MessageMediaDocument):
                        # 获取文件名和MIME类型
                        attributes = message.media.document.attributes
                        file_name = next((attr.file_name for attr in attributes if hasattr(attr, 'file_name')), None)
                        mime_type = message.media.document.mime_type
                        media_type = f"文档 (MIME: {mime_type}, 文件名: {file_name})" if file_name else f"文档 (MIME: {mime_type})"

                    logger.info(f"媒体类型: {media_type}")

                    # 尝试直接转发消息而不是重新上传媒体
                    try:
                        logger.info("尝试直接转发原始消息...")
                        await message.forward_to(self.target_channel[0])
                        logger.success(f"✅ 成功转发媒体消息到 {self.target_channel[0]}")
                        return
                    except Exception as forward_error:
                        logger.warning(f"直接转发失败: {str(forward_error)}, 尝试重新上传...")

                    # 如果直接转发失败，尝试重新上传
                    try:
                        await self.bot_client.send_file(
                            self.target_channel[0],
                            message.media,
                            caption=forward_text[:1024],  # Telegram媒体说明长度限制
                            parse_mode=None,
                            force_document=isinstance(message.media, MessageMediaDocument)
                        )
                        logger.success(f"✅ 成功重新上传媒体消息到 {self.target_channel[0]}")
                    except Exception as upload_error:
                        logger.error(f"❌ 重新上传媒体失败: {str(upload_error)}")

                        # 如果都失败了，尝试只发送文本消息
                        logger.info("尝试只发送文本内容...")
                        media_info = f"\n\n[注意：原消息包含{media_type}，但由于权限限制无法转发]"
                        text_only_message = forward_text + media_info

                        await self.bot_client.send_message(
                            self.target_channel[0],
                            text_only_message,
                            parse_mode=None,
                            link_preview=False
                        )
                        logger.info("✅ 已发送包含媒体说明的文本消息")

                except Exception as e:
                    logger.error(f"❌ 转发媒体消息失败: {str(e)}")
                    logger.warning("跳过媒体转发，继续处理其他消息")

            # 记录成功发送
            self.anti_ban_strategies.record_success()

            logger.info(
                f"📈 转发统计 分钟内: {self.anti_ban_strategies.message_count['minute']}, 小时内: {self.anti_ban_strategies.message_count['hour']}")
            logger.success("🎉 消息转发流程完全完成")

        except Exception as e:
            # 发生错误时从已处理集合中移除消息ID
            async with self.message_lock:
                self.processed_messages.discard(message_id)

            if isinstance(e, FloodWaitError):
                logger.warning(f"遇到频率限制，等待 {e.seconds} 秒")
                self.anti_ban_strategies.record_error(str(e))
                if e.seconds > 300:  # 超过5分钟
                    logger.warning(f"频率限制时间过长({e.seconds}秒)，暂停监听直到工作时间")
                    self.pause_until_work_time()
                else:
                    await asyncio.sleep(e.seconds)
            elif isinstance(e, PeerFloodError):
                logger.error(f"目标频道被限制：{e}")
                logger.warning("检测到PEER_FLOOD错误，暂停监听直到工作时间")
                self.pause_until_work_time()
            else:
                logger.error(f"发送消息失败: {e}")
                error_action = self.anti_ban_strategies.get_error_action(str(e))
                logger.info(f"建议操作: {error_action}")

                # 检查是否为需要暂停监听的错误
                dangerous_keywords = ["BANNED", "RESTRICTED", "SESSION_REVOKED", "USER_DEACTIVATED"]
                if any(keyword in str(e).upper() for keyword in dangerous_keywords):
                    logger.error("检测到严重错误，暂停监听直到工作时间")
                    self.pause_until_work_time()
                    return

                if any(keyword in str(e).upper() for keyword in self.anti_ban_config.DANGEROUS_ERRORS):
                    logger.error("检测到危险错误，进入长时间冷却")
                    cooldown = self.anti_ban_strategies.record_error(str(e))
                    if cooldown > 600:  # 超过10分钟
                        logger.warning("冷却时间过长，暂停监听直到工作时间")
                        self.pause_until_work_time()
                    else:
                        await asyncio.sleep(cooldown)
                else:
                    cooldown = self.anti_ban_strategies.record_error(str(e))
                    await asyncio.sleep(min(cooldown, 60))  # 最多等待60秒

    def pause_until_work_time(self):
        """暂停监听直到工作时间"""
        self.is_listening = False
        next_work_time = self.anti_ban_strategies.get_next_work_time()
        self.pause_until = next_work_time
        logger.warning(f"已暂停监听，将在 {next_work_time.strftime('%Y-%m-%d %H:%M:%S')} 恢复")

    def resume_listening(self):
        """恢复监听"""
        self.is_listening = True
        self.pause_until = None
        logger.info("已恢复消息监听")

    async def check_status(self):
        """每4分钟检查一次运行状态"""
        while True:
            try:
                current_time = datetime.now(pytz.timezone("Asia/Shanghai"))
                uptime = current_time - self.start_time

                status_report = [
                    "🤖 机器人运行状态报告",
                    f"⏰ 当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"⌛ 已运行时间: {str(uptime).split('.')[0]}",
                    f"📊 处理消息统计:",
                    f"  • 总处理消息: {self.total_messages_processed}",
                    f"  • 最后消息时间: {self.last_message_received.strftime('%Y-%m-%d %H:%M:%S') if self.last_message_received else '无'}",
                    f"  • 缓存消息数量: {len(self.processed_messages)}",
                    f"💡 系统状态:",
                    f"  • 监听状态: {'✅ 正常' if self.is_listening else '⛔ 已暂停'}",
                    f"  • 暂停时间: {self.pause_until.strftime('%Y-%m-%d %H:%M:%S') if self.pause_until else '无'}",
                    f"  • 用户客户端: {'✅ 已连接' if self.user_client.is_connected() else '❌ 未连接'}",
                    f"  • Bot客户端: {'✅ 已连接' if self.bot_client.is_connected() else '❌ 未连接'}",
                    f"📈 消息限制:",
                    f"  • 分钟内: {self.anti_ban_strategies.message_count['minute']}/{self.anti_ban_config.MAX_MESSAGES_PER_MINUTE}",
                    f"  • 小时内: {self.anti_ban_strategies.message_count['hour']}/{self.anti_ban_config.MAX_MESSAGES_PER_HOUR}",
                    f"  • 今日内: {self.anti_ban_strategies.message_count['day']}/{self.anti_ban_config.MAX_MESSAGES_PER_DAY}",
                    f"⚙️ 运行参数:",
                    f"  • 延迟倍数: {self.anti_ban_strategies.current_delay_multiplier:.2f}",
                    f"  • 连续错误: {self.anti_ban_strategies.consecutive_errors}",
                    f"  • 工作时间: {'✅' if self.anti_ban_strategies.is_work_time() else '❌'}",
                    f"  • 安全时间: {'✅' if self.anti_ban_strategies.is_safe_time() else '❌'}"
                ]

                status_message = "\n".join(status_report)
                logger.info(status_message)

                # 如果有任何异常状态，添加警告
                warnings = []
                if not self.is_listening:
                    warnings.append("⚠️ 机器人当前不在监听状态")
                if not self.user_client.is_connected():
                    warnings.append("⚠️ 用户客户端未连接")
                if not self.bot_client.is_connected():
                    warnings.append("⚠️ Bot客户端未连接")
                if self.anti_ban_strategies.consecutive_errors > 0:
                    warnings.append(f"⚠️ 存在 {self.anti_ban_strategies.consecutive_errors} 个连续错误")

                if warnings:
                    logger.warning("\n".join(warnings))

            except Exception as e:
                logger.error(f"状态检查出错: {e}")

            # 等待4分钟
            await asyncio.sleep(240)

    async def cleanup(self):
        """清理资源"""
        logger.info("开始清理资源...")
        self.running = False

        # 停止所有任务
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # 等待任务完成
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        # 关闭客户端连接
        if self.user_client:
            await self.user_client.disconnect()
        if self.bot_client:
            await self.bot_client.disconnect()

        # 停止日志处理器
        if self.telegram_log_handler:
            self.telegram_log_handler.stop()

        logger.info("资源清理完成")

    async def start(self):
        """启动转发器"""
        try:
            # 设置信号处理
            for sig in (signal.SIGTERM, signal.SIGINT):
                self.loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.handle_signal(s)))

            logger.debug(f"API ID: {self.api_id}")

            # 启动用户客户端（用于监听）
            await self.user_client.start()
            user_me = await self.user_client.get_me()
            logger.info(f"用户HASH已连接: {user_me.first_name} (@{user_me.username})")
            logger.debug(f"✓ 连接状态: {self.user_client.is_connected()}")

            # 启动Bot客户端（用于转发）
            await self.bot_client.start(bot_token=self.bot_token)
            bot_me = await self.bot_client.get_me()
            logger.info(f"用户Bot已连接: {bot_me.first_name} (@{bot_me.username})")
            logger.debug(f"✓ 连接状态: {self.bot_client.is_connected()}")

            # 初始化并启动Telegram日志处理器
            global telegram_log_handler
            self.telegram_log_handler = TelegramLogHandler(self.bot_client, LOGS_CHANNEL[0])
            telegram_log_handler = self.telegram_log_handler
            await self.telegram_log_handler.start()

            # 添加Telegram日志输出
            logger.add(telegram_log_sink, level="INFO")
            logger.info("Tg日志处理器已启动")

            # 检查事件处理器
            event_handlers = self.user_client.list_event_handlers()
            for i, handler in enumerate(event_handlers):
                logger.debug(f"  处理器{i + 1}: {handler}")

            logger.info("等待新消息中...")

            # 启动状态监控任务
            self.tasks.extend([
                self.loop.create_task(self._monitor_status()),
                self.loop.create_task(self._periodic_status_check()),
                self.loop.create_task(self.check_status())
            ])

            # 运行直到收到停止信号
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"启动时出错: {str(e)}")
            import traceback
            logger.error(f"完整错误信息:\n{traceback.format_exc()}")
            raise
        finally:
            await self.cleanup()

    async def handle_signal(self, sig):
        """处理系统信号"""
        logger.info(f"收到信号 {sig.name}，准备关闭...")
        self.running = False

    async def _monitor_status(self):
        """监控状态，定期检查是否需要恢复监听"""
        while True:
            try:
                if not self.is_listening and self.pause_until:
                    if datetime.now(beijing_tz) >= self.pause_until and self.anti_ban_strategies.is_work_time():
                        self.resume_listening()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"状态监控出错: {e}")
                await asyncio.sleep(60)

    async def _periodic_status_check(self):
        """定期检查系统状态并发送报告"""
        while True:
            try:
                # 每30分钟执行一次状态检查
                await asyncio.sleep(1800)

                # 获取当前时间
                current_time = datetime.now(beijing_tz)

                # 检查工作状态
                is_work_time = self.anti_ban_strategies.is_work_time()
                is_safe_time = self.anti_ban_strategies.is_safe_time()
                can_send = self.anti_ban_strategies.can_send_message()

                # 构建状态报告
                status_report = [
                    "📊 系统状态报告",
                    f"⏰ 当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"🎯 监听状态: {'✅ 正在监听' if self.is_listening else '⏸️ 已暂停'}",
                    f"⌛ 暂停时间: {self.pause_until.strftime('%Y-%m-%d %H:%M:%S') if self.pause_until else '无'}",
                    f"👥 用户客户端: {'✅ 已连接' if self.user_client.is_connected() else '❌ 未连接'}",
                    f"🤖 Bot客户端: {'✅ 已连接' if self.bot_client.is_connected() else '❌ 未连接'}",
                    f"📈 消息统计:",
                    f"  • 分钟内: {self.anti_ban_strategies.message_count['minute']}/{self.anti_ban_config.MAX_MESSAGES_PER_MINUTE}",
                    f"  • 小时内: {self.anti_ban_strategies.message_count['hour']}/{self.anti_ban_config.MAX_MESSAGES_PER_HOUR}",
                    f"  • 今日内: {self.anti_ban_strategies.message_count['day']}/{self.anti_ban_config.MAX_MESSAGES_PER_DAY}",
                    f"⚙️ 系统检查:",
                    f"  • 工作时间: {'✅' if is_work_time else '❌'}",
                    f"  • 安全时间: {'✅' if is_safe_time else '❌'}",
                    f"  • 发送限制: {'✅ 可发送' if can_send else '❌ 已限制'}",
                    f"  • 已处理消息数: {len(self.processed_messages)}",
                    f"  • 延迟倍数: {self.anti_ban_strategies.current_delay_multiplier:.2f}",
                    f"  • 连续错误: {self.anti_ban_strategies.consecutive_errors}"
                ]

                # 发送状态报告
                status_message = "\n".join(status_report)
                if self.bot_client and self.bot_client.is_connected():
                    await self.bot_client.send_message(LOGS_CHANNEL[0], status_message)
                    logger.info("✅ 已发送状态报告")

            except Exception as e:
                logger.error(f"状态检查出错: {e}")
                await asyncio.sleep(300)  # 出错后等待5分钟再试


def main():
    """主函数"""
    forwarder = None
    try:
        # 启动 Flask 在新线程
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()

        # 创建转发器实例
        forwarder = MessageForwarder()

        # 运行转发器
        if forwarder.loop and not forwarder.loop.is_closed():
            forwarder.loop.run_until_complete(forwarder.start())
        else:
            logger.error("事件循环未初始化或已关闭")
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    except Exception as e:
        logger.error(f"主函数运行出错: {str(e)}")
        import traceback
        logger.error(f"完整错误信息:\n{traceback.format_exc()}")
    finally:
        # 确保资源被正确清理
        if forwarder and forwarder.loop and not forwarder.loop.is_closed():
            try:
                forwarder.loop.run_until_complete(forwarder.cleanup())
                forwarder.loop.close()
            except Exception as e:
                logger.error(f"清理资源时出错: {str(e)}")


if __name__ == "__main__":
    main()