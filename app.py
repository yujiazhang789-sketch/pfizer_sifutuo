import streamlit as st
import pandas as pd
import altair as alt

# ==========================================================
# 思福妥® 多层次保障支付模拟计算器 - TEST v3
# 基于当前已知信息：
# - 产品说明书：Version No. 20251225
# - 成人 CrCL >50 mL/min：2.5 g，每8小时1次，静脉输注2小时
# - 复杂性腹腔内感染（cIAI）：5~14天
# - 医院获得性肺炎/呼吸机相关性肺炎（HAP/VAP）：7~14天
# - 治疗方案选择有限的需氧革兰阴性菌感染：疗程依病情/病原体/临床及细菌学进展决定
#
# IMPORTANT：
# 3天/7天/14天在本程序中用于“支付情景测算”，
# 不代表所有适应症的说明书推荐疗程。
#
# 当前医保/大病医保/惠民保/商业保险参数均为假设值，
# 仅用于验证计算器逻辑；后续应改为 policy.xlsx 驱动。
# ==========================================================

st.set_page_config(
    page_title="思福妥多层次保障支付模拟计算器（TEST v3）",
    layout="wide"
)

# -----------------------------
# 1. 产品基础信息（说明书）
# -----------------------------
PRODUCT = {
    "通用名称": "注射用头孢他啶阿维巴坦钠",
    "商品名称": "思福妥® / Zavicefta®",
    "规格": "2.5 g（头孢他啶 2.0 g + 阿维巴坦 0.5 g）",
    "成人标准剂量": "2.5 g，每8小时1次",
    "输注时间": "2小时",
    "成人适用肾功能": "CrCL >50 mL/min",
    "说明书版本": "20251225",
}

INDICATIONS = {
    "复杂性腹腔内感染（cIAI）": "说明书疗程：5~14天；如已知或疑似厌氧菌参与，应与甲硝唑联用。",
    "医院获得性肺炎/呼吸机相关性肺炎（HAP/VAP）": "说明书疗程：7~14天。",
    "治疗方案选择有限的需氧革兰阴性菌感染": "说明书疗程：取决于感染严重程度、病原菌、患者临床情况和细菌学进展。"
}

# 支付模型固定比较场景
STANDARD_DAYS = [3, 7, 14]

# Pilot地区：按“省份 → 城市”设计
REGIONS = {
    "北京": ["北京"],
    "上海": ["上海"],
    "广东": ["广州"],
    "河南": ["郑州"],
    "浙江": ["杭州"],
    "山东": ["济南"],
}

# -----------------------------
# 2. TEST版产品价格/用量
# -----------------------------
# 当前仍使用此前TEST假设；后续请替换为真实价格
DEFAULT_PRICE = 1396.0       # 元/瓶（假设）
DEFAULT_DAILY_USAGE = 3.0    # 瓶/天；与成人 q8h（每日3次）一致

# -----------------------------
# 3. TEST版四层保障参数
# -----------------------------
# 注意：以下全部为假设，不代表任何地区真实政策
POLICY = {
    "基本医保": {
        "rate": 0.70,
        "deductible": 0.0,
        "cap": 300000.0,
        "note": "TEST假设：原始药品费用全部进入基本医保计算基数，报销70%。"
    },
    "大病医保": {
        "rate": 0.60,
        "deductible": 10000.0,
        "cap": 300000.0,
        "note": "TEST假设：以基本医保后患者剩余费用为基数，超过1万元部分报销60%。"
    },
    "惠民保": {
        "rate": 0.50,
        "deductible": 5000.0,
        "cap": 1000000.0,
        "note": "TEST假设：以大病医保后患者剩余费用为基数，超过5000元部分报销50%。"
    },
    "福享关爱": {
        "rate": 0.50,
        "deductible": 1000.0,
        "cap": 200000.0,
        "note": "TEST假设：以惠民保后患者剩余费用为基数，超过1000元部分赔付50%。"
    }
}


# -----------------------------
# 4. 核心计算函数
# -----------------------------
def calc_layer(base_cost, deductible, rate, cap):
    """
    TEST版通用单层支付：
    eligible = max(上一层剩余费用 - 本层起付线, 0)
    payment = eligible * 支付比例
    payment 受封顶线约束，且不得超过本层基数
    """
    base_cost = max(float(base_cost), 0.0)
    deductible = max(float(deductible), 0.0)
    rate = max(min(float(rate), 1.0), 0.0)
    cap = max(float(cap), 0.0)

    eligible = max(base_cost - deductible, 0.0)
    payment = eligible * rate
    payment = min(payment, cap, base_cost)
    remaining = max(base_cost - payment, 0.0)

    return payment, remaining


