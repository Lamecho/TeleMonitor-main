# 防封配置文件
from loguru import logger
import random
import time
from datetime import datetime
import pytz

class AntiBanConfig:
    """防封配置"""

    # 节流控制（更保守的设置）
    MAX_MESSAGES_PER_MINUTE = 3   # 每分钟最大消息数
    MAX_MESSAGES_PER_HOUR = 25    # 每小时最大消息数
    MAX_MESSAGES_PER_DAY = 400    # 每天最大消息数

    # 延迟设置（更长的延迟）
    MIN_DELAY = 5     # 最小延迟秒数
    MAX_DELAY = 20    # 最大延迟秒数
    BURST_DELAY = 45  # 连续消息后的额外延迟

    # 错误处理
    MAX_CONSECUTIVE_ERRORS = 3    # 最大连续错误数
    COOLDOWN_TIME = 120          # 冷却时间（秒）
    EXPONENTIAL_BACKOFF = True   # 指数退避

    # 动态延迟
    ADAPTIVE_DELAY = True        # 启用自适应延迟
    SUCCESS_REDUCE_FACTOR = 0.9  # 成功时减少延迟的因子
    ERROR_INCREASE_FACTOR = 2.0  # 错误时增加延迟的因子

    # 危险错误关键词
    DANGEROUS_ERRORS = [
        "PEER_FLOOD", "FLOOD_WAIT", "AUTH_KEY_DUPLICATED", "SESSION_REVOKED",
        "USER_DEACTIVATED", "PHONE_NUMBER_BANNED", "USER_RESTRICTED", "CHAT_WRITE_FORBIDDEN"
    ]

    # 垃圾消息关键词
    SPAM_KEYWORDS = ["广告", "推广", "代理", "刷单", "兼职", "加微信"]

    # 安全建议
    SAFETY_TIPS = [
        "1. 避免短时间内大量操作",
        "2. 使用随机延迟避免机器人检测",
        "3. 监控错误日志，及时处理异常",
        "4. 定期更换IP和设备信息",
        "5. 避免在敏感时段大量操作",
        "6. 保持账号正常使用习惯",
        "7. 使用代理分散风险",
        "8. 备份重要数据和会话文件"
    ]

