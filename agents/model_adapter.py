from abc import ABC, abstractmethod
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, AuthenticationError
import httpx
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
    def __init__(self, api_key, base_url, model_name, request_timeout=120, max_retries=5, initial_backoff_seconds=2, proxy_url=None, proxy_username=None, proxy_password=None):
        print(f"[OpenAIAdapter __init__] Initializing with base_url: {base_url}")
        print(f"[OpenAIAdapter __init__] Initial request_timeout: {request_timeout}, max_retries: {max_retries}")
        self.model_name = model_name
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds

        if proxy_url:
            original_http_proxy = os.environ.get('HTTP_PROXY')
            original_https_proxy = os.environ.get('HTTPS_PROXY')

            # Refined logic for full_proxy_url construction:
            temp_proxy_url = proxy_url # Work with a temporary variable

            # Separate scheme from the host/auth part
            scheme = "http" # Default scheme
            host_auth_part = temp_proxy_url

            if "://" in temp_proxy_url:
                scheme, host_auth_part = temp_proxy_url.split("://", 1)

            # Check if host_auth_part (e.g., user:pass@host:port or host:port) already contains credentials
            if "@" in host_auth_part:
                # Credentials are in the URL, use it as is with its original scheme (or default if none was stripped)
                full_proxy_url = f"{scheme}://{host_auth_part}"
            elif proxy_username:
                # Credentials provided as parameters, prepend them to the host_auth_part
                auth_string = proxy_username
                if proxy_password:
                    auth_string += f":{proxy_password}"
                full_proxy_url = f"{scheme}://{auth_string}@{host_auth_part}"
            else:
                # No credentials in URL and no credentials in parameters
                full_proxy_url = f"{scheme}://{host_auth_part}"

            try:
                os.environ['HTTP_PROXY'] = full_proxy_url
                os.environ['HTTPS_PROXY'] = full_proxy_url

                print(f"[OpenAIAdapter __init__] Attempting to use proxy: {full_proxy_url}")
                print(f"[OpenAIAdapter __init__] HTTP_PROXY before httpx.Client(): {os.environ.get('HTTP_PROXY')}")
                print(f"[OpenAIAdapter __init__] HTTPS_PROXY before httpx.Client(): {os.environ.get('HTTPS_PROXY')}")

                # httpx.Client() will pick up proxy settings from env vars
                # Pass a new httpx_client to OpenAI so it picks up the env vars at its initialization time
                httpx_client = httpx.Client()
                self.client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    http_client=httpx_client
                )
                print(f"[OpenAIAdapter __init__] OpenAI client configured with custom httpx.Client for proxy.")
            finally:
                # Restore original environment variables
                if original_http_proxy is None:
                    os.environ.pop('HTTP_PROXY', None)
                else:
                    os.environ['HTTP_PROXY'] = original_http_proxy

                if original_https_proxy is None:
                    os.environ.pop('HTTPS_PROXY', None)
                else:
                    os.environ['HTTPS_PROXY'] = original_https_proxy
            print(f"# original_http_proxy='{original_http_proxy}' original_https_proxy='{original_https_proxy}'")
            print(f"# '{self}', '{api_key}', '{base_url}', '{model_name}', '{request_timeout}', '{max_retries}', '{initial_backoff_seconds}', '{proxy_url}', '{proxy_username}', '{proxy_password}'")
        else:
            # If no proxy_url, initialize OpenAI client without custom http_client
            # It will use its own default httpx.Client()
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            print(f"[OpenAIAdapter __init__] OpenAI client configured without custom proxy httpx.Client.")

    def get_response(self, messages, **kwargs):
        retries = 0
        backoff_seconds = self.initial_backoff_seconds

        # Prepare parameters for the API call (moved here to be available for initial print)
        # Prioritize model from kwargs if provided, otherwise use self.model_name
        params = {
            "messages": messages,
            **kwargs
        }
        if 'model' not in params:
            params['model'] = self.model_name

        params['stream'] = True # Enable streaming

        print(f"[OpenAIAdapter get_response] Using OpenAI client with base_url: {self.client.base_url}")
        # Attempt to convert params to string for logging, handling potential circular references or complex objects if any.
        try:
            params_str = str(params)
        except Exception:
            params_str = "Could not convert params to string for logging."
        print(f"[OpenAIAdapter get_response] Attempting to send request with parameters: {params_str}")

        while retries <= self.max_retries:
            try:
                completion_stream = self.client.chat.completions.create(**params, timeout=self.request_timeout)

                print("[OpenAIAdapter get_response] Request was sent with stream=True. Processing stream...")
                collected_content = []
                last_chunk = None # To store the last chunk for model/id if needed

                try:
                    for chunk in completion_stream:
                        print(f"[OpenAIAdapter get_response] Received stream chunk: {chunk.model_dump_json(indent=2)}")
                        last_chunk = chunk # Keep track of the last chunk
                        if chunk.choices:
                            choice = chunk.choices[0]
                            if choice.delta and choice.delta.content is not None:
                                collected_content.append(choice.delta.content)
                            if choice.finish_reason is not None:
                                print(f"[OpenAIAdapter get_response] Stream finished with reason: {choice.finish_reason}")

                    full_response_content = "".join(collected_content)
                    print(f"[OpenAIAdapter get_response] Collected full content from stream: {full_response_content}")

                    class MockMessage:
                        def __init__(self, content):
                            self.content = content
                            self.tool_calls = None

                    class MockChoice:
                        def __init__(self, content):
                            self.message = MockMessage(content)
                            self.finish_reason = "stop"

                    class MockCompletion:
                        def __init__(self, content, model_name_from_stream=None, response_id=None):
                            self.choices = [MockChoice(content)]
                            self.model = model_name_from_stream if model_name_from_stream else params.get('model')
                            self.id = response_id if response_id else "streamed_response"
                            # Initialize other common attributes to None or default values
                            self.created = int(time.time()) # Unix timestamp
                            self.object = "chat.completion" # Default object type for chat completions
                            self.system_fingerprint = None
                            self.usage = None # Usage info is not typically available directly from stream in this manner

                    model_name_to_use = None
                    response_id_to_use = None
                    if last_chunk: # Safely access attributes from the last chunk
                        if hasattr(last_chunk, 'model') and last_chunk.model:
                            model_name_to_use = last_chunk.model
                        if hasattr(last_chunk, 'id') and last_chunk.id:
                            response_id_to_use = last_chunk.id

                    final_completion_response = MockCompletion(full_response_content, model_name_to_use, response_id_to_use)
                    return final_completion_response

                except Exception as e:
                    print(f"[OpenAIAdapter get_response] Error while processing stream: {type(e).__name__} - {str(e)}")
                    traceback.print_exc()
                    return None

            except httpx.TimeoutException as e:
                print(f"OpenAI API Call failed due to httpx.TimeoutException: {type(e).__name__} - {str(e)}")
                print(f"URL that was requested: {e.request.url if e.request else 'N/A'}")
                traceback.print_exc()
                # For timeout, retrying might be applicable depending on strategy, here we just return None after retries exhausted
                # Fall through to retry logic if desired, or handle specifically. For now, let it be caught by retry logic for 5xx.
                # If we want to retry httpx.TimeoutException specifically, need to adjust retry logic or add a specific retry counter here.
                # For this change, we are just logging and then it will be handled by the generic retry for 5xx or fail.
                # A more robust solution might involve specific retry conditions for timeouts.
                # For now, let's print and let the existing retry logic (if any applicable) or failure occur.
                # The current retry logic is for APIError 5xx, so this will likely fall through to the generic Exception or fail immediately.
                # Let's make it return None for now, consistent with other specific error handlers.
                return None
            except httpx.RequestError as e:
                print(f"OpenAI API Call failed due to httpx.RequestError: {type(e).__name__} - {str(e)}")
                print(f"URL that was requested: {e.request.url if e.request else 'N/A'}")
                traceback.print_exc()
                return None
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
            model_name=config.get("model_name"),
            request_timeout=config.get("request_timeout", 120),
            max_retries=config.get("max_retries", 5),
            initial_backoff_seconds=config.get("initial_backoff_seconds", 2),
            proxy_url=config.get("proxy_url"),
            proxy_username=config.get("proxy_username"),
            proxy_password=config.get("proxy_password")
        )
    elif model_type == "ollama":
        return OllamaAdapter(
            base_url=config.get("base_url", "http://localhost:11434"),
            model_name=config.get("model_name", "qwen2:7b") # 默认为qwen2:7b
        )
    else:
        raise ValueError(f"Unsupported model type: {model_type}")
