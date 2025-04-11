import requests
import json
import time
from openai import OpenAI
from PyPDF2 import PdfReader
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, SERP_API_KEY, SERP_API_URL

# 工具定义
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "当需要获取最新互联网信息时使用,如果有多个需要查询的问题可以分成多次查询",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "after_date": {"type": "string", "description": "只返回此日期之后的结果，格式YYYY-MM-DD"}
                },
                "required": ["query"]
            }
        }
    }
]


class ResearchAgent:
    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )
        self.search_count = 0
        self.research_materials = {
            "original_text": "",
            "search_results": []
        }

    def extract_text(self, file_input):
        """从PDF文件或文件路径提取文本"""
        if isinstance(file_input, str):
            if file_input.endswith('.pdf'):
                try:
                    with open(file_input, 'rb') as f:
                        pdf_reader = PdfReader(f)
                        return self._extract_pdf_text(pdf_reader)
                except Exception as e:
                    print(f"文件读取失败: {str(e)}")
                    return None
            return None

        if hasattr(file_input, 'filename') and file_input.filename.endswith('.pdf'):
            try:
                pdf_reader = PdfReader(file_input)
                return self._extract_pdf_text(pdf_reader)
            except Exception as e:
                print(f"PDF解析失败: {str(e)}")
                return None

        return None

    def _extract_pdf_text(self, pdf_reader):
        """从PDF阅读器提取文本"""
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text if text else None

    def search_internet(self, arguments):
        try:
            query = arguments["query"]
            after_date = arguments.get("after_date", "")

            params = {
                'api_key': SERP_API_KEY,
                'q': query,
                'engine': 'google',
                'num': 30  # 每次获取10条结果
            }

            # 如果有日期筛选条件
            if after_date:
                params['q'] = f'{query} after:{after_date}'

            response = requests.get(SERP_API_URL, params=params, timeout=15)
            response.raise_for_status()

            results = response.json().get('organic_results', [])
            self.search_count += len(results)

            # 格式化搜索结果
            search_result = "\n".join([f"{i + 1}. {res.get('snippet', '')} [URL: {res.get('link', '')}]"
                                       for i, res in enumerate(results)])

            self.research_materials["search_results"].append({
                "query": query,
                "result": search_result,
                "urls": [res.get('link', '') for res in results],  # 单独保存URL列表
                "after_date": after_date  # 保存日期筛选条件
            })

            return search_result

        except Exception as e:
            print(f"SerpAPI搜索失败: {str(e)}")
            return "暂时无法获取SerpAPI搜索结果"

    def get_response(self, messages):
        try:
            completion = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            return completion
        except Exception as e:
            print(f"API调用失败: {str(e)}")
            return None

    def conduct_research(self, patent_text, research_prompt):
        self.research_materials["original_text"] = patent_text
    
        messages = [
            {"role": "system", "content": research_prompt},
            {"role": "user", "content": patent_text}
        ]
    
        max_rounds = 5
        for _ in range(max_rounds):
            response = self.get_response(messages)
            if not response:
                return None
    
            assistant_msg = response.choices[0].message
            messages.append(assistant_msg)
    
            if not assistant_msg.tool_calls:
                if "研究完成" in assistant_msg.content:
                    return self.research_materials
                continue
    
            tool_responses = []
            for tool_call in assistant_msg.tool_calls:
                if tool_call.function.name == "search_internet":
                    arguments = json.loads(tool_call.function.arguments)
                    print(f"\n[执行搜索] 关键词: {arguments['query']} 日期筛选: after:{arguments.get('after_date', '无')}")
                    result = self.search_internet(arguments)
                    print(f"[搜索结果] 摘要: {result}...")  # 显示部分结果
                    tool_responses.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "search_internet",
                        "content": result
                    })
    
            messages.extend(tool_responses)
            time.sleep(1)  # 避免触发API速率限制
    
        # 在处理搜索结果时，添加对目标企业的标记
        # 从 research_prompt 中提取目标企业信息
        target_companies = []
        if "请重点挖掘以下企业的产品或技术" in research_prompt:
            try:
                target_section = research_prompt.split("请重点挖掘以下企业的产品或技术")[1].split("\n")[0]
                companies_part = target_section.split("：")[1] if "：" in target_section else ""
                if companies_part:
                    target_companies = [company.strip() for company in companies_part.split("、")]
            except:
                pass
        
        # 标记来自目标企业的搜索结果
        for result in self.research_materials.get('search_results', []):
            result_text = result.get('result', '').lower()
            for company in target_companies:
                if company.lower() in result_text:
                    result['is_target_company'] = True
                    # 可以添加额外的处理逻辑，例如提高优先级
                    break
            else:
                result['is_target_company'] = False
        
        return self.research_materials
    