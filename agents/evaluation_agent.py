import yaml
from openai import OpenAI
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
import re
from prompts.prompt_templates import get_customized_prompt


class EvaluationAgent:
    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )
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

    def conduct_evaluation(self, research_materials, evaluation_prompt=None):
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
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.3  # 降低创造性，确保严谨性
            )
            assistant_msg = response.choices[0].message

            # 提取评估结果或追问问题
            if "请提供" in assistant_msg.content:
                # 触发追问，要求用户补充信息（实际场景中可对接企业知识库）
                messages.append(assistant_msg)
                # 模拟用户回复（实际需对接前端交互）
                user_reply = "线索A的公开日为2024-05-15，实施地在中国广东"
                messages.append({"role": "user", "content": user_reply})
            else:
                # 解析评估报告
                evaluated_clues = self.parse_evaluation_result(assistant_msg.content)
                return evaluated_clues  # 评估完成

        return None  # 超过最大轮次

    def parse_evaluation_result(self, content):
        """解析模型返回的结构化评估结果"""
        pattern = r"线索(\d+):\n+匹配度得分：(\d+\.\d+)分\n+法律风险等级：(\w+)\n+证据链完整性：(.*?)\n+"
        results = re.findall(pattern, content, re.DOTALL)
        return [{
            "clue_id": idx,
            "match_score": float(score),
            "risk_level": level,
            "evidence": evidence.strip()
        } for idx, score, level, evidence in results]
    