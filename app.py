"""Streamlit部署入口。保留HTML/JavaScript计算器的界面与浏览器端计算。"""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="思福妥多层次保障支付模拟计算器",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """<style>
    .block-container {padding-top: 1.2rem; padding-bottom: 1rem; max-width: 1320px;}
    [data-testid="stAppViewContainer"] {background: #eef5f9;}
    </style>""",
    unsafe_allow_html=True,
)

page_file = Path(__file__).resolve().parent / "calculator.html"
if not page_file.is_file():
    st.error("缺少 calculator.html。请把它与 app.py、requirements.txt 上传到同一个目录。")
    st.stop()

page_html = page_file.read_text(encoding="utf-8")
# iframe内运行现有JS，保留实时计算、JSON导入导出、CSV及打印。
# scrolling=True避免手机端或长参数表被裁切。
components.html(page_html, height=1800, scrolling=True)

with st.expander("运行与数据说明"):
    st.write("本版由Streamlit展示，计算与表单交互在浏览器内执行。")
    st.write("当前价格、比例和限额均为演示假设；请在政策与参数中填写并核验。")
    st.write("修改后请下载配置JSON保存。刷新页面或重启应用后需重新载入。")
    st.write("嵌入窗口可滚动；如浏览器限制窗口内打印或下载，可使用下方独立网页版。")
    st.download_button(
        "下载独立网页版",
        data=page_html,
        file_name="思福妥支付模拟计算器.html",
        mime="text/html",
    )
