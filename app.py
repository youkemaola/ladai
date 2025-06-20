import gradio as gr
import numpy as np
import plotly.graph_objects as go
import asyncio

# --- 1. 定义考试参数 (和原来一样) ---
EXAM_CONFIG = {
    '事业单位': {
        'written_max': 300,
        'written_mu': 160.0,
        'written_sigma': 25.80,
        'interview_mu': 74.0,
        'interview_sigma': 4.86,
        'score_formula': lambda w, i: w / 3.0 + i
    },
    '公务员': {
        'written_max': 200,
        'written_mu': 134.0,
        'written_sigma': 6.47,
        'interview_mu': 74.0,
        'interview_sigma': 4.78,
        'score_formula': lambda w, i: w / 2.0 + i
    }
}
NUM_SIMULATIONS = 10000

# --- 2. 核心模拟函数 ---
# Gradio将调用这个函数来更新UI
async def run_simulation(exam_type, total_participants, promotion_slots, written_cutoff, user_written, user_interview, *opponents_scores):
    """
    接收所有UI输入作为参数，并返回所有UI输出。
    *opponents_scores 会接收所有对手的笔试和面试分数。
    """
    config = EXAM_CONFIG[exam_type]
    
    # --- 数据处理和验证 ---
    total_participants = int(total_participants)
    promotion_slots = int(promotion_slots)
    
    if not (2 <= total_participants <= 9 and 1 <= promotion_slots < total_participants):
        # 在Gradio中，我们可以通过返回错误信息来提示用户
        raise gr.Error("输入无效！请检查总人数(2-9)和晋级人数(需小于总人数)。")

    opponent_known_scores = []
    # opponents_scores 是一个扁平的元组 (opp1_w, opp1_i, opp2_w, opp2_i, ...)
    # 我们需要将它重新组织
    for i in range(0, (total_participants - 1) * 2, 2):
        written = opponents_scores[i] if opponents_scores[i] > 0 else None
        interview = opponents_scores[i+1] if opponents_scores[i+1] > 0 else None
        opponent_known_scores.append({'written': written, 'interview': interview})

    # --- 模拟逻辑 (与原版基本一致) ---
    promotion_count = 0
    user_total_score = config['score_formula'](user_written, user_interview)
    
    num_unknown_written = sum(1 for o in opponent_known_scores if o['written'] is None)
    num_unknown_interview = sum(1 for o in opponent_known_scores if o['interview'] is None)
    
    # 预生成随机数池
    sim_written_pool, sim_interview_pool = [], []
    if num_unknown_written > 0:
        while len(sim_written_pool) < num_unknown_written * NUM_SIMULATIONS:
            s = np.random.normal(config['written_mu'], config['written_sigma'], 2000)
            sim_written_pool.extend(s[(s > written_cutoff) & (s < config['written_max'])])
    if num_unknown_interview > 0:
        while len(sim_interview_pool) < num_unknown_interview * NUM_SIMULATIONS:
            s = np.random.normal(config['interview_mu'], config['interview_sigma'], 2000)
            sim_interview_pool.extend(s[(s >= 60) & (s <= 100)])
    
    written_pool_idx, interview_pool_idx = 0, 0
    last_run_details = {}

    for i in range(NUM_SIMULATIONS):
        if i % 1000 == 0: await asyncio.sleep(0) # 允许UI刷新

        all_scores = []
        current_run_details = {'user': {'written': user_written, 'interview': user_interview, 'total': user_total_score}}
        
        for j in range(total_participants - 1):
            sim_written = opponent_known_scores[j]['written'] or sim_written_pool[written_pool_idx]; written_pool_idx += (sim_written is None)
            sim_interview = opponent_known_scores[j]['interview'] or sim_interview_pool[interview_pool_idx]; interview_pool_idx += (sim_interview is None)
            all_scores.append(config['score_formula'](sim_written, sim_interview))
            if i == NUM_SIMULATIONS - 1:
                current_run_details[f'opponent_{j+1}'] = {'written': sim_written, 'interview': sim_interview, 'total': config['score_formula'](sim_written, sim_interview)}
        
        all_scores.append(user_total_score)
        all_scores.sort(reverse=True)
        if len([s for s in all_scores if s > user_total_score]) < promotion_slots:
            promotion_count += 1
    
    last_run_details = current_run_details

    # --- 准备返回给Gradio的输出 ---
    probability = promotion_count / NUM_SIMULATIONS
    
    # 1. 更新图表
    fig = go.Figure(data=[go.Bar(y=[probability], x=['晋级概率'], text=[f'{probability:.2%}'], textposition='auto')])
    fig.update_layout(yaxis_range=[0,1], yaxis_tickformat=".0%", title_text="晋级概率", title_x=0.5)
    
    # 2. 更新表情
    if probability > 0.5: face = '😂'
    elif probability > 0.1: face = '🙂'
    else: face = '😭'

    # 3. 更新统计文本
    promo_text = f"在 {NUM_SIMULATIONS} 次模拟中，你成功晋级了 {promotion_count} 次。"

    # 4. 生成HTML结果表格
    sorted_results = sorted(last_run_details.items(), key=lambda item: item[1]['total'], reverse=True)
    user_rank = next((i for i, (name, _) in enumerate(sorted_results, 1) if name == 'user'), -1)
    promotion_status = "成功晋级！" if 1 <= user_rank <= promotion_slots else "未能晋级。"
    
    table_html = f"""
    <div style="text-align:center; font-size:1.2em; margin-bottom:10px;">你在该轮模拟中排名第 {user_rank}，<b>{promotion_status}</b></div>
    <table style="width:95%; margin:auto; border-collapse:collapse; font-size:14px;">
        <tr style="background-color:#f2f2f2;">
            <th style="border:1px solid #ddd; padding:8px;">排名</th><th style="border:1px solid #ddd; padding:8px;">角色</th>
            <th style="border:1px solid #ddd; padding:8px;">笔试</th><th style="border:1px solid #ddd; padding:8px;">面试</th>
            <th style="border:1px solid #ddd; padding:8px;">总分</th>
        </tr>
    """
    for i, (name, scores) in enumerate(sorted_results, 1):
        is_user = (name == 'user')
        row_style = "background-color:#d4edda; font-weight:bold;" if is_user else ""
        role_name = "<b>你</b>" if is_user else name.replace("opponent_", "对手")
        table_html += f"""
        <tr style="{row_style}">
            <td style="border:1px solid #ddd; padding:8px;">{i}</td><td style="border:1px solid #ddd; padding:8px;">{role_name}</td>
            <td style="border:1px solid #ddd; padding:8px;">{scores['written']:.2f}</td><td style="border:1px solid #ddd; padding:8px;">{scores['interview']:.2f}</td>
            <td style="border:1px solid #ddd; padding:8px;"><b>{scores['total']:.2f}</b></td>
        </tr>
        """
    table_html += "</table>"
    
    # 按顺序返回所有输出
    return fig, face, promo_text, table_html

