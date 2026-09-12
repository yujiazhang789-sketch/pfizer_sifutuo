import streamlit as st
import pandas as pd
import altair as alt

# ==========================================================
# 思福妥多层次保障支付模拟计算器 - TEST版
# 说明：
# 1) 本版所有政策参数均为“假设值”，仅用于跑通计算逻辑和页面。
# 2) 后续拿到真实政策后，优先把 POLICY 参数替换为真实数据；
#    再根据实际政策调整各层的“计算基数”。
# ==========================================================

st.set_page_config(
    page_title="思福妥多层次保障支付模拟计算器（TEST）",
    layout="wide"
)

# -----------------------------
# 1. 测试假设参数
# -----------------------------
DEFAULT_PRICE = 1396.0       # 元/支
DEFAULT_DAILY_USAGE = 3      # 支/天
STANDARD_DAYS = [3, 7, 14]

# Pilot地区（TEST版）
PROVINCES = [
    "北京",
    "上海",
    "广东",
    "河南",
    "浙江",
    "山东"
]

POLICY = {
    "基本医保": {
        "rate": 0.70,
        "deductible": 0.0,
        "cap": 300000.0,
        "note": "假设：思福妥治疗费用全部进入基本医保计算基数，报销70%。"
    },
    "大病医保": {
        "rate": 0.60,
        "deductible": 10000.0,
        "cap": 300000.0,
        "note": "假设：以基本医保后患者剩余费用为基数，超过1万元部分报销60%。"
    },
    "惠民保": {
        "rate": 0.50,
        "deductible": 5000.0,
        "cap": 1000000.0,
        "note": "假设：以大病医保后患者剩余费用为基数，超过5000元部分报销50%。"
    },
    "福享关爱": {
        "rate": 0.50,
        "deductible": 1000.0,
        "cap": 200000.0,
        "note": "假设：以惠民保后患者剩余费用为基数，超过1000元部分赔付50%。"
    }
}


# -----------------------------
# 2. 核心计算函数
# -----------------------------
def calc_layer(base_cost, deductible, rate, cap):
    """
    通用单层支付：
    可支付金额 = max(基数 - 起付线, 0) * 比例
    最终支付额再受封顶线约束，且不能超过本层基数。
    """
    eligible = max(float(base_cost) - float(deductible), 0.0)
    payment = eligible * float(rate)
    payment = min(payment, float(cap), float(base_cost))
    remaining = max(float(base_cost) - payment, 0.0)
    return payment, remaining


def calculate_scenario(days, unit_price, daily_usage, policy):
    total_cost = float(unit_price) * float(daily_usage) * int(days)

    # 第一层：基本医保
    basic_pay, after_basic = calc_layer(
        total_cost,
        policy["基本医保"]["deductible"],
        policy["基本医保"]["rate"],
        policy["基本医保"]["cap"]
    )

    # 第二层：大病医保
    major_pay, after_major = calc_layer(
        after_basic,
        policy["大病医保"]["deductible"],
        policy["大病医保"]["rate"],
        policy["大病医保"]["cap"]
    )

    # 第三层：惠民保
    hmb_pay, after_hmb = calc_layer(
        after_major,
        policy["惠民保"]["deductible"],
        policy["惠民保"]["rate"],
        policy["惠民保"]["cap"]
    )

    # 第四层：福享关爱商业保险
    care_pay, final_pay = calc_layer(
        after_hmb,
        policy["福享关爱"]["deductible"],
        policy["福享关爱"]["rate"],
        policy["福享关爱"]["cap"]
    )

    total_reimb = basic_pay + major_pay + hmb_pay + care_pay
    coverage_rate = total_reimb / total_cost if total_cost > 0 else 0
    daily_final = final_pay / days if days > 0 else 0

    return {
        "治疗天数": int(days),
        "原始总费用": total_cost,
        "基本医保支付": basic_pay,
        "基本医保后自付": after_basic,
        "大病医保支付": major_pay,
        "大病医保后自付": after_major,
        "惠民保支付": hmb_pay,
        "惠民保后自付": after_hmb,
        "福享关爱支付": care_pay,
        "最终自付": final_pay,
        "总保障金额": total_reimb,
        "总保障比例": coverage_rate,
        "日均最终自付": daily_final
    }


