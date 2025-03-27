# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from openai import OpenAI
import json
import requests
import time
import os
from PyPDF2 import PdfReader
import markdown
from werkzeug.utils import secure_filename
from datetime import datetime
import random
from urllib.parse import quote_plus

app = Flask(__name__)
app.secret_key = 'your-secret-key-123'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 初始化 OpenAI 客户端
client = OpenAI(
    api_key="sk-********",###这个是deepseek的api
    base_url="https://api.deepseek.com/",
)

# SerpAPI配置
SERP_API_KEY = "********"  # 这个是SerpAPI密钥
SERP_API_URL = "https://serpapi.com/search.json"

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
            completion = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            return completion
        except Exception as e:
            print(f"API调用失败: {str(e)}")
            return None

    def conduct_research(self, patent_text):
        self.research_materials["original_text"] = patent_text

        system_prompt = """你是一个华为公司法务研究专家，负责：
        1. 阅读并理解专利内容
        2. 根据专利特征和领域进行互联网搜索
        3. 收集相关技术信息和潜在侵权线索
        4. 搜索内容不要仅限于专利而需要更关注现有的技术比如技术源码等,查找除了华为公司以外的潜在侵权线索,如果有线索可以把具体网址(超链接形式)或者关键词列出来,如果是查找到其他的专利只能找发布时间不能早于公司专利的专利
        5. 当不再需要搜索时，输出"研究完成"四个字"""

        messages = [
            {"role": "system", "content": system_prompt},
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

        return self.research_materials


class SummaryAgent:
    def __init__(self):
        pass

    def get_response(self, messages):
        try:
            completion = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages
            )
            return completion
        except Exception as e:
            print(f"API调用失败: {str(e)}")
            return None

    def generate_summary(self, research_materials):
        system_prompt = """你是一个华为公司法务总结专家，请根据以下材料：
        1. 原始专利文本
        2. 研究搜索结果
        3. 你自己的专业知识
        生成一份专业的专利侵权分析报告。

        要求：
        1. 提炼专利特征和领域，显示公司专利名称和专利号，专利号在名称上面
        2. 分析潜在侵权线索
        3. 使用严格的Markdown格式,不要出现表格结构的输出,也不要输出字样'```markdown','```'
        4. 包含清晰的标题层级
        5. 重要关键词用**加粗**显示
        6. 如果有线索可以把关键词列出来,最好把具体网址也列出来,如果涉及到其他的专利其发布时间不能早于公司专利
        7. 按以下格式输出：
            ## 1. 专利特征分析
            ### 1.1 专利名称
            内容...

            ### 1.2 技术领域
            内容...

            ### 1.3 主要特征
            - **特征分类1**：
              • 具体特征描述1
              • 具体特征描述2

            - **特征分类2**：
              • 具体特征描述1"""

        research_context = f"""原始专利内容：
        {research_materials['original_text']}

        搜索结果：
        {json.dumps(research_materials['search_results'], indent=2, ensure_ascii=False)}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": research_context}
        ]

        response = self.get_response(messages)
        if not response:
            return "总结失败"

        final_answer = f"## 分析结果\n{response.choices[0].message.content}\n\n"
        print("final answer:",final_answer)
        return markdown.markdown(final_answer)


class PatentAnalyzer:
    def __init__(self):
        self.research_agent = ResearchAgent()
        self.summary_agent = SummaryAgent()

    def extract_text(self, file_input):
        return self.research_agent.extract_text(file_input)

    def analyze_patent(self, patent_text):
        # 第一阶段：研究代理收集信息
        research_materials = self.research_agent.conduct_research(patent_text)
        if not research_materials:
            return "分析失败"

        # 第二阶段：总结代理生成报告
        return self.summary_agent.generate_summary(research_materials)


# 以下路由和视图函数保持不变...
@app.route('/')
def home():
    return redirect(url_for('upload'))


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' in request.files:
            file = request.files['file']
            if file.filename != '':
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])

                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                session['source_type'] = 'file'
                session['source'] = filename
                return redirect(url_for('analyzing'))

        elif 'url' in request.form and request.form['url']:
            url = request.form['url'].strip()
            if url:
                session['source_type'] = 'url'
                session['source'] = url
                return redirect(url_for('analyzing'))

    return render_template('upload.html')


@app.route('/analyzing')
def analyzing():
    if 'source_type' not in session:
        return redirect(url_for('upload'))
    return render_template('analyzing.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'source_type' not in session:
        return jsonify(error="无效的会话")

    source_type = session['source_type']
    source = session['source']
    patent_text = None

    try:
        if source_type == 'file':
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], source)
            patent_text = PatentAnalyzer().extract_text(filepath)
        elif source_type == 'url':
            try:
                response = requests.get(source, timeout=10)
                response.raise_for_status()
                patent_text = response.text
            except Exception as e:
                return jsonify(error=f"无法下载网页内容: {str(e)}")
        else:
            return jsonify(error="无效的输入类型")

        if not patent_text:
            return jsonify(error="无法提取有效文本内容")

        analyzer = PatentAnalyzer()
        result = analyzer.analyze_patent(patent_text)
        session['analysis_result'] = result
        return jsonify(result=result)

    except Exception as e:
        print(f"分析过程中出错: {str(e)}")
        return jsonify(error=f"分析过程中出错: {str(e)}")


@app.route('/report')
def report():
    if 'analysis_result' not in session:
        return redirect(url_for('upload'))

    report_id = f"HW-PAT-{datetime.now().year}-{random.randint(1000, 9999)}"
    report_time = datetime.now()

    return render_template(
        'report.html',
        result=session['analysis_result'],
        report_id=report_id,
        report_time=report_time
    )


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)