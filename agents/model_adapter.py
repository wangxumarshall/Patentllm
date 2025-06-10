from abc import ABC, abstractmethod
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, AuthenticationError
import requests
import json
import traceback
import os
import time

class BaseModelAdapter(ABC):
    @abstractmethod
    def get_response(self, messages, **kwargs):
        pass

class OpenAIAdapter(BaseModelAdapter):
    def __init__(self, api_key, base_url, model_name="deepseek-chat", request_timeout=60, max_retries=3, initial_backoff_seconds=1):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds

    def get_response(self, messages, **kwargs):
        retries = 0
        backoff_seconds = self.initial_backoff_seconds
        while retries <= self.max_retries:
            try:
                # Prepare parameters for the API call
                # Prioritize model from kwargs if provided, otherwise use self.model_name
                params = {
                    "messages": messages,
                    **kwargs
                }
                if 'model' not in params:
                    params['model'] = self.model_name

                completion = self.client.chat.completions.create(**params, timeout=self.request_timeout)
                return completion
            except APIConnectionError as e:
                print(f"OpenAI API ConnectionError: Failed to connect to OpenAI at {self.client.base_url}. Error.")
                traceback.print_exc()
                http_proxy = os.getenv('HTTP_PROXY')
                https_proxy = os.getenv('HTTPS_PROXY')
                print(f"Proxy Information: HTTP_PROXY='{http_proxy}' HTTPS_PROXY='{https_proxy}'")
                return None
        except RateLimitError as e:
            print(f"OpenAI API RateLimitError: Rate limit exceeded for {self.client.base_url}. Error. ")
            traceback.print_exc()
            return None
        except AuthenticationError as e:
            print(f"OpenAI API AuthenticationError: Authentication failed for {self.client.base_url}. Error. ")
            traceback.print_exc()
            return None
        except APIError as e: # Catch other OpenAI API errors
            if hasattr(e, 'status_code') and 500 <= e.status_code <= 599:
                if retries < self.max_retries:
                    print(f"OpenAI API 5xx error (Status: {e.status_code}). Retrying in {backoff_seconds}s... (Attempt {retries + 1}/{self.max_retries})")
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                    retries += 1
                    continue
                else:
                    print(f"OpenAI API call failed after {self.max_retries} retries for a 5xx error (Status: {e.status_code}).")
                    traceback.print_exc()
                    return None
            
            # Handle non-5xx APIErrors or if retries exhausted for 5xx
            print(f"OpenAI APIError: Encountered API error of type '{type(e).__name__}' with {self.client.base_url}.")
            
            if hasattr(e, 'status_code') and e.status_code is not None:
                print(f"  Status Code: {e.status_code}")
            else:
                print(f"  Status Code: Not available")

            if hasattr(e, 'code') and e.code is not None:
                 print(f"  Error Code: {e.code}")
            else:
                print(f"  Error Code: Not available")

            if hasattr(e, 'body') and e.body is not None:
                body_info = f"type: {type(e.body).__name__}, length: {len(str(e.body))}"
                print(f"  Error Body Info: {body_info}. Content omitted for brevity. Enable debug for full body.")
            else:
                print(f"  Error Body Info: Not available or empty.")

            print("  Traceback:")
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"OpenAI API call failed (unexpected error): Could not process request for {self.client.base_url}. Error.")
            traceback.print_exc()
            return None

        # If loop finishes, all retries failed for 5xx errors
        if retries > self.max_retries: # Should be retries == self.max_retries + 1 if loop exited due to retries
            print(f"OpenAI API call failed after {self.max_retries} retries for a 5xx error.")
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
            model_name=config.get("model_name", "deepseek-chat"),
            request_timeout=config.get("request_timeout", 60),
            max_retries=config.get("max_retries", 3),
            initial_backoff_seconds=config.get("initial_backoff_seconds", 1)
        )
    elif model_type == "ollama":
        return OllamaAdapter(
            base_url=config.get("base_url", "http://localhost:11434"),
            model_name=config.get("model_name", "qwen2:7b") # 默认为qwen2:7b
        )
    else:
        raise ValueError(f"Unsupported model type: {model_type}")
