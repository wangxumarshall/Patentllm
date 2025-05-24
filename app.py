from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import random
import requests
from agents.patent_analyzer import PatentAnalyzer
from config.settings import UPLOAD_FOLDER, MAX_CONTENT_LENGTH, SECRET_KEY
from prompts.prompt_templates import get_customized_prompt
import traceback # 导入 traceback 模块

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 不再需要读取提示词文件
# with open('prompts/research_prompt.txt', 'r', encoding='utf-8') as f:
#     research_prompt = f.read()
# 
# with open('prompts/summary_prompt.txt', 'r', encoding='utf-8') as f:
#     summary_prompt = f.read()


@app.route('/')
def home():
    return redirect(url_for('upload'))


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # 保存用户输入的分析参数到会话
        session['analysis_params'] = {
            'company_name': request.form.get('company_name', '国际知名ICT企业'),
            'target_companies': request.form.get('target_companies', ''),
            'exclude_companies': request.form.get('exclude_companies', ''),
            'focus_area': request.form.get('focus_area', '')
        }
        
        # 处理文件上传或URL输入
        if 'file' in request.files and request.files['file'].filename:
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
    
    # 获取分析参数
    analysis_params = session.get('analysis_params', {})
    company_name = analysis_params.get('company_name', '国际知名ICT企业')
    
    # 处理目标企业和排除企业列表
    target_companies = analysis_params.get('target_companies', '')
    if target_companies:
        target_companies = [company.strip() for company in target_companies.split(',')]
    
    exclude_companies = analysis_params.get('exclude_companies', '')
    if exclude_companies:
        exclude_companies = [company.strip() for company in exclude_companies.split(',')]
    
    focus_area = analysis_params.get('focus_area', '')

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

        # 获取自定义的 prompt
        research_prompt = get_customized_prompt(
            'research', 
            company_name=company_name,
            target_companies=target_companies,
            exclude_companies=exclude_companies,
            focus_area=focus_area
        )
        
        summary_prompt = get_customized_prompt(
            'summary', 
            company_name=company_name,
            target_companies=target_companies
        )

        analyzer = PatentAnalyzer()
        # 传递分析参数到分析器
        result = analyzer.analyze_patent(
            patent_text, 
            research_prompt, 
            summary_prompt,
            company_name=company_name,
            target_companies=target_companies
        )
        
        session['analysis_result'] = result
        return jsonify(result=result)

    except Exception as e:
        print(f"分析过程中出错: {str(e)}")
        traceback.print_exc()  # 打印完整的堆栈跟踪到终端
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
    