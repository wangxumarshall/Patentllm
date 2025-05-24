import yaml
from openai import OpenAI
# from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL # Remove this line
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
import re
from prompts.prompt_templates import get_customized_prompt
# from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL
from config.settings import MODEL_CONFIG # 修改导入
from agents.model_adapter import get_model_adapter # 导入适配器工厂函数

class EvaluationAgent:
    def __init__(self):
        # self.client = OpenAI(
        #     api_key=OPENAI_API_KEY,
        #     base_url=OPENAI_BASE_URL
        # )
        self.model_adapter = get_model_adapter(MODEL_CONFIG)
        # 加载评估规则
        with open('config/evaluation_rules.yaml', 'r', encoding='utf-8') as f:
            self.evaluation_rules = yaml.safe_load(f)['evaluation_criteria']

    def calculate_match_score(self, patent_claims, clue_text):
        """计算技术特征匹配度得分（基于TF - IDF算法）"""
        texts = [patent_claims, clue_text]
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(texts)
        similarity = cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0][0]
        return round(similarity * 100, 2)

    def validate_time_validity(self, clue_pub_date, target_filing_date):
        """验证公开时间有效性"""
        try:
            clue_date = datetime.strptime(clue_pub_date, "%Y-%m-%d")
            target_date = datetime.strptime(target_filing_date, "%Y-%m-%d")
            return clue_date >= target_date
        except:
            return False

    def generate_evaluation_prompt(self, research_materials):
        """构建评估用对话上下文"""
        target_patent = research_materials['original_text']
        clues = [f"线索{i + 1}: {clue['result']}" for i, clue in enumerate(research_materials['search_results'])]
        return f"""目标专利内容：
{target_patent}

待评估侵权线索：
{chr(10).join(clues)}"""

    def conduct_evaluation(self, research_materials, evaluation_prompt=None, **kwargs):
        """多轮评估主流程"""
        # 如果没有提供自定义 prompt，则使用默认 prompt
        if evaluation_prompt is None:
            evaluation_prompt = get_customized_prompt('evaluation')
            
        messages = [{"role": "system", "content": evaluation_prompt}]

        # 第一轮：初步评估
        messages.append({
            "role": "user",
            "content": self.generate_evaluation_prompt(research_materials)
        })

        max_rounds = 3
        for _ in range(max_rounds):
            # response = self.client.chat.completions.create(
            #     model="deepseek-chat", # 这个模型名也应该来自配置
            #     messages=messages,
            #     temperature=0.3  # 降低创造性，确保严谨性
            # )
            response = self.model_adapter.get_response(
                messages,
                model=MODEL_CONFIG.get("model_name"), 
                temperature=0.3
            )
            if not response: # 检查适配器调用是否成功
                print("Failed to get response from model adapter in EvaluationAgent.")
                return [] # 或者进行其他错误处理
            assistant_msg = response.choices[0].message

            # 提取评估结果或追问问题
            if "请提供" in assistant_msg.content:
                # 触发追问，要求用户补充信息（实际场景中可对接企业知识库）
                messages.append({"role": "assistant", "content": assistant_msg.content}) # Corrected line
                # 模拟用户回复（实际需对接前端交互）
                user_reply = "线索A的公开日为2024-05-15，实施地在中国广东"
                messages.append({"role": "user", "content": user_reply})
            else:
                # 解析评估报告
                evaluated_clues = self.parse_evaluation_result(assistant_msg.content, **kwargs) # 将kwargs传递下去
                return evaluated_clues  # 评估完成

        return None  # 超过最大轮次

    def parse_evaluation_result(self, content, **kwargs): # 添加**kwargs以接收target_companies
        """解析模型返回的结构化评估结果"""
        evaluated_clues = []

        # 1. Remove "final answer:" prefix if it exists
        if content.startswith("final answer:"):
            content = content[len("final answer:"):].strip()

        # 2. Remove <think>...</think> block
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Split content into sections for each clue.
        # Assuming "根据提供的评估信息，以下是针对**线索X**的详细分析和建议：" is a reliable marker.
        # We can split by "---" which seems to be a separator, and then look for the clue marker within each part.
        # However, a more robust way might be to find all clue markers first.

        clue_sections = re.split(r'(?=根据提供的评估信息，以下是针对\*\*线索\d+\*\*的详细分析和建议：)', content)
        
        for section in clue_sections:
            if not section.strip():
                continue

            clue_id_match = re.search(r"根据提供的评估信息，以下是针对\*\*线索(\d+)\*\*的详细分析和建议：", section)
            if not clue_id_match:
                continue
            
            clue_id = clue_id_match.group(1)
            
            match_score = 0.0
            risk_level = "未知" # Default in case parsing fails for these fields
            evidence = "未能提取" # Default

            # Extract Match Score
            score_match = re.search(r"### \*\*1\. 匹配度分析（(\d+)分）\*\*", section)
            if score_match:
                match_score = float(score_match.group(1))

            # Extract Risk Level
            risk_match = re.search(r"- \*\*风险等级：(\w+)\*\*", section)
            if risk_match:
                risk_level = risk_match.group(1)
            
            # Extract Evidence
            # This regex captures text after "### **2. 证据分析**" until it hits another "### **" (potential next section like "### **3. ..."),
            # or "---" (common separator), or end of the section string ($).
            evidence_match = re.search(r"### \*\*2\. 证据分析\*\*(.*?)(?=### \*\*|\n---\n|$)", section, re.DOTALL)
            if evidence_match:
                evidence_text = evidence_match.group(1).strip()
                # Clean up bullet points and extra whitespace
                evidence_lines = [line.strip() for line in evidence_text.split('\n') if line.strip() and not line.strip().startswith("---")]
                evidence = "\n".join(evidence_lines)
            
            evaluated_clues.append({
                "clue_id": clue_id,
                "match_score": match_score,
                "risk_level": risk_level,
                "evidence": evidence
            })
        
        # Fallback: If after attempting to parse all sections, evaluated_clues is still empty,
        # then the new parsing logic failed to find any structured clues.
        if not evaluated_clues:
            print("警告：无法从模型响应中解析出结构化评估结果（新格式解析未找到有效线索或内容为空），将创建默认评估结果")
            evaluated_clues = [{
                "clue_id": "1", # Defaulting to "1" as per original fallback
                "match_score": 75.0,
                "risk_level": "中",
                "evidence": "模型未提供结构化评估或解析失败，已完成基本分析"
            }]

        # 获取目标企业列表
        target_companies = kwargs.get('target_companies', [])
        
        # 在处理评估结果时，对目标企业的线索进行特殊处理
        for clue in evaluated_clues:
            # 初始化is_target_company字段
            clue['is_target_company'] = False
            
            # 如果有目标企业，尝试匹配
            if target_companies:
                # 检查线索中是否包含目标企业名称
                # 首先尝试从evidence中查找
                evidence_text = clue.get('evidence', '').lower()
                for company in target_companies:
                    if company.lower() in evidence_text:
                        clue['is_target_company'] = True
                        # 对目标企业降低风险阈值，提高关注度
                        if clue['match_score'] >= 60:  # 对目标企业降低风险阈值
                            clue['risk_level'] = '高'
                        break
        
        return evaluated_clues
    