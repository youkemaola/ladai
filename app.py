import gradio as gr
import numpy as np
import plotly.graph_objects as go
import asyncio

# ==============================================================================
# 1. 美化CSS
# [修改1] 将背景图的URL修改为本地文件路径
# ==============================================================================
glassmorphism_css = """
/* 将背景图应用到Gradio应用的根元素上 */
gradio-app {
    /* 这里是唯一的CSS改动：将url()中的地址改为本地相对路径 */
    background-image: url('/file=static/background.jpg') !important;
    background-size: cover !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-attachment: fixed !important;
}

/* ------------------ 以下所有CSS规则保持不变 ------------------ */
.gradio-container {
    background: none !important;
}

.gradio-container .gr-panel, 
.gradio-container .gr-button, 
.gradio-container .gr-box,
.gradio-container .gr-input,
.gradio-container .gr-plot {
    background: rgba(255, 255, 255, 0.1) !important; 
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border-radius: 15px !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1) !important;
}

.gradio-container .gr-input-wrap input, 
.gradio-container .gr-input-wrap textarea,
.gradio-container .gr-slider-input input {
    background: transparent !important;
    color: #FFFFFF !important;
    border: none !important;
    box-shadow: none !important;
}

.gradio-container .gr-button {
    color: #FFFFFF !important;
    font-weight: bold;
}

.gradio-container .gr-label, 
.gradio-container .gr-info,
.gradio-container .markdown h1, 
.gradio-container .markdown h2, 
.gradio-container .markdown p {
    color: #FFFFFF !important;
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.6);
}

.gradio-container .gr-plot .plotly {
    background-color: transparent !important;
}
.gradio-container .gr-plot .plotly .xtick text,
.gradio-container .gr-plot .plotly .ytick text {
    fill: #FFFFFF !important;
    text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.7);
}
"""

# --- 参数和模拟逻辑部分（完全未作改动）---
EXAM_CONFIG = {
    '事业单位': {
        'written_max': 300, 'written_mu': 160.0, 'written_sigma': 25.80,
        'interview_mu': 74.0, 'interview_sigma': 4.86,
        'score_formula': lambda w, i: w / 3.0 + i
    },
    '公务员': {
        'written_max': 200, 'written_mu': 134.0, 'written_sigma': 6.47,
        'interview_mu': 74.0, 'interview_sigma': 4.78,
        'score_formula': lambda w, i: w / 2.0 + i
    }
}
NUM_SIMULATIONS = 10000

