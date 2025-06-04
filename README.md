# Telegram 消息转发器

一个简单的 Telegram 消息转发工具，可以监听多个源频道并将消息转发到指定目标频道。

## 功能特点

- 支持监听多个源频道
- 自动转发消息到目标频道
- 保留原始消息的媒体内容
- 添加源频道和时间戳信息
- 支持代理设置
- 详细的日志记录

## 使用方法

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量：
   - 复制 `.env.example` 为 `.env`
   - 填入您的 Telegram API 凭据和频道信息
   - 如需使用代理，设置相应的代理配置

3. 运行程序：
```bash
python forward_bot.py
```

## 环境变量说明

- `API_ID`: Telegram API ID
- `API_HASH`: Telegram API Hash
- `SOURCE_CHANNELS`: 源频道列表，用逗号分隔（例如：@channel1,@channel2,@channel3）
- `TARGET_CHANNEL`: 目标频道
- `PROXY_ENABLED`: 是否启用代理（true/false）
- `PROXY_TYPE`: 代理类型（http/socks5）
- `PROXY_ADDRESS`: 代理服务器地址
- `PROXY_PORT`: 代理服务器端口

## 注意事项

1. 首次运行时需要进行 Telegram 账号验证
2. 确保账号有权限访问源频道和目标频道
3. 如果在中国大陆使用，建议配置代理
4. 程序会自动创建日志文件
