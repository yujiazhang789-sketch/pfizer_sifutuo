import streamlit as st
import pandas as pd
import altair as alt

# ==========================================================
# 思福妥® 多层次保障支付模拟计算器 - Meeting Update v4
# 2026-09 最新会议逻辑
#
# 核心原则：
# 1) 只测算“新增使用思福妥”这一药物本身带来的增量费用与保障。
# 2) 基本医保优先按“每支固定医保支付金额”处理。
# 3) 大病医保按年度累计口径，计算本次思福妥新增触发的增量赔付。
# 4) 惠民保按城市后台匹配；用户只选择是否参加及是否既往症。
# 5) 福享关爱无免赔额概念；用户只选择是否参加。
# 6) 不在网页加载说明书，避免信息过载和影响速度。
#
# 当前待确认：
# - 北京基本医保每支固定支付金额：当前按326元/支演示，待Local二次确认。
# - 北京大病医保：起付线30,404元；30,404~50,000元部分60%，
#   超过50,000元部分70%（按会议当前口径）。
# - 惠民保、福享关爱完整赔付参数尚未最终确认，程序中明确标记为DEMO占位。
# ==========================================================

st.set_page_config(
    page_title="思福妥多层次保障支付模拟计算器",
    layout="wide"
)

PRODUCT = {
    "name": "思福妥®",
    "unit_price": 1396.0,
    "daily_units": 3,
    "scenarios": [3, 7, 14],
}

REGIONS = {
    "北京": ["北京"],
    "上海": ["上海"],
    "广东": ["广州", "深圳"],
    "河南": ["郑州"],
    "浙江": ["杭州"],
    "山东": ["济南"],
}

GENERIC_DEMO_POLICY = {
    "status": "待Local补充",
    "basic": {
        "fixed_pay_per_unit": 326.0,
        "verified": False,
        "note": "DEMO占位：暂按每支固定医保支付326元演示，非当地真实政策。"
    },
    "major": {
        "deductible": 30000.0,
        "tier1_upper": 50000.0,
        "tier1_rate": 0.60,
        "tier2_rate": 0.70,
        "verified": False,
        "note": "DEMO占位：该城市大病医保参数待Local补充。"
    },
    "hmb": {
        "name": "当地惠民保（待补充）",
        "scope": "院内医保内自付责任（待确认）",
        "healthy_deductible": 5000.0,
        "healthy_rate": 0.50,
        "preexisting_deductible": 5000.0,
        "preexisting_rate": 0.30,
        "verified": False,
        "official_link": "",
        "note": "DEMO占位参数，仅用于跑通四层模型。"
    },
    "care": {
        "name": "福享关爱",
        "rate": 0.50,
        "verified": False,
        "note": "会议已确认无免赔额；赔付比例仍待最终确认，TEST版暂按50%演示。"
    }
}

POLICY_DB = {
    ("北京", "北京"): {
        "status": "北京Demo｜部分数据待Local二次确认",
        "basic": {
            "fixed_pay_per_unit": 326.0,
            "verified": False,
            "note": "当前按每支固定医保支付326元测算；最终医保支付口径仍需北京Local二次确认。"
        },
        "major": {
            "deductible": 30404.0,
            "tier1_upper": 50000.0,
            "tier1_rate": 0.60,
            "tier2_rate": 0.70,
            "verified": True,
            "note": "年度累计口径：30,404元以上至50,000元部分按60%，超过50,000元部分按70%。"
        },
        "hmb": {
            "name": "北京普惠健康保",
            "scope": "院内医保内自付责任",
            "healthy_deductible": 5000.0,
            "healthy_rate": 0.50,
            "preexisting_deductible": 5000.0,
            "preexisting_rate": 0.30,
            "verified": False,
            "official_link": "",
            "note": "已确认按院内医保内自付责任方向测算；具体免赔额/比例仍待Local核实。"
        },
        "care": {
            "name": "福享关爱",
            "rate": 0.50,
            "verified": False,
            "note": "无免赔额；具体赔付比例仍待项目规则最终确认，TEST版暂按50%演示。"
        }
    }
}

