from agents.research_agent import ResearchAgent
from agents.summary_agent import SummaryAgent
from agents.evaluation_agent import EvaluationAgent
from prompts.prompt_templates import get_customized_prompt


class PatentAnalyzer:
    def __init__(self):
        self.research_agent = ResearchAgent()
        self.summary_agent = SummaryAgent()
        self.evaluation_agent = EvaluationAgent()

    def extract_text(self, file_input):
        return self.research_agent.extract_text(file_input)

    def analyze_patent(self, patent_text, research_prompt, summary_prompt, **kwargs):
        # 第一阶段：研究代理收集信息
        research_materials = self.research_agent.conduct_research(patent_text, research_prompt)
        if not research_materials:
            return "分析失败"

        # 获取评估阶段的自定义 prompt
        patent_info = self.extract_patent_info(research_materials)
        evaluation_prompt = get_customized_prompt(
            'evaluation', 
            company_name=kwargs.get('company_name', '全球知名ICT公司'),
            patent_info=patent_info,
            target_companies=kwargs.get('target_companies', [])
        )
        
        # 第二阶段：评估代理验证侵权线索
        evaluated_clues = self.evaluation_agent.conduct_evaluation(
            research_materials, 
            evaluation_prompt,
            target_companies=kwargs.get('target_companies', [])
        )
        
        if not evaluated_clues:
            return "评估失败，线索信息不完整"

        # 过滤无效线索（保留高风险线索）
        high_risk_clues = [clue for clue in evaluated_clues if clue["match_score"] >= 70]
        research_materials['evaluated_clues'] = high_risk_clues  # 注入评估结果

        # 第三阶段：总结代理生成报告
        return self.summary_agent.generate_summary(research_materials, summary_prompt)
    
    def extract_patent_info(self, research_materials):
        """从研究材料中提取专利信息，用于定制评估 prompt"""
        patent_text = research_materials.get('original_text', '')
        
        # 提取可能的专利号和日期
        import re
        patent_number = re.search(r'专利号[：:]\s*([A-Z0-9]+)', patent_text)
        filing_date = re.search(r'申请日[：:]\s*(\d{4}-\d{2}-\d{2})', patent_text)
        
        return {
            'patent_number': patent_number.group(1) if patent_number else None,
            'filing_date': filing_date.group(1) if filing_date else None,
        }
    