class AntiBanStrategies:
    """防封策略集合"""

    def __init__(self):
        self.message_count = {'minute': 0, 'hour': 0, 'day': 0}
        self.last_reset = {'minute': 0, 'hour': 0, 'day': 0}
        self.consecutive_errors = 0
        self.current_delay_multiplier = 1.0
        self.last_message_time = 0

    def reset_counters(self):
        """重置计数器"""
        current_time = time.time()

        if current_time - self.last_reset['minute'] >= 60:
            self.message_count['minute'] = 0
            self.last_reset['minute'] = current_time

        if current_time - self.last_reset['hour'] >= 3600:
            self.message_count['hour'] = 0
            self.last_reset['hour'] = current_time

        if current_time - self.last_reset['day'] >= 86400:
            self.message_count['day'] = 0
            self.last_reset['day'] = current_time

    def can_send_message(self):
        """检查是否可以发送消息"""
        self.reset_counters()
        config = AntiBanConfig()
        return (self.message_count['minute'] < config.MAX_MESSAGES_PER_MINUTE and
                self.message_count['hour'] < config.MAX_MESSAGES_PER_HOUR and
                self.message_count['day'] < config.MAX_MESSAGES_PER_DAY)

    def get_adaptive_delay(self):
        """获取自适应延迟"""
        config = AntiBanConfig()
        base_delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)

        if config.ADAPTIVE_DELAY:
            base_delay *= self.current_delay_multiplier

        # 连续发送消息增加额外延迟
        if time.time() - self.last_message_time < 10:
            base_delay += config.BURST_DELAY

        return base_delay

    def record_success(self):
        """记录成功发送"""
        config = AntiBanConfig()
        self.message_count['minute'] += 1
        self.message_count['hour'] += 1
        self.message_count['day'] += 1
        self.consecutive_errors = 0
        self.last_message_time = time.time()

        if config.ADAPTIVE_DELAY:
            self.current_delay_multiplier = max(0.5,
                self.current_delay_multiplier * config.SUCCESS_REDUCE_FACTOR)

    def record_error(self, error_msg=""):
        """记录错误"""
        config = AntiBanConfig()
        self.consecutive_errors += 1

        if config.ADAPTIVE_DELAY:
            self.current_delay_multiplier *= config.ERROR_INCREASE_FACTOR

        if config.EXPONENTIAL_BACKOFF:
            return config.COOLDOWN_TIME * (2 ** min(self.consecutive_errors - 1, 5))
        return config.COOLDOWN_TIME

    @staticmethod
    def should_skip_message(message_text):
        """检查是否应该跳过消息"""
        config = AntiBanConfig()
        if not message_text or len(message_text.strip()) < 10:
            return True

        # 检查垃圾消息关键词
        text_lower = message_text.lower()
        spam_count = sum(1 for keyword in config.SPAM_KEYWORDS if keyword in text_lower)
        return spam_count >= 2

    @staticmethod
    def get_error_action(error_msg):
        """根据错误消息获取建议操作"""
        error_msg = error_msg.upper()

        if "FLOOD" in error_msg:
            return "立即停止操作，等待冷却"
        elif "BANNED" in error_msg or "RESTRICTED" in error_msg:
            return "账号可能被限制，需要人工检查"
        elif "SESSION" in error_msg:
            return "会话问题，需要重新登录"
        elif "CONNECTION" in error_msg:
            return "网络问题，可以重试"
        else:
            return "未知错误，建议谨慎处理"

    @staticmethod
    def is_work_time():
        """检查消息是否应该被处理
        - 工作日9:00-18:00：100%处理
        - 周末9:00-18:00：50%处理
        - 其他时间：30%处理
        """
        try:
            beijing_tz = pytz.timezone("Asia/Shanghai")
            current_time = datetime.now(beijing_tz)
            current_hour = current_time.hour
            is_weekend = current_time.weekday() >= 5

            # 检查是否在9:00-18:00之间
            in_work_hours = 9 <= current_hour <= 18

            # 如果不在9:00-18:00之间，30%概率处理
            if not in_work_hours:
                return random.random() < 0.3

            # 在9:00-18:00之间
            if is_weekend:
                # 周末工作时间，50%概率处理
                return random.random() < 0.5
            else:
                # 工作日工作时间，100%处理
                return True

        except Exception:
            return True  # 出错时默认为工作时间

    @staticmethod
    def should_process_weekend_message():
        """检查周末消息是否应该被处理（50%概率）"""
        try:
            beijing_tz = pytz.timezone("Asia/Shanghai")
            current_time = datetime.now(beijing_tz)
            # 检查是否为周末
            is_weekend = current_time.weekday() >= 5
            if not is_weekend:
                return True  # 非周末返回True
            # 周末时随机返回，50%概率为True
            return random.random() < 0.5
        except Exception:
            return True  # 出错时默认处理消息

    @staticmethod
    def is_safe_time():
        """检查是否为安全时间（避开敏感时段）"""
        try:
            beijing_tz = pytz.timezone("Asia/Shanghai")
            current_time = datetime.now(beijing_tz)
            current_hour = current_time.hour
            # 避开深夜和早晨时段
            return 7 <= current_hour <= 23
        except Exception:
            return True  # 出错时默认为安全时间

    @staticmethod
    def get_next_work_time():
        """获取下一个工作时间"""
        try:
            beijing_tz = pytz.timezone("Asia/Shanghai")
            current_time = datetime.now(beijing_tz)

            # 如果当前是工作时间，返回当前时间
            if AntiBanStrategies.is_work_time():
                return current_time

            # 如果当前小时 < 9，返回今天9点
            if current_time.hour < 9:
                return current_time.replace(hour=9, minute=0, second=0, microsecond=0)

            # 否则返回明天9点
            from datetime import timedelta
            next_day = current_time + timedelta(days=1)
            return next_day.replace(hour=9, minute=0, second=0, microsecond=0)
        except Exception:
            # 出错时返回1小时后
            from datetime import timedelta
            return datetime.now(pytz.timezone("Asia/Shanghai")) + timedelta(hours=1)



if __name__ == "__main__":
    print("防封配置加载完成")
    print("\n安全建议:")
    for tip in AntiBanConfig.SAFETY_TIPS:
        print(tip)