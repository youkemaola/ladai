import gradio as gr

def greet(name):
    return "你好, " + name + "! 你的应用在ModelScope上运行成功了！"

iface = gr.Interface(fn=greet, inputs="text", outputs="text", title="部署测试")
iface.launch()
