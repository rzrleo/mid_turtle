# config.py
import os
import secrets

# 基本配置
DEBUG = True
SECRET_KEY = secrets.token_hex(16)  # 生成随机密钥

# 游戏配置
MAX_QUESTIONS = 10  # 最大提问次数
SPECIAL_USERNAMES = ["0104", "0624"]  # 特殊用户名
ROOM_TIMEOUT = 3600  # 房间过期时间（秒）

# 文件路径
STORIES_PATH = os.path.join(os.path.dirname(__file__), 'static/data/stories.json')

# API配置
DEEPSEEK_API_KEY = "sk-cf567b2a17ce4cf9ad7ad39789e380f4"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 服务器配置
HOST = "0.0.0.0"
PORT = 5001