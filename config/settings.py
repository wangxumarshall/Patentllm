import os

# 从环境变量或配置文件中读取 API 密钥
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-********')
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/')
SERP_API_KEY = os.getenv('SERP_API_KEY', '********')
SERP_API_URL = os.getenv('SERP_API_URL', 'https://serpapi.com/search.json')

# 上传文件夹配置
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# Flask 应用密钥
SECRET_KEY = 'your-secret-key-123'
    