def money(x):
    return f"¥{float(x):,.0f}"

def get_policy(province, city):
    return POLICY_DB.get((province, city), GENERIC_DEMO_POLICY)

def calc_basic(total_cost, units, policy):
    fixed = float(policy.get("fixed_pay_per_unit", 0))
    pay = min(float(total_cost), float(units) * fixed)
    return pay, max(float(total_cost) - pay, 0.0)

def cumulative_major_claim(cumulative_eligible, policy):
    x = max(float(cumulative_eligible), 0.0)
    d = float(policy["deductible"])
    u = float(policy["tier1_upper"])
    r1 = float(policy["tier1_rate"])
    r2 = float(policy["tier2_rate"])
    if x <= d:
        return 0.0
    if x <= u:
        return (x - d) * r1
    return max(u - d, 0.0) * r1 + (x - u) * r2

def calc_major_increment(prior_cumulative, current_after_basic, policy):
    before = cumulative_major_claim(prior_cumulative, policy)
    after = cumulative_major_claim(prior_cumulative + current_after_basic, policy)
    pay = max(after - before, 0.0)
    pay = min(pay, float(current_after_basic))
    return pay, max(float(current_after_basic) - pay, 0.0)

def calc_hmb(base_cost, is_preexisting, policy, participate):
    if not participate:
        return 0.0, float(base_cost)
    if is_preexisting:
        deductible = float(policy["preexisting_deductible"])
        rate = float(policy["preexisting_rate"])
    else:
        deductible = float(policy["healthy_deductible"])
        rate = float(policy["healthy_rate"])
    eligible = max(float(base_cost) - deductible, 0.0)
    pay = min(eligible * rate, float(base_cost))
    return pay, max(float(base_cost) - pay, 0.0)

def calc_care(base_cost, policy, participate):
    if not participate:
        return 0.0, float(base_cost)
    pay = min(float(base_cost) * float(policy["rate"]), float(base_cost))
    return pay, max(float(base_cost) - pay, 0.0)

