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

    def _summarize_search_results(self, search_results):
        summary_lines = []
        for i, result_item in enumerate(search_results):
            query = result_item.get('query', '未知查询')
            result_text = result_item.get('result', '无结果')

            summary_lines.append(f"### 搜索查询 {i+1}: {query}")

            # 简单提取前几行作为摘要，这里假设每行是一个片段
            snippets = result_text.split('\n')
            max_snippets_per_query = 3 # 最多显示3个片段
            valid_snippets_found = 0

            # Iterate through all lines to find snippets, but only take the first max_snippets_per_query valid ones
            processed_snippets_count = 0
            for snippet_text in snippets:
                if processed_snippets_count >= max_snippets_per_query:
                    break # Stop if we have already found enough valid snippets
                if snippet_text.strip(): # 确保片段不是空的
                    valid_snippets_found += 1
                    summary_lines.append(f"- 片段 {valid_snippets_found}: {snippet_text.strip()}")
                    processed_snippets_count += 1

            if valid_snippets_found == 0:
                summary_lines.append("- 无有效片段")

            summary_lines.append("") # 添加空行分隔不同查询的结果

        # Remove the last empty line if summary_lines is not empty, to prevent multiple trailing newlines
        if summary_lines and summary_lines[-1] == "":
            summary_lines.pop()

        return "\n".join(summary_lines)

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

        original_text = research_materials['original_text']
        max_len = 20000
        if len(original_text) > max_len:
            original_text = original_text[:max_len] + "\n... (truncated due to length)"

        research_context = f"""原始专利内容：
{original_text}

评估后侵权线索：
{evaluation_context}

搜索结果摘要：
{self._summarize_search_results(research_materials['search_results'])}"""

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
    