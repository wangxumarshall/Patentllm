from abc import ABC, abstractmethod
from openai import OpenAI
import requests
import json

class BaseModelAdapter(ABC):
    @abstractmethod
    def get_response(self, messages, **kwargs):
        pass

class OpenAIAdapter(BaseModelAdapter):
    def __init__(self, api_key, base_url, model_name="deepseek-chat"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def get_response(self, messages, **kwargs):
        try:
            # Prepare parameters for the API call
            # Prioritize model from kwargs if provided, otherwise use self.model_name
            params = {
                "messages": messages,
                **kwargs
            }
            if 'model' not in params:
                params['model'] = self.model_name
            
            completion = self.client.chat.completions.create(**params)
            return completion
        except Exception as e:
            print(f"OpenAI API call failed: {str(e)}")
            return None

class OllamaAdapter(BaseModelAdapter):
    def __init__(self, base_url="http://localhost:11434", model_name="qwen2:7b"):
        self.base_url = base_url
        self.model_name = model_name
        self.api_endpoint = f"{self.base_url}/api/chat"

    def get_response(self, messages, **kwargs):
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False, # 根据需要设置是否流式输出
            **kwargs
        }
        try:
            response = requests.post(self.api_endpoint, json=payload)
            response.raise_for_status() # 如果请求失败则抛出HTTPError
            # Ollama的响应格式可能与OpenAI不同，需要适配
            # 假设Ollama返回的格式中，消息内容在 response.json()['message']['content']
            # 并且需要构造成与OpenAI completion对象类似的结构，至少包含 choices[0].message.content
            # 这是一个简化的示例，您可能需要根据Ollama的实际输出来调整
            class MockChoice:
                def __init__(self, content):
                    self.message = MockMessage(content)
            class MockMessage:
                def __init__(self, content):
                    self.content = content
                    self.tool_calls = None # 假设Ollama当前不支持tool_calls，或需要额外处理
            
            response_data = response.json()
            # 检查Ollama的响应结构，提取需要的内容
            # 例如，如果Ollama的响应是 {'model': 'qwen2:7b', 'created_at': '...', 'message': {'role': 'assistant', 'content': '...'}, 'done': True, ...}
            assistant_content = response_data.get('message', {}).get('content', '')
            
            # 模拟OpenAI的completion对象结构
            class MockCompletion:
                def __init__(self, content):
                    self.choices = [MockChoice(content)]
            
            return MockCompletion(assistant_content)

        except requests.exceptions.RequestException as e:
            print(f"Ollama API call failed: {str(e)}")
            return None
        except json.JSONDecodeError:
            print(f"Failed to decode Ollama API response: {response.text}")
            return None

# 可以在这里添加一个工厂函数来根据配置创建适配器实例
def get_model_adapter(config):
    model_type = config.get("type")
    if model_type == "openai":
        return OpenAIAdapter(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model_name=config.get("model_name", "deepseek-chat")
        )
    elif model_type == "ollama":
        return OllamaAdapter(
            base_url=config.get("base_url", "http://localhost:11434"),
            model_name=config.get("model_name", "qwen2:7b") # 默认为qwen2:7b
        )
    else:
        raise ValueError(f"Unsupported model type: {model_type}")