# --- 3. 使用Gradio搭建UI界面 ---
with gr.Blocks(theme=gr.themes.Soft(), title="考试晋级率模拟器") as demo:
    gr.Markdown("# 交互式考试晋级率模拟器")
    gr.Markdown("调整下方参数，实时模拟您在考试中的晋级概率。")
    
    # 收集所有输入的列表，方便后续处理
    inputs = []
    
    with gr.Row():
        exam_type = gr.Dropdown(list(EXAM_CONFIG.keys()), value="事业单位", label="选择考试类型")
        total_participants = gr.Number(value=3, label="总参与人数", minimum=2, maximum=9, step=1)
        promotion_slots = gr.Number(value=1, label="允许晋级人数", minimum=1, maximum=8, step=1)
        written_cutoff = gr.Number(value=150, label="笔试入围分数")
    inputs.extend([exam_type, total_participants, promotion_slots, written_cutoff])

    with gr.Row():
        user_written = gr.Slider(label="你的笔试成绩", minimum=0, maximum=300, value=160, step=0.5)
        user_interview = gr.Slider(label="你的面试成绩", minimum=0, maximum=100, value=75, step=0.5)
    inputs.extend([user_written, user_interview])

    # 动态更新滑块的最大值
    def update_slider_max(exam_choice):
        max_val = EXAM_CONFIG[exam_choice]['written_max']
        return gr.Slider(maximum=max_val, value=max_val*0.5) # 返回一个新的滑块实例来更新
    exam_type.change(fn=update_slider_max, inputs=exam_type, outputs=user_written)

    gr.Markdown("--- \n ### 对手成绩（选填）")
    
    # 创建最大数量的对手输入行，并默认隐藏
    opponent_inputs = []
    with gr.Blocks() as opponent_rows:
        for i in range(8): # 最多8个对手
            with gr.Row(visible=False) as row:
                w = gr.Number(label=f"对手{i+1}笔试", value=0)
                iv = gr.Number(label=f"对手{i+1}面试", value=0)
                opponent_inputs.extend([w, iv])
    
    all_inputs = inputs + opponent_inputs

    # 根据总人数，动态显示/隐藏对手输入行
    def update_opponent_visibility(num_total):
        num_opponents = int(num_total) - 1
        updates = []
        for i in range(8):
            updates.append(gr.Row(visible=(i < num_opponents)))
        return updates
    
    total_participants.change(fn=update_opponent_visibility, inputs=total_participants, outputs=opponent_rows.children)

    # 定义输出区域
    with gr.Row():
        face_output = gr.Textbox(label="模拟心情", interactive=False, text_align="center", scale=1)
        plot_output = gr.Plot(label="概率图", scale=2)
    
    promo_text_output = gr.Textbox(label="模拟统计", interactive=False)
    html_output = gr.HTML()

    outputs = [plot_output, face_output, promo_text_output, html_output]

    # 将所有输入和输出绑定到模拟函数
    for component in all_inputs:
        component.change(fn=run_simulation, inputs=all_inputs, outputs=outputs)
    
    # 页面加载时运行一次
    demo.load(fn=run_simulation, inputs=all_inputs, outputs=outputs)

# --- 4. 启动应用 ---
if __name__ == "__main__":
    demo.launch()
