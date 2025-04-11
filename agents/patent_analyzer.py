from agents.research_agent import ResearchAgent
from agents.summary_agent import SummaryAgent
from agents.evaluation_agent import EvaluationAgent
from prompts.prompt_templates import EVALUATION_PROMPT


class PatentAnalyzer:
    def __init__(self):
        self.research_agent = ResearchAgent()
        self.summary_agent = SummaryAgent()
        self.evaluation_agent = EvaluationAgent()

    def extract_text(self, file_input):
        return self.research_agent.extract_text(file_input)

    def analyze_patent(self, patent_text, research_prompt, summary_prompt):
        # 第一阶段：研究代理收集信息
        research_materials = self.research_agent.conduct_research(patent_text, research_prompt)
        if not research_materials:
            return "分析失败"

        # 第二阶段：评估代理验证侵权线索
        evaluated_clues = self.evaluation_agent.conduct_evaluation(research_materials)
        if not evaluated_clues:
            return "评估失败，线索信息不完整"

        # 过滤无效线索（保留高风险线索）
        high_risk_clues = [clue for clue in evaluated_clues if clue["match_score"] >= 70]
        research_materials['evaluated_clues'] = high_risk_clues  # 注入评估结果

        # 第三阶段：总结代理生成报告
        return self.summary_agent.generate_summary(research_materials, summary_prompt)
    