async def run_simulation(exam_type, total_participants, promotion_slots, written_cutoff, user_written, user_interview, *opponents_scores):
    config = EXAM_CONFIG[exam_type]
    total_participants = int(total_participants) if total_participants else 3
    promotion_slots = int(promotion_slots) if promotion_slots else 1
    if not (2 <= total_participants <= 9 and 1 <= promotion_slots < total_participants):
        raise gr.Error("输入无效！请检查总人数(2-9)和晋级人数(需小于总人数)。")
    opponent_known_scores = []
    for i in range(0, (total_participants - 1) * 2, 2):
        written_score = opponents_scores[i] if opponents_scores[i] and opponents_scores[i] > 0 else None
        interview_score = opponents_scores[i+1] if opponents_scores[i+1] and opponents_scores[i+1] > 0 else None
        opponent_known_scores.append({'written': written_score, 'interview': interview_score})
    highlight_opp1 = False
    if total_participants > 1 and user_written != written_cutoff:
        opponent_known_scores[0]['written'] = written_cutoff
        highlight_opp1 = True
    promotion_count = 0
    user_total_score = config['score_formula'](user_written, user_interview)
    num_unknown_written = sum(1 for o in opponent_known_scores if o['written'] is None)
    num_unknown_interview = sum(1 for o in opponent_known_scores if o['interview'] is None)
    sim_written_pool, sim_interview_pool = [], []
    if num_unknown_written > 0:
        pool_size = num_unknown_written * NUM_SIMULATIONS
        written_samples = []
        while len(written_samples) < pool_size:
            s = np.random.normal(config['written_mu'], config['written_sigma'], int(pool_size * 1.5))
            written_samples.extend(s[(s > written_cutoff) & (s < config['written_max'])])
        sim_written_pool = written_samples[:pool_size]
    if num_unknown_interview > 0:
        pool_size = num_unknown_interview * NUM_SIMULATIONS
        interview_samples = []
        while len(interview_samples) < pool_size:
            s = np.random.normal(config['interview_mu'], config['interview_sigma'], int(pool_size * 1.5))
            interview_samples.extend(s[(s >= 60) & (s <= 100)])
        sim_interview_pool = interview_samples[:pool_size]
    written_pool_idx, interview_pool_idx = 0, 0
    last_run_details = {}
    for i in range(NUM_SIMULATIONS):
        if i % 1000 == 0: await asyncio.sleep(0)
        all_scores = []
        is_last_run = (i == NUM_SIMULATIONS - 1)
        if is_last_run:
            current_run_details = {'user': {'written': user_written, 'interview': user_interview, 'total': user_total_score}}
        for j in range(total_participants - 1):
            sim_written = opponent_known_scores[j]['written']
            if sim_written is None:
                sim_written = sim_written_pool[written_pool_idx]
                written_pool_idx += 1
            sim_interview = opponent_known_scores[j]['interview']
            if sim_interview is None:
                sim_interview = sim_interview_pool[interview_pool_idx]
                interview_pool_idx += 1
            opponent_total_score = config['score_formula'](sim_written, sim_interview)
            all_scores.append(opponent_total_score)
            if is_last_run:
                current_run_details[f'opponent_{j+1}'] = {'written': sim_written, 'interview': sim_interview, 'total': opponent_total_score}
        all_scores.append(user_total_score)
        all_scores.sort(reverse=True)
        if len([s for s in all_scores if s > user_total_score]) < promotion_slots:
            promotion_count += 1
    if 'current_run_details' in locals() and last_run_details == {}:
        last_run_details = current_run_details
    probability = promotion_count / NUM_SIMULATIONS
    fig = go.Figure(data=[go.Bar(y=[probability], x=['上岸概率'], text=[f'{probability:.2%}'], textposition='auto', marker_color='rgba(55, 126, 229, 0.7)')])
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', yaxis_range=[0,1], yaxis_tickformat=".0%", title_text="上岸概率", title_x=0.5, font_color="white", title_font_color="white", yaxis=dict(gridcolor='rgba(255, 255, 255, 0.2)'), modebar_remove=['toimage', 'zoom', 'pan', 'select', 'lasso2d', 'autoscale'])
    if probability > 0.5: face = '😂'
    elif probability > 0.1: face = '🙂'
    else: face = '😭'
    promo_text = f"在 {NUM_SIMULATIONS} 次模拟中，你成功上岸了 {promotion_count} 次。"
    table_html = ""
    if last_run_details:
        sorted_results = sorted(last_run_details.items(), key=lambda item: item[1]['total'], reverse=True)
        user_rank = next((i for i, (name, _) in enumerate(sorted_results, 1) if name == 'user'), -1)
        promotion_status = "成功上岸！" if 1 <= user_rank <= promotion_slots else "未能上岸。"
        table_html = f"""<div style="color:white; text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.6); text-align:center; font-size:1.2em; margin-bottom:10px;">你在该轮模拟中排名第 {user_rank}，<b>{promotion_status}</b></div><table style="width:95%; margin:auto; border-collapse:collapse; font-size:14px; color:white; text-shadow: 1px 1px 2px rgba(0,0,0,0.5);"><tr style="background-color:rgba(255, 255, 255, 0.25);"><th style="border:1px solid rgba(255,255,255,0.3); padding:8px;">排名</th><th style="border:1px solid rgba(255,255,255,0.3); padding:8px;">角色</th><th style="border:1px solid rgba(255,255,255,0.3); padding:8px;">笔试</th><th style="border:1px solid rgba(255,255,255,0.3); padding:8px;">面试</th><th style="border:1px solid rgba(255,255,255,0.3); padding:8px;">总分</th></tr>"""
        for i, (name, scores) in enumerate(sorted_results, 1):
            row_style = "background-color:rgba(212, 237, 218, 0.3); font-weight:bold;" if name == 'user' else ""
            role_name = "<b>你</b>" if name == 'user' else name.replace("opponent_", "对手")
            written_score_cell = f"<td style='border:1px solid rgba(255,255,255,0.3); padding:8px;'>{scores['written']:.2f}</td>"
            if highlight_opp1 and name == "opponent_1":
                written_score_cell = f"<td style='border:1px solid rgba(255,255,255,0.3); padding:8px; background-color:rgba(255, 248, 196, 0.4); color:black; text-shadow:none;'>{scores['written']:.2f} (进面分)</td>"
            table_html += f"""<tr style="{row_style}"><td style="border:1px solid rgba(255,255,255,0.3); padding:8px;">{i}</td><td style="border:1px solid rgba(255,255,255,0.3); padding:8px;">{role_name}</td>{written_score_cell}<td style="border:1px solid rgba(255,255,255,0.3); padding:8px;">{scores['interview']:.2f}</td><td style="border:1px solid rgba(255,255,255,0.3); padding:8px;"><b>{scores['total']:.2f}</b></td></tr>"""
        table_html += "</table>"
    return fig, gr.update(value=face), gr.update(value=promo_text), gr.update(value=table_html)

