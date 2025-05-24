from openai import OpenAI
import markdown
# from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL # 不再直接使用这些
from config.settings import MODEL_CONFIG # 导入新的模型配置
from agents.model_adapter import get_model_adapter # 导入适配器工厂函数
import json # 确保导入json

class SummaryAgent:
    def __init__(self):
        # self.client = OpenAI(
        #     api_key=OPENAI_API_KEY,
        #     base_url=OPENAI_BASE_URL
        # )
        self.model_adapter = get_model_adapter(MODEL_CONFIG)

    def get_response(self, messages, **kwargs):
        # try:
        #     completion = self.client.chat.completions.create(
        #         model="deepseek-chat", # 这个模型名也应该来自配置
        #         messages=messages,
        #         **kwargs
        #     )
        #     return completion
        # except Exception as e:
        #     print(f"API调用失败: {str(e)}")
        #     return None
        return self.model_adapter.get_response(messages, model=MODEL_CONFIG.get("model_name"), **kwargs)

    def generate_summary(self, research_materials, summary_prompt):
        # 新增评估结果上下文，包含目标企业标记
        evaluation_context = "\n".join([
            f"### 线索{i + 1}评估结果\n"
            f"- 匹配度：{clue['match_score']}分\n"
            f"- 风险等级：{clue['risk_level']}\n"
            f"- 证据：{clue['evidence']}"
            + (f"\n- 目标企业：是" if clue.get('is_target_company', False) else "")
            for i, clue in enumerate(research_materials.get('evaluated_clues', []))
        ])

        research_context = f"""原始专利内容：
{research_materials['original_text']}

评估后侵权线索：
{evaluation_context}

搜索结果：
{json.dumps(research_materials['search_results'], indent=2, ensure_ascii=False)}"""

        messages = [
            {"role": "system", "content": summary_prompt},
            {"role": "user", "content": research_context}
        ]

        response = self.get_response(messages)
        if not response:
            return "总结失败"

        final_answer = f"## 分析结果\n{response.choices[0].message.content}\n\n"
        print("final answer:", final_answer)
        return markdown.markdown(final_answer)
    