def calculate_scenario(days, unit_price, daily_usage, policy):
    total_cost = float(unit_price) * float(daily_usage) * int(days)

    basic_pay, after_basic = calc_layer(
        total_cost,
        policy["基本医保"]["deductible"],
        policy["基本医保"]["rate"],
        policy["基本医保"]["cap"]
    )

    major_pay, after_major = calc_layer(
        after_basic,
        policy["大病医保"]["deductible"],
        policy["大病医保"]["rate"],
        policy["大病医保"]["cap"]
    )

    hmb_pay, after_hmb = calc_layer(
        after_major,
        policy["惠民保"]["deductible"],
        policy["惠民保"]["rate"],
        policy["惠民保"]["cap"]
    )

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
# 5. 页面样式
# -----------------------------
st.markdown("""
<style>
.big-title {
    color: #003366;
    font-size: 28px;
    font-weight: 800;
    margin-bottom: 4px;
}
.sub-title {
    color: #6b7280;
    font-size: 13px;
    margin-bottom: 14px;
}
.section-title {
    font-size: 18px;
    font-weight: 700;
    margin-top: 8px;
    margin-bottom: 8px;
}
.warning-box {
    background: #fff3cd;
    color: #856404;
    padding: 11px 13px;
    border-radius: 6px;
    font-size: 12px;
    margin-bottom: 14px;
}
.info-box {
    background: #eef6ff;
    border: 1px solid #d7e9ff;
    padding: 12px;
    border-radius: 7px;
    font-size: 13px;
    line-height: 1.7;
}
.product-box {
    background: #f8f9fa;
    border: 1px solid #e5e7eb;
    padding: 12px;
    border-radius: 7px;
    font-size: 13px;
    line-height: 1.7;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="big-title">思福妥® 多层次保障支付模拟计算器</div>',
    unsafe_allow_html=True
)
st.markdown(
    '<div class="sub-title">基本医保 → 大病医保 → 惠民保 → 福享关爱商业保险项目</div>',
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="warning-box">
    <b>⚠️ TEST版说明：</b>
    当前各层保障政策参数均为模拟假设，不代表任何地区真实医保、惠民保或商业保险政策。
    3天/7天/14天仅为支付情景测算周期，不等同于所有适应症的说明书推荐疗程。
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# 6. 顶部产品说明书信息
# -----------------------------
with st.expander("📘 思福妥说明书信息（当前已同步）", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"""
            <div class="product-box">
            <b>通用名称：</b>{PRODUCT["通用名称"]}<br>
            <b>商品名称：</b>{PRODUCT["商品名称"]}<br>
            <b>规格：</b>{PRODUCT["规格"]}<br>
            <b>说明书版本：</b>{PRODUCT["说明书版本"]}
            </div>
            """,
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(
            f"""
            <div class="product-box">
            <b>成人标准剂量：</b>{PRODUCT["成人标准剂量"]}<br>
            <b>输注时间：</b>{PRODUCT["输注时间"]}<br>
            <b>当前测算默认人群：</b>成人，{PRODUCT["成人适用肾功能"]}<br>
            <b>备注：</b>肾功能受损患者需按说明书调整剂量，当前TEST版暂不自动计算肾功能减量。
            </div>
            """,
            unsafe_allow_html=True
        )

left, right = st.columns([1, 1.65])

# -----------------------------
# 7. 左侧输入
# -----------------------------
with left:
    st.markdown('<div class="section-title">地区与治疗场景</div>', unsafe_allow_html=True)

    selected_province = st.selectbox(
        "省份",
        list(REGIONS.keys()),
        index=0
    )

    selected_city = st.selectbox(
        "城市",
        REGIONS[selected_province],
        index=0
    )

    selected_indication = st.selectbox(
        "适应症",
        list(INDICATIONS.keys()),
        index=0
    )

    st.info(INDICATIONS[selected_indication])

    st.markdown(
        f"**当前地区：{selected_province} · {selected_city}**  \n"
        "TEST版暂时所有地区共用同一套假设支付参数；正式版将按地区自动加载政策。"
    )

    st.divider()

    st.markdown('<div class="section-title">基础治疗参数</div>', unsafe_allow_html=True)

    unit_price = st.number_input(
        "思福妥单价（元/瓶）",
        min_value=0.0,
        value=float(DEFAULT_PRICE),
        step=1.0,
        help="当前为TEST假设值，后续替换为真实价格。"
    )

    daily_usage = st.number_input(
        "每日使用量（瓶/天）",
        min_value=0.0,
        value=float(DEFAULT_DAILY_USAGE),
        step=1.0,
        help="成人CrCL >50 mL/min说明书标准给药频率为每8小时1次，对应每日3次。"
    )

    selected_days = st.selectbox(
        "当前查看的支付测算周期",
        STANDARD_DAYS,
        index=1,
        format_func=lambda x: f"{x}天"
    )

    current_total = unit_price * daily_usage * selected_days

    p1, p2 = st.columns(2)
    p1.metric("每日药品费用", f"¥{unit_price * daily_usage:,.0f}")
    p2.metric("当前周期原始总费用", f"¥{current_total:,.0f}")

    if selected_days == 3:
        st.warning(
            "3天为支付模拟情景。根据当前说明书，cIAI疗程为5~14天，"
            "HAP/VAP疗程为7~14天；请勿将3天理解为上述适应症的说明书推荐疗程。"
        )

    st.divider()

    st.markdown('<div class="section-title">四层保障参数（TEST假设，可修改）</div>', unsafe_allow_html=True)

    editable_policy = {}

    for layer_name in ["基本医保", "大病医保", "惠民保", "福享关爱"]:
        with st.expander(layer_name, expanded=(layer_name == "基本医保")):
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
                f"{layer_name}起付线/免赔额（元）",
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

    st.caption("当前TEST计算逻辑：每层以上一层保障后的患者剩余费用作为下一层计算基数。")

# -----------------------------
# 8. 右侧：当前疗程结果
# -----------------------------
with right:
    current = calculate_scenario(
        selected_days,
        unit_price,
        daily_usage,
        editable_policy
    )

    st.markdown('<div class="section-title">当前支付测算结果</div>', unsafe_allow_html=True)
    st.write(
        f"**地区：{selected_province} · {selected_city} ｜ "
        f"适应症：{selected_indication} ｜ 测算周期：{selected_days}天**"
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("原始总费用", f"¥{current['原始总费用']:,.0f}")
    m2.metric("总保障金额", f"¥{current['总保障金额']:,.0f}")
    m3.metric("最终患者自付", f"¥{current['最终自付']:,.0f}")
    m4.metric("日均患者自付", f"¥{current['日均最终自付']:,.0f}")

    st.caption(f"综合保障比例：{current['总保障比例']:.1%}")

    # 支付路径
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

    st.markdown("#### 患者自付逐层变化")

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

    # 各层明细
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
    # 9. 3/7/14天统一比较
    # -----------------------------
    st.markdown('<div class="section-title">3天 / 7天 / 14天支付情景对比</div>', unsafe_allow_html=True)

    compare_rows = [
        calculate_scenario(d, unit_price, daily_usage, editable_policy)
        for d in STANDARD_DAYS
    ]
    compare_df = pd.DataFrame(compare_rows)
    compare_df.insert(0, "城市", selected_city)
    compare_df.insert(0, "省份", selected_province)

    display_compare = compare_df[
        [
            "省份",
            "城市",
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

    # 最终自付总额
    total_chart_df = compare_df[["治疗天数", "最终自付"]].copy()
    total_chart_df["疗程"] = total_chart_df["治疗天数"].astype(str) + "天"

    total_chart = alt.Chart(total_chart_df).mark_bar(size=45).encode(
        x=alt.X("疗程:N", title="支付测算周期", sort=["3天", "7天", "14天"]),
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

    st.markdown("#### 不同支付测算周期的最终自付")
    st.altair_chart(
        (total_chart + total_labels).properties(height=260),
        use_container_width=True
    )

    # 日均自付趋势
    daily_chart_df = compare_df[["治疗天数", "日均最终自付"]].copy()
    daily_chart_df["疗程"] = daily_chart_df["治疗天数"].astype(str) + "天"

    line = alt.Chart(daily_chart_df).mark_line(point=True).encode(
        x=alt.X("疗程:N", title="支付测算周期", sort=["3天", "7天", "14天"]),
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
            f"当前TEST参数下：日均患者自付从 "
            f"3天 ¥{d3:,.0f}/天 → 7天 ¥{d7:,.0f}/天 → "
            f"14天 ¥{d14:,.0f}/天，呈逐步下降趋势。"
        )
    else:
        st.info(
            "当前参数下日均患者自付未呈连续下降。"
            "后续应以真实地区政策参数验证该趋势。"
        )

# -----------------------------
# 10. 页尾说明
# -----------------------------
st.divider()

st.markdown(
    """
    **说明书口径提示：**
    - 成人 CrCL >50 mL/min：2.5 g，每8小时1次，静脉输注2小时；
    - cIAI：5~14天；
    - HAP/VAP：7~14天；
    - 治疗方案选择有限的需氧革兰阴性菌感染：疗程依患者具体情况决定；
    - 肾功能受损患者需调整给药方案，本TEST版尚未纳入肾功能减量计算。
    """
)

st.caption(
    "免责声明：本工具目前为内部模型测试版。支付金额仅用于模型演示，"
    "不构成医保结算、保险理赔或临床用药建议。实际用药以说明书及医师判断为准，"
    "实际支付以当地医保政策、保险条款和结算结果为准。"
)