# --- UI界面构建部分（完全未作改动）---
# [修改2] 在 gr.Blocks 中添加 allowed_paths 参数
with gr.Blocks(title="考试上岸率模拟", css=glassmorphism_css, allowed_paths=["static"]) as demo:
    gr.Markdown("# 考试上岸率模拟")
    gr.Markdown("调整下方参数，实时模拟您在考试中的上岸概率。")
    inputs_list = []
    with gr.Row():
        exam_type_dd = gr.Dropdown(list(EXAM_CONFIG.keys()), value="事业单位", label="选择考试类型")
        total_participants_num = gr.Number(value=3, label="总参与人数", minimum=2, maximum=9, step=1)
        promotion_slots_num = gr.Number(value=1, label="允许上岸人数", minimum=1, maximum=8, step=1)
        written_cutoff_num = gr.Number(value=150, label="笔试进面分数")
    inputs_list.extend([exam_type_dd, total_participants_num, promotion_slots_num, written_cutoff_num])
    with gr.Row():
        user_written_slider = gr.Slider(label="你的笔试成绩", minimum=0, maximum=300, value=160, step=0.5)
        user_interview_slider = gr.Slider(label="你的面试成绩", minimum=0, maximum=100, value=75, step=0.5)
    inputs_list.extend([user_written_slider, user_interview_slider])
    def update_slider_max_val(exam_choice):
        max_val = EXAM_CONFIG[exam_choice]['written_max']
        return gr.update(maximum=max_val, value=round(max_val * 0.5))
    exam_type_dd.change(fn=update_slider_max_val, inputs=exam_type_dd, outputs=user_written_slider)
    with gr.Row():
        with gr.Column(scale=4):
            gr.Markdown("--- \n ### 对手成绩（选填）")
        with gr.Column(scale=1, min_width=50):
            clear_btn = gr.Button("清空对手成绩")
    gr.Markdown("<p style='color:lightgray; font-size:0.9em; text-shadow: 1px 1px 2px rgba(0,0,0,0.7);'>提示：对手成绩留空，则该项成绩将在模拟中随机生成。</p>")
    opponent_inputs_list = []
    opponent_blocks_list = []
    with gr.Row():
        for i in range(4):
            with gr.Column(visible=(i<2), min_width=160) as col:
                w = gr.Number(label=f"对手{i+1}笔试", value=None, minimum=0, maximum=300)
                iv = gr.Number(label=f"对手{i+1}面试", value=None, minimum=0, maximum=100)
                opponent_inputs_list.extend([w, iv])
                opponent_blocks_list.append(col)
    with gr.Row():
        for i in range(4, 8):
            with gr.Column(visible=False, min_width=160) as col:
                w = gr.Number(label=f"对手{i+1}笔试", value=None, minimum=0, maximum=300)
                iv = gr.Number(label=f"对手{i+1}面试", value=None, minimum=0, maximum=100)
                opponent_inputs_list.extend([w, iv])
                opponent_blocks_list.append(col)
    all_inputs_list = inputs_list + opponent_inputs_list
    def clear_opponent_scores():
        return [None] * 16
    clear_btn.click(fn=clear_opponent_scores, inputs=None, outputs=opponent_inputs_list)
    def update_opponent_visibility_ui(num_total):
        num_opponents = int(num_total) - 1 if num_total else 2
        return [gr.update(visible=(i < num_opponents)) for i in range(8)]
    total_participants_num.change(fn=update_opponent_visibility_ui, inputs=total_participants_num, outputs=opponent_blocks_list)
    with gr.Row():
        face_output_tb = gr.Textbox(label="模拟心情", interactive=False, text_align="center", scale=1)
        plot_output_pl = gr.Plot(label="上岸概率图", scale=3)
    promo_text_output_tb = gr.Textbox(label="模拟统计", interactive=False)
    html_output_html = gr.HTML()
    outputs_list = [plot_output_pl, face_output_tb, promo_text_output_tb, html_output_html]
    all_triggers = inputs_list + opponent_inputs_list
    for component in all_triggers:
        component.change(fn=run_simulation, inputs=all_inputs_list, outputs=outputs_list, show_progress="full")
    demo.load(fn=run_simulation, inputs=all_inputs_list, outputs=outputs_list, show_progress="full")

if __name__ == "__main__":
    demo.launch()