# -----------------------------
# 3. 页面样式
# -----------------------------
st.markdown("""
<style>
.big-title {
    color: #003366;
    font-size: 28px;
    font-weight: 800;
    margin-bottom: 4px;
}
.subtle {
    color: #666;
    font-size: 13px;
}
.section-title {
    font-size: 18px;
    font-weight: 700;
    margin-top: 8px;
    margin-bottom: 8px;
}
.result-card {
    background: #f7f9fb;
    border: 1px solid #e6e9ed;
    border-radius: 8px;
    padding: 14px;
}
.warning-box {
    background: #fff3cd;
    color: #856404;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 12px;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="big-title">思福妥多层次保障支付模拟计算器</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="warning-box"><b>⚠️ TEST版：</b>'
    '当前所有医保、大病医保、惠民保及商业保险参数均为假设值，仅用于验证计算器逻辑，不代表任何地区真实政策。</div>',
    unsafe_allow_html=True
)

left, right = st.columns([1, 1.6])

# -----------------------------
# 4. 左侧：输入与参数
# -----------------------------
with left:
    st.markdown('<div class="section-title">地区选择</div>', unsafe_allow_html=True)

    selected_province = st.selectbox(
        "省份",
        PROVINCES,
        index=0
    )

    st.caption(
        f"当前选择：{selected_province}。TEST版暂时共用同一套假设政策参数；"
        "正式版将按省份自动匹配当地基本医保、大病医保、惠民保及商业保险规则。"
    )

    st.divider()

    st.markdown('<div class="section-title">基础治疗参数</div>', unsafe_allow_html=True)

    unit_price = st.number_input(
        "思福妥单价（元/支）",
        min_value=0.0,
        value=DEFAULT_PRICE,
        step=1.0
    )

    daily_usage = st.number_input(
        "每日使用量（支/天）",
        min_value=0.0,
        value=float(DEFAULT_DAILY_USAGE),
        step=1.0
    )

    selected_days = st.selectbox(
        "当前查看疗程",
        STANDARD_DAYS,
        index=1,
        format_func=lambda x: f"{x}天"
    )

    current_total = unit_price * daily_usage * selected_days
    st.metric("当前疗程原始总费用", f"¥{current_total:,.0f}")

    st.divider()

    st.markdown('<div class="section-title">四层保障参数（假设，可直接修改）</div>', unsafe_allow_html=True)

    editable_policy = {}

    for layer_name in ["基本医保", "大病医保", "惠民保", "福享关爱"]:
        st.markdown(f"**{layer_name}**")
        c1, c2 = st.columns(2)

        default_rate = POLICY[layer_name]["rate"] * 100
        default_deductible = POLICY[layer_name]["deductible"]
        default_cap = POLICY[layer_name]["cap"]

        rate = c1.number_input(
            f"{layer_name}比例（%）",
            min_value=0.0,
            max_value=100.0,
            value=float(default_rate),
            step=5.0,
            key=f"{layer_name}_rate"
        )

        deductible = c2.number_input(
            f"{layer_name}起付线（元）",
            min_value=0.0,
            value=float(default_deductible),
            step=1000.0,
            key=f"{layer_name}_deductible"
        )

        cap = st.number_input(
            f"{layer_name}封顶线（元）",
            min_value=0.0,
            value=float(default_cap),
            step=10000.0,
            key=f"{layer_name}_cap"
        )

        editable_policy[layer_name] = {
            "rate": rate / 100.0,
            "deductible": deductible,
            "cap": cap,
            "note": POLICY[layer_name]["note"]
        }

        st.caption(POLICY[layer_name]["note"])

    st.info(
        "当前TEST逻辑：每一层都以上一层保障后的患者剩余费用作为下一层计算基数。"
    )


# -----------------------------
# 5. 右侧：当前疗程结果
# -----------------------------
with right:
    current = calculate_scenario(
        selected_days,
        unit_price,
        daily_usage,
        editable_policy
    )

    st.markdown('<div class="section-title">当前疗程结果</div>', unsafe_allow_html=True)
    st.write(f"**当前地区：{selected_province}**")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("原始总费用", f"¥{current['原始总费用']:,.0f}")
    m2.metric("总保障金额", f"¥{current['总保障金额']:,.0f}")
    m3.metric("最终自付", f"¥{current['最终自付']:,.0f}")
    m4.metric("日均自付", f"¥{current['日均最终自付']:,.0f}")

    st.caption(
        f"综合保障比例：{current['总保障比例']:.1%}"
    )

    # 支付路径表
    path_df = pd.DataFrame({
        "支付阶段": [
            "原始治疗费用",
            "基本医保后",
            "大病医保后",
            "惠民保后",
            "福享关爱后"
        ],
        "患者剩余自付": [
            current["原始总费用"],
            current["基本医保后自付"],
            current["大病医保后自付"],
            current["惠民保后自付"],
            current["最终自付"]
        ]
    })

    st.markdown("#### 患者自付逐层下降")

    order = list(path_df["支付阶段"])

    bars = alt.Chart(path_df).mark_bar(size=32).encode(
        y=alt.Y("支付阶段:N", sort=order, title=None),
        x=alt.X("患者剩余自付:Q", title="患者自付金额（元）"),
        tooltip=[
            alt.Tooltip("支付阶段:N"),
            alt.Tooltip("患者剩余自付:Q", format=",.0f")
        ]
    )

    labels = alt.Chart(path_df).mark_text(
        align="left",
        dx=5
    ).encode(
        y=alt.Y("支付阶段:N", sort=order),
        x="患者剩余自付:Q",
        text=alt.Text("患者剩余自付:Q", format=",.0f")
    )

    st.altair_chart(
        (bars + labels).properties(height=260),
        use_container_width=True
    )

    # 各层支付明细
    st.markdown("#### 各层支付明细")

    detail_df = pd.DataFrame({
        "保障层级": ["基本医保", "大病医保", "惠民保", "福享关爱"],
        "本层支付金额": [
            current["基本医保支付"],
            current["大病医保支付"],
            current["惠民保支付"],
            current["福享关爱支付"]
        ],
        "保障后患者自付": [
            current["基本医保后自付"],
            current["大病医保后自付"],
            current["惠民保后自付"],
            current["最终自付"]
        ]
    })

    st.dataframe(
        detail_df.style.format({
            "本层支付金额": "¥{:,.0f}",
            "保障后患者自付": "¥{:,.0f}"
        }),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # -----------------------------
    # 6. 3 / 7 / 14天统一比较
    # -----------------------------
    st.markdown('<div class="section-title">3天 / 7天 / 14天疗程对比</div>', unsafe_allow_html=True)

    compare_rows = [
        calculate_scenario(d, unit_price, daily_usage, editable_policy)
        for d in STANDARD_DAYS
    ]
    compare_df = pd.DataFrame(compare_rows)

    compare_df.insert(0, "省份", selected_province)

    display_compare = compare_df[
        [
            "省份",
            "治疗天数",
            "原始总费用",
            "基本医保支付",
            "大病医保支付",
            "惠民保支付",
            "福享关爱支付",
            "最终自付",
            "日均最终自付",
            "总保障比例"
        ]
    ].copy()

    st.dataframe(
        display_compare.style.format({
            "原始总费用": "¥{:,.0f}",
            "基本医保支付": "¥{:,.0f}",
            "大病医保支付": "¥{:,.0f}",
            "惠民保支付": "¥{:,.0f}",
            "福享关爱支付": "¥{:,.0f}",
            "最终自付": "¥{:,.0f}",
            "日均最终自付": "¥{:,.0f}",
            "总保障比例": "{:.1%}"
        }),
        use_container_width=True,
        hide_index=True
    )

    # 最终自付总额对比
    total_chart_df = compare_df[["治疗天数", "最终自付"]].copy()
    total_chart_df["疗程"] = total_chart_df["治疗天数"].astype(str) + "天"

    total_chart = alt.Chart(total_chart_df).mark_bar(size=45).encode(
        x=alt.X("疗程:N", title="治疗周期", sort=["3天", "7天", "14天"]),
        y=alt.Y("最终自付:Q", title="最终患者自付（元）"),
        tooltip=[
            "疗程:N",
            alt.Tooltip("最终自付:Q", format=",.0f")
        ]
    )

    total_labels = alt.Chart(total_chart_df).mark_text(
        dy=-8
    ).encode(
        x=alt.X("疗程:N", sort=["3天", "7天", "14天"]),
        y="最终自付:Q",
        text=alt.Text("最终自付:Q", format=",.0f")
    )

    st.markdown("#### 不同疗程最终自付")
    st.altair_chart(
        (total_chart + total_labels).properties(height=260),
        use_container_width=True
    )

    # 日均自付趋势
    daily_chart_df = compare_df[["治疗天数", "日均最终自付"]].copy()
    daily_chart_df["疗程"] = daily_chart_df["治疗天数"].astype(str) + "天"

    line = alt.Chart(daily_chart_df).mark_line(point=True).encode(
        x=alt.X("疗程:N", title="治疗周期", sort=["3天", "7天", "14天"]),
        y=alt.Y("日均最终自付:Q", title="日均患者自付（元/天）"),
        tooltip=[
            "疗程:N",
            alt.Tooltip("日均最终自付:Q", format=",.0f")
        ]
    )

    st.markdown("#### 日均治疗自付趋势")
    st.altair_chart(
        line.properties(height=260),
        use_container_width=True
    )

    # 自动结论
    d3 = compare_df.loc[compare_df["治疗天数"] == 3, "日均最终自付"].iloc[0]
    d7 = compare_df.loc[compare_df["治疗天数"] == 7, "日均最终自付"].iloc[0]
    d14 = compare_df.loc[compare_df["治疗天数"] == 14, "日均最终自付"].iloc[0]

    if d3 > d7 > d14:
        st.success(
            f"测试结果：在当前假设参数下，日均患者自付从 "
            f"3天 ¥{d3:,.0f}/天 → 7天 ¥{d7:,.0f}/天 → "
            f"14天 ¥{d14:,.0f}/天，呈逐步下降趋势。"
        )
    else:
        st.info(
            "当前参数下日均自付未呈连续下降。你可以修改左侧起付线和报销比例测试不同情景。"
        )

st.divider()
st.caption(
    "免责声明：本工具为内部测试模型，仅用于演示支付路径及参数敏感性。"
    "所有假设政策参数均不代表真实医保、惠民保或商业保险条款，实际结算以当地政策及保险合同为准。"
)