def calculate_scenario(
    days, province, city, prior_major_cumulative,
    participate_hmb, is_preexisting, participate_care
):
    policy = get_policy(province, city)
    units = int(PRODUCT["daily_units"] * days)
    total_cost = PRODUCT["unit_price"] * units

    basic_pay, after_basic = calc_basic(total_cost, units, policy["basic"])
    major_pay, after_major = calc_major_increment(
        prior_major_cumulative, after_basic, policy["major"]
    )
    hmb_pay, after_hmb = calc_hmb(
        after_major, is_preexisting, policy["hmb"], participate_hmb
    )
    care_pay, final_pay = calc_care(
        after_hmb, policy["care"], participate_care
    )

    total_support = basic_pay + major_pay + hmb_pay + care_pay
    return {
        "省份": province,
        "城市": city,
        "支付测算周期": days,
        "用药支数": units,
        "思福妥药品费用": total_cost,
        "基本医保支付": basic_pay,
        "医保后药品自付": after_basic,
        "大病医保支付": major_pay,
        "大病后药品自付": after_major,
        "惠民保支付": hmb_pay,
        "惠民保后药品自付": after_hmb,
        "福享关爱支付": care_pay,
        "最终药品自付": final_pay,
        "总保障金额": total_support,
        "综合保障比例": total_support / total_cost if total_cost else 0,
        "日均药品自付": final_pay / days if days else 0,
    }

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.hero-title { font-size: 30px; font-weight: 800; color: #17365D; margin-bottom: 2px; }
.hero-sub { color: #667085; font-size: 14px; margin-bottom: 14px; }
.notice {
    background: #FFF7E6; border: 1px solid #FFD591; border-radius: 10px;
    padding: 11px 14px; color: #8C5A00; font-size: 12px; line-height: 1.65;
    margin-bottom: 14px;
}
.info {
    background: #F5F9FF; border: 1px solid #D9E8FF; border-radius: 10px;
    padding: 11px 14px; color: #344054; font-size: 12px; line-height: 1.65;
}
.section-title { font-size: 18px; font-weight: 750; color: #1D2939; margin: 8px 0 10px 0; }
.layer-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
    gap: 10px; margin: 10px 0 14px 0;
}
.layer-card { border-radius: 12px; padding: 13px 14px; min-height: 112px; border: 1px solid rgba(0,0,0,.06); }
.layer-name { font-size: 13px; font-weight: 700; opacity: .85; margin-bottom: 5px; }
.layer-value { font-size: 23px; font-weight: 800; margin-bottom: 3px; }
.layer-note { font-size: 11px; opacity: .78; line-height: 1.45; }
.blue { background: #EAF3FF; color: #194F90; }
.gold { background: #FFF6DE; color: #8A5A00; }
.purple { background: #F2EDFF; color: #5A3DAA; }
.green { background: #EAF8F0; color: #26734D; }
.final-card {
    background: linear-gradient(135deg, #FFF1F0, #FFF7F6);
    border: 1px solid #FFCCC7; border-radius: 14px; padding: 15px 18px;
    margin: 8px 0 14px 0;
}
.final-label { font-size: 13px; color: #8C2E24; }
.final-value { font-size: 30px; font-weight: 850; color: #C53B2C; }
.final-sub { font-size: 12px; color: #7A4A45; margin-top: 3px; }
.status-badge {
    display: inline-block; background: #F2F4F7; color: #475467; border-radius: 999px;
    padding: 4px 9px; font-size: 11px; margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero-title">思福妥® 多层次保障支付模拟计算器</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">基本医保 → 大病医保 → 惠民保 → 福享关爱｜聚焦思福妥药品增量支付</div>', unsafe_allow_html=True)
st.markdown("""
<div class="notice">
<b>模型口径：</b>
本工具仅测算“选择思福妥”这一药物本身新增的药品费用与保障支付。
患者原有ICU/抗感染治疗及其他诊疗项目仍按原路径结算，不计入本页面最终药品自付；
但判断大病医保是否跨过年度起付线时，可纳入患者此前已累计的合规个人负担估算。
</div>
""", unsafe_allow_html=True)

left, right = st.columns([0.92, 1.55], gap="large")

with left:
    st.markdown('<div class="section-title">① 选择地区与保障</div>', unsafe_allow_html=True)

    province = st.selectbox("省份", list(REGIONS.keys()))
    city = st.selectbox("城市", REGIONS[province])
    policy = get_policy(province, city)

    st.markdown(f'<span class="status-badge">{policy["status"]}</span>', unsafe_allow_html=True)

    if (province, city) not in POLICY_DB:
        st.warning("该城市真实政策尚未录入，目前使用DEMO占位参数，仅用于验证页面和计算逻辑。")

    st.markdown("**惠民保**")
    st.caption(f'{policy["hmb"]["name"]}｜{policy["hmb"]["scope"]}')

    participate_hmb = st.checkbox(f'参加 {policy["hmb"]["name"]}', value=True)

    is_preexisting = False
    if participate_hmb:
        population = st.radio(
            "惠民保人群",
            ["非既往症人群", "既往症人群"],
            horizontal=True
        )
        is_preexisting = population == "既往症人群"

    participate_care = st.checkbox(f'参加 {policy["care"]["name"]}', value=True)

    st.divider()
    st.markdown('<div class="section-title">② 大病医保累计基础</div>', unsafe_allow_html=True)

    base_mode = st.radio(
        "使用思福妥前，本年度已累计符合大病医保口径的个人负担/合规费用（估算）",
        ["0元", "约2万元", "约5万元", "自定义"],
        index=1
    )

    if base_mode == "0元":
        prior_major_cumulative = 0.0
    elif base_mode == "约2万元":
        prior_major_cumulative = 20000.0
    elif base_mode == "约5万元":
        prior_major_cumulative = 50000.0
    else:
        prior_major_cumulative = st.number_input(
            "自定义累计金额（元）",
            min_value=0.0,
            value=20000.0,
            step=1000.0
        )

    st.caption("该金额仅用于判断大病医保门槛，不会再次计入本次思福妥药品自付。")

    st.divider()
    st.markdown('<div class="section-title">③ 当前支付测算周期</div>', unsafe_allow_html=True)

    selected_days = st.selectbox(
        "周期",
        PRODUCT["scenarios"],
        index=1,
        format_func=lambda x: f"{x}天"
    )

    current_units = PRODUCT["daily_units"] * selected_days
    current_drug_cost = PRODUCT["unit_price"] * current_units

    c1, c2 = st.columns(2)
    c1.metric("用药支数", f"{current_units} 支")
    c2.metric("药品费用", money(current_drug_cost))

    st.markdown(
        f"""
        <div class="info">
        <b>固定产品参数</b><br>
        单价：{money(PRODUCT["unit_price"])}/支<br>
        每日用量：{PRODUCT["daily_units"]}支/天<br>
        当前周期：{selected_days}天，共{current_units}支
        </div>
        """,
        unsafe_allow_html=True
    )

with right:
    result = calculate_scenario(
        selected_days, province, city, prior_major_cumulative,
        participate_hmb, is_preexisting, participate_care
    )

    st.markdown('<div class="section-title">当前测算结果</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="layer-grid">
            <div class="layer-card blue">
                <div class="layer-name">① 基本医保</div>
                <div class="layer-value">{money(result["基本医保支付"])}</div>
                <div class="layer-note">当前按每支固定支付 {money(policy["basic"]["fixed_pay_per_unit"])}</div>
            </div>
            <div class="layer-card gold">
                <div class="layer-name">② 大病医保</div>
                <div class="layer-value">{money(result["大病医保支付"])}</div>
                <div class="layer-note">结合此前累计费用，计算本次新增触发金额</div>
            </div>
            <div class="layer-card purple">
                <div class="layer-name">③ 惠民保</div>
                <div class="layer-value">{money(result["惠民保支付"])}</div>
                <div class="layer-note">{policy["hmb"]["name"]}</div>
            </div>
            <div class="layer-card green">
                <div class="layer-name">④ 福享关爱</div>
                <div class="layer-value">{money(result["福享关爱支付"])}</div>
                <div class="layer-note">无免赔额；项目参数后台计算</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="final-card">
            <div class="final-label">经过四重保障后的思福妥最终药品自付</div>
            <div class="final-value">{money(result["最终药品自付"])}</div>
            <div class="final-sub">
                日均药品自付 {money(result["日均药品自付"])}/天
                · 综合保障比例 {result["综合保障比例"]:.1%}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    path_df = pd.DataFrame({
        "阶段": ["原始药品费用", "基本医保后", "大病医保后", "惠民保后", "福享关爱后"],
        "患者药品自付": [
            result["思福妥药品费用"],
            result["医保后药品自付"],
            result["大病后药品自付"],
            result["惠民保后药品自付"],
            result["最终药品自付"]
        ]
    })
    stage_order = path_df["阶段"].tolist()

    bars = alt.Chart(path_df).mark_bar(size=32).encode(
        y=alt.Y("阶段:N", sort=stage_order, title=None),
        x=alt.X("患者药品自付:Q", title="患者药品自付（元）"),
        tooltip=["阶段:N", alt.Tooltip("患者药品自付:Q", format=",.0f")]
    )
    labels = alt.Chart(path_df).mark_text(align="left", dx=5).encode(
        y=alt.Y("阶段:N", sort=stage_order),
        x="患者药品自付:Q",
        text=alt.Text("患者药品自付:Q", format=",.0f")
    )
    st.markdown("#### 自付逐层下降")
    st.altair_chart((bars + labels).properties(height=260), use_container_width=True)

    details = pd.DataFrame({
        "层级": ["基本医保", "大病医保", "惠民保", "福享关爱"],
        "本层支付": [
            result["基本医保支付"], result["大病医保支付"],
            result["惠民保支付"], result["福享关爱支付"]
        ],
        "本层后药品自付": [
            result["医保后药品自付"], result["大病后药品自付"],
            result["惠民保后药品自付"], result["最终药品自付"]
        ]
    })
    st.dataframe(
        details.style.format({
            "本层支付": "¥{:,.0f}",
            "本层后药品自付": "¥{:,.0f}"
        }),
        use_container_width=True,
        hide_index=True
    )

    st.divider()
    st.markdown('<div class="section-title">3天 / 7天 / 14天支付情景</div>', unsafe_allow_html=True)

    compare_rows = [
        calculate_scenario(
            d, province, city, prior_major_cumulative,
            participate_hmb, is_preexisting, participate_care
        )
        for d in PRODUCT["scenarios"]
    ]
    compare_df = pd.DataFrame(compare_rows)
    show_cols = [
        "支付测算周期", "用药支数", "思福妥药品费用",
        "基本医保支付", "大病医保支付", "惠民保支付",
        "福享关爱支付", "最终药品自付", "日均药品自付", "综合保障比例"
    ]
    st.dataframe(
        compare_df[show_cols].style.format({
            "思福妥药品费用": "¥{:,.0f}",
            "基本医保支付": "¥{:,.0f}",
            "大病医保支付": "¥{:,.0f}",
            "惠民保支付": "¥{:,.0f}",
            "福享关爱支付": "¥{:,.0f}",
            "最终药品自付": "¥{:,.0f}",
            "日均药品自付": "¥{:,.0f}",
            "综合保障比例": "{:.1%}"
        }),
        use_container_width=True,
        hide_index=True
    )

    trend_df = compare_df[["支付测算周期", "日均药品自付"]].copy()
    trend_df["周期"] = trend_df["支付测算周期"].astype(str) + "天"
    line = alt.Chart(trend_df).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X("周期:N", sort=["3天", "7天", "14天"], title="支付测算周期"),
        y=alt.Y("日均药品自付:Q", title="日均药品自付（元/天）"),
        tooltip=["周期:N", alt.Tooltip("日均药品自付:Q", format=",.0f")]
    )
    st.markdown("#### 日均药品自付趋势")
    st.altair_chart(line.properties(height=250), use_container_width=True)

    d3 = compare_df.loc[compare_df["支付测算周期"] == 3, "日均药品自付"].iloc[0]
    d7 = compare_df.loc[compare_df["支付测算周期"] == 7, "日均药品自付"].iloc[0]
    d14 = compare_df.loc[compare_df["支付测算周期"] == 14, "日均药品自付"].iloc[0]

    if d3 > d7 > d14:
        st.success(
            f"当前模型下，日均药品自付从3天 {money(d3)}/天 → "
            f"7天 {money(d7)}/天 → 14天 {money(d14)}/天，呈下降趋势。"
        )
    else:
        st.info("当前参数下日均药品自付未呈连续下降；后续需用Local确认后的真实政策参数继续验证。")

st.divider()

with st.expander("查看当前地区后台政策口径", expanded=False):
    st.write(f"**地区：** {province} · {city}")
    st.write(f"**基本医保：** {policy['basic']['note']}")
    st.write(f"**大病医保：** {policy['major']['note']}")
    st.write(f"**惠民保：** {policy['hmb']['note']}")
    st.write(f"**福享关爱：** {policy['care']['note']}")
    if not policy["hmb"]["verified"] or not policy["care"]["verified"]:
        st.warning("当前惠民保/福享关爱仍含DEMO占位参数。正式对外使用前，请先完成Local及项目正式条款核验。")

st.markdown("""
<div class="info">
<b>免责声明</b><br>
本模型用于内部支付路径模拟，不构成医保结算、保险理赔或临床用药建议。
实际支付结果可能因患者参保身份、在职/退休状态、医院等级、门诊/住院场景、
特殊人群政策、年度封顶线、实际累计费用、具体计算基数及当地实时政策而产生差异。
本工具聚焦思福妥药品本身的增量支付，患者其他诊疗费用未纳入最终药品自付金额。
所有结果应以当地医保部门、保险产品正式条款及实际结算为准。
</div>
""", unsafe_allow_html=True)
