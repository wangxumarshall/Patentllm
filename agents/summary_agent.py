from openai import OpenAI
import markdown
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL


class SummaryAgent:
    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )

    def get_response(self, messages):
        try:
            completion = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages
            )
            return completion
        except Exception as e:
            print(f"API调用失败: {str(e)}")
            return None

    def generate_summary(self, research_materials, summary_prompt):
        # 新增评估结果上下文
        evaluation_context = "\n".join([
            f"### 线索{i + 1}评估结果\n"
            f"- 匹配度：{clue['match_score']}分\n"
            f"- 风险等级：{clue['risk_level']}\n"
            f"- 证据：{clue['evidence']}"
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
    