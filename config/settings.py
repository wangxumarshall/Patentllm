import os

# 从环境变量或配置文件中读取 API 密钥
# OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'sk-********')
# OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/')
SERP_API_KEY = os.getenv('SERP_API_KEY', 'fd4cbc958a28c07f9ed39872ec94bacf2909e85580322a2473ce0a98ebd894ce')
SERP_API_URL = os.getenv('SERP_API_URL', 'https://serpapi.com/search.json')

# 上传文件夹配置
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

# Flask 应用密钥
SECRET_KEY = 'your-secret-key-123'

# 是否启用评估功能
ENABLE_EVALUATION = os.getenv('ENABLE_EVALUATION', 'True').lower() == 'true'

# 模型配置
# 可以将这些配置移到环境变量或专门的YAML/JSON文件中
ACTIVE_MODEL_CONFIG = {
    "type": os.getenv('MODEL_TYPE', 'openai'), # 默认为openai, 可设置为 'ollama'
    "openai": {
        "api_key": "sk-1234",  # 将这里替换为您的真实 OpenAI API Key
        #"base_url": os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/'),
        "base_url": os.getenv('OPENAI_BASE_URL', 'http://api.openai.rnd.huawei.com'),
        "default_model": "qwq-32b-128k"
    },
    "ollama": {
        "base_url": os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
        "default_model": "qwen3:8b" # 确保这个模型已经在Ollama中拉取并可用
    }
}

# 根据激活的模型类型选择具体配置
MODEL_CONFIG = {
    "type": ACTIVE_MODEL_CONFIG["type"],
    "api_key": ACTIVE_MODEL_CONFIG.get(ACTIVE_MODEL_CONFIG["type"], {}).get("api_key") if ACTIVE_MODEL_CONFIG["type"] == "openai" else None,
    "base_url": ACTIVE_MODEL_CONFIG.get(ACTIVE_MODEL_CONFIG["type"], {}).get("base_url"),
    "model_name": ACTIVE_MODEL_CONFIG.get(ACTIVE_MODEL_CONFIG["type"], {}).get("default_model")
}
    
