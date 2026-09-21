import streamlit as st
import pandas as pd
import altair as alt

# ==========================================================
# 思福妥® 多层次保障支付模拟计算器 - v5
# UI参考：xacduro-insurance.netlify.app 的模块化、卡片化、内部工具呈现方式
# 逻辑基础：2026-09 最新会议口径
#
# 重要：
# - 本版聚焦“思福妥药品本身”的增量支付路径，不重建患者完整住院结算。
# - 北京基础医保固定支付金额、大病医保阶梯按当前会议口径录入。
# - 惠民保/福享关爱仍有待Local/项目正式规则确认的参数，页面会清晰标记。
# ==========================================================

st.set_page_config(
    page_title="思福妥多层次保障支付模拟计算器",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------------------------------------------------
# 1. 固定产品参数
# ----------------------------------------------------------
PRODUCT = {
    "name": "思福妥®",
    "unit_price": 1396.0,
    "daily_units": 3,
    "scenarios": [3, 7, 14],
}

# ----------------------------------------------------------
# 2. Pilot 地区
# ----------------------------------------------------------
REGIONS = {
    "北京": ["北京"],
    "上海": ["上海"],
    "广东": ["广州", "深圳"],
    "河南": ["郑州"],
    "浙江": ["杭州"],
    "山东": ["济南"],
}

# ----------------------------------------------------------
# 3. 后台政策数据库
# 后续可迁移至 policy.xlsx
# ----------------------------------------------------------
GENERIC_DEMO_POLICY = {
    "status": "待Local补充",
    "source_status": "DEMO占位参数",
    "basic": {
        "fixed_pay_per_unit": 326.0,
        "verified": False,
        "note": "暂按每支固定医保支付326元演示，非当地真实政策。"
    },
    "major": {
        "deductible": 30000.0,
        "tier1_upper": 50000.0,
        "tier1_rate": 0.60,
        "tier2_rate": 0.70,
        "verified": False,
        "note": "其他城市大病医保参数待Local补充。"
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
        "status": "北京 Pilot Demo",
        "source_status": "部分数据待Local二次确认",
        "basic": {
            "fixed_pay_per_unit": 326.0,
            "verified": False,
            "note": "当前按每支固定医保支付326元测算；会议要求继续与北京Local确认最终医保支付口径。"
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
            "note": "无免赔额；具体赔付比例仍待项目正式规则确认，TEST版暂按50%演示。"
        }
    }
}

# ----------------------------------------------------------
# 4. 工具函数
# ----------------------------------------------------------
def money(x):
    return f"¥{float(x):,.0f}"

def get_policy(province, city):
    return POLICY_DB.get((province, city), GENERIC_DEMO_POLICY)

def calc_basic(total_cost, units, basic_policy):
    fixed = float(basic_policy.get("fixed_pay_per_unit", 0))
    pay = min(float(total_cost), float(units) * fixed)
    after = max(float(total_cost) - pay, 0.0)
    return pay, after

def cumulative_major_claim(cumulative_eligible, major_policy):
    x = max(float(cumulative_eligible), 0.0)
    deductible = float(major_policy["deductible"])
    tier1_upper = float(major_policy["tier1_upper"])
    r1 = float(major_policy["tier1_rate"])
    r2 = float(major_policy["tier2_rate"])

    if x <= deductible:
        return 0.0
    if x <= tier1_upper:
        return (x - deductible) * r1

    tier1_pay = max(tier1_upper - deductible, 0.0) * r1
    tier2_pay = (x - tier1_upper) * r2
    return max(tier1_pay + tier2_pay, 0.0)

def calc_major_increment(prior_cumulative, current_after_basic, major_policy):
    prior = max(float(prior_cumulative), 0.0)
    current = max(float(current_after_basic), 0.0)

    before_claim = cumulative_major_claim(prior, major_policy)
    after_claim = cumulative_major_claim(prior + current, major_policy)
    incremental_pay = max(after_claim - before_claim, 0.0)
    incremental_pay = min(incremental_pay, current)

    return incremental_pay, max(current - incremental_pay, 0.0)

def calc_hmb(base_cost, is_preexisting, hmb_policy, participate):
    if not participate:
        return 0.0, float(base_cost)

    if is_preexisting:
        deductible = float(hmb_policy["preexisting_deductible"])
        rate = float(hmb_policy["preexisting_rate"])
    else:
        deductible = float(hmb_policy["healthy_deductible"])
        rate = float(hmb_policy["healthy_rate"])

    eligible = max(float(base_cost) - deductible, 0.0)
    pay = min(eligible * rate, float(base_cost))
    return pay, max(float(base_cost) - pay, 0.0)

def calc_care(base_cost, care_policy, participate):
    if not participate:
        return 0.0, float(base_cost)

    rate = float(care_policy["rate"])
    pay = min(float(base_cost) * rate, float(base_cost))
    return pay, max(float(base_cost) - pay, 0.0)

def calculate_scenario(
    days,
    province,
    city,
    prior_major_cumulative,
    participate_hmb,
    is_preexisting,
    participate_care
):
    policy = get_policy(province, city)

    units = int(PRODUCT["daily_units"] * days)
    total_cost = float(PRODUCT["unit_price"]) * units

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
        "综合保障比例": total_support / total_cost if total_cost > 0 else 0,
        "日均药品自付": final_pay / days if days > 0 else 0,
    }

# ----------------------------------------------------------
# 5. 页面 CSS
# ----------------------------------------------------------
st.markdown("""
<style>
:root {
    --navy: #153B63;
    --navy-2: #0F2E4D;
    --blue: #2F6BFF;
    --cyan: #20A7C9;
    --mint: #2AA876;
    --amber: #E7A93B;
    --purple: #7A5AF8;
    --ink: #14202B;
    --muted: #667085;
    --line: #E6ECF2;
    --surface: #F7F9FC;
}

html, body, [class*="css"] {
    font-family: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
    max-width: 1320px;
}

header[data-testid="stHeader"] {
    background: rgba(255,255,255,0);
}

#MainMenu, footer {
    visibility: hidden;
}

.hero {
    background:
        radial-gradient(circle at 85% 15%, rgba(32,167,201,.18), transparent 26%),
        linear-gradient(135deg, #0F2E4D 0%, #153B63 68%, #1C547C 100%);
    border-radius: 20px;
    padding: 28px 30px 25px 30px;
    color: white;
    margin-bottom: 16px;
    box-shadow: 0 12px 34px rgba(21,59,99,.14);
}
.hero-kicker {
    font-size: 12px;
    letter-spacing: .14em;
    font-weight: 700;
    opacity: .76;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.hero-title {
    font-size: 32px;
    font-weight: 800;
    line-height: 1.2;
    margin-bottom: 7px;
}
.hero-sub {
    font-size: 14px;
    color: rgba(255,255,255,.82);
    line-height: 1.6;
    max-width: 880px;
}
.hero-badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 15px;
}
.hero-badge {
    display: inline-flex;
    align-items: center;
    padding: 6px 10px;
    border-radius: 999px;
    background: rgba(255,255,255,.10);
    border: 1px solid rgba(255,255,255,.16);
    font-size: 11px;
    color: rgba(255,255,255,.92);
}

.notice {
    background: #F8FAFD;
    border: 1px solid var(--line);
    border-left: 4px solid var(--cyan);
    border-radius: 12px;
    padding: 11px 14px;
    color: #475467;
    font-size: 12px;
    line-height: 1.65;
    margin-bottom: 14px;
}

.section-eyebrow {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #98A2B3;
    font-weight: 700;
    margin-bottom: 3px;
}
.section-title {
    font-size: 19px;
    font-weight: 800;
    color: #1D2939;
    margin-bottom: 10px;
}

.panel {
    background: white;
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 15px 16px;
    box-shadow: 0 5px 20px rgba(29,41,57,.045);
    margin-bottom: 12px;
}

.status-line {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    padding: 8px 10px;
    background:#F8FAFC;
    border-radius:10px;
    margin-bottom:10px;
    font-size:12px;
}
.status-pill {
    display:inline-flex;
    align-items:center;
    gap:5px;
    border-radius:999px;
    padding:4px 8px;
    background:#EEF4FF;
    color:#2F5EC4;
    font-size:11px;
    font-weight:700;
}

.layer-flow {
    display: grid;
    grid-template-columns: repeat(4, minmax(130px, 1fr));
    gap: 10px;
    margin: 10px 0 14px;
}
.layer-card {
    position: relative;
    overflow: hidden;
    border-radius: 14px;
    padding: 15px 15px 14px;
    min-height: 124px;
    border: 1px solid rgba(0,0,0,.045);
}
.layer-card:before {
    content:"";
    position:absolute;
    top:0;
    left:0;
    right:0;
    height:4px;
    background: currentColor;
    opacity:.85;
}
.layer-index {
    font-size:10px;
    font-weight:800;
    letter-spacing:.08em;
    opacity:.58;
    margin-bottom:5px;
}
.layer-name {
    font-size:13px;
    font-weight:800;
    margin-bottom:5px;
}
.layer-value {
    font-size:24px;
    font-weight:850;
    margin-bottom:5px;
}
.layer-note {
    font-size:11px;
    opacity:.72;
    line-height:1.45;
}
.card-blue { background:#EEF5FF; color:#285EAD; }
.card-gold { background:#FFF7E9; color:#946200; }
.card-purple { background:#F4F0FF; color:#6247AA; }
.card-green { background:#EDF9F2; color:#26754F; }

.final-panel {
    background: linear-gradient(135deg, #F8FBFF 0%, #EDF6FF 100%);
    border: 1px solid #D6E9FA;
    border-radius: 16px;
    padding: 18px 20px;
    margin: 8px 0 16px;
}
.final-top {
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    gap:15px;
    flex-wrap:wrap;
}
.final-label {
    color:#51606E;
    font-size:12px;
    margin-bottom:4px;
}
.final-value {
    font-size:34px;
    line-height:1.1;
    font-weight:900;
    color:#153B63;
}
.final-meta {
    display:flex;
    gap:18px;
    flex-wrap:wrap;
    color:#51606E;
    font-size:12px;
}
.final-meta strong {
    color:#153B63;
    font-size:15px;
}

.mini-grid {
    display:grid;
    grid-template-columns: repeat(3, 1fr);
    gap:9px;
    margin-top:10px;
}
.mini-card {
    background:white;
    border:1px solid var(--line);
    border-radius:12px;
    padding:10px 12px;
}
.mini-label {
    color:#98A2B3;
    font-size:10px;
    margin-bottom:3px;
}
.mini-value {
    color:#1D2939;
    font-size:17px;
    font-weight:800;
}

.policy-row {
    padding: 10px 0;
    border-bottom:1px solid #EEF2F6;
}
.policy-row:last-child {
    border-bottom:none;
}
.policy-key {
    color:#667085;
    font-size:11px;
    margin-bottom:2px;
}
.policy-value {
    color:#1D2939;
    font-size:13px;
    font-weight:700;
    line-height:1.5;
}
.small-muted {
    color:#7C8795;
    font-size:11px;
    line-height:1.55;
}

@media (max-width: 850px) {
    .hero { padding:22px 19px; border-radius:16px; }
    .hero-title { font-size:26px; }
    .layer-flow { grid-template-columns: 1fr 1fr; }
    .mini-grid { grid-template-columns: 1fr; }
}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------
# 6. Hero
# ----------------------------------------------------------
st.markdown("""
<div class="hero">
  <div class="hero-kicker">SIFUTUO ACCESS · INTERNAL TOOL</div>
  <div class="hero-title">思福妥® 多层次保障支付模拟计算器</div>
  <div class="hero-sub">
    聚焦思福妥药品增量支付，串联基本医保、大病医保、惠民保与福享关爱，
    快速比较不同治疗周期下患者最终药品自付及日均负担。
  </div>
  <div class="hero-badges">
    <span class="hero-badge">内部参考</span>
    <span class="hero-badge">Pilot Demo</span>
    <span class="hero-badge">3 / 7 / 14 天情景</span>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="notice">
<b>使用提示：</b>
本工具只测算“选择思福妥”这一药物本身新增的药品费用与保障支付，不重建患者完整住院/ICU医保结算。
患者既往治疗费用仅用于判断大病医保年度累计门槛是否被触发。
</div>
""", unsafe_allow_html=True)

# ----------------------------------------------------------
# 7. 输入区 + 结果区
# ----------------------------------------------------------
left, right = st.columns([0.92, 1.58], gap="large")

with left:
    st.markdown('<div class="section-eyebrow">STEP 01</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">选择地区与保障</div>', unsafe_allow_html=True)

    province = st.selectbox("省份", list(REGIONS.keys()))
    city = st.selectbox("城市", REGIONS[province])

    policy = get_policy(province, city)

    st.markdown(
        f"""
        <div class="status-line">
            <span><b>{province} · {city}</b></span>
            <span class="status-pill">{policy["status"]}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if (province, city) not in POLICY_DB:
        st.warning("该城市真实政策尚未录入，当前仅使用DEMO占位参数。")

    st.caption(f'自动匹配惠民保：{policy["hmb"]["name"]}')

    participate_hmb = st.checkbox(
        f'参加 {policy["hmb"]["name"]}',
        value=True
    )

    is_preexisting = False
    if participate_hmb:
        population = st.radio(
            "惠民保人群",
            ["非既往症人群", "既往症人群"],
            horizontal=True
        )
        is_preexisting = population == "既往症人群"

    participate_care = st.checkbox(
        f'参加 {policy["care"]["name"]}',
        value=True
    )

    st.divider()

    st.markdown('<div class="section-eyebrow">STEP 02</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">大病医保累计基础</div>', unsafe_allow_html=True)

    base_mode = st.radio(
        "使用思福妥前，本年度已累计符合大病医保口径的个人负担/合规费用",
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

    st.caption("该金额仅用于判断大病医保是否进一步触发，不重复计入本次药品自付。")

    st.divider()

    st.markdown('<div class="section-eyebrow">STEP 03</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">选择支付测算周期</div>', unsafe_allow_html=True)

    selected_days = st.segmented_control(
        "周期",
        options=PRODUCT["scenarios"],
        default=7,
        format_func=lambda x: f"{x}天"
    )
    if selected_days is None:
        selected_days = 7

    current_units = PRODUCT["daily_units"] * selected_days
    current_drug_cost = PRODUCT["unit_price"] * current_units

    st.markdown(
        f"""
        <div class="mini-grid">
            <div class="mini-card">
                <div class="mini-label">单价</div>
                <div class="mini-value">{money(PRODUCT["unit_price"])}/支</div>
            </div>
            <div class="mini-card">
                <div class="mini-label">每日用量</div>
                <div class="mini-value">{PRODUCT["daily_units"]} 支</div>
            </div>
            <div class="mini-card">
                <div class="mini-label">当前药品费用</div>
                <div class="mini-value">{money(current_drug_cost)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with right:
    result = calculate_scenario(
        days=selected_days,
        province=province,
        city=city,
        prior_major_cumulative=prior_major_cumulative,
        participate_hmb=participate_hmb,
        is_preexisting=is_preexisting,
        participate_care=participate_care
    )

    st.markdown('<div class="section-eyebrow">PAYMENT PATH</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">四重保障支付路径</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="layer-flow">
          <div class="layer-card card-blue">
            <div class="layer-index">LAYER 01</div>
            <div class="layer-name">基本医保</div>
            <div class="layer-value">{money(result["基本医保支付"])}</div>
            <div class="layer-note">当前按每支固定支付 {money(policy["basic"]["fixed_pay_per_unit"])}</div>
          </div>
          <div class="layer-card card-gold">
            <div class="layer-index">LAYER 02</div>
            <div class="layer-name">大病医保</div>
            <div class="layer-value">{money(result["大病医保支付"])}</div>
            <div class="layer-note">结合此前年度累计费用计算本次增量保障</div>
          </div>
          <div class="layer-card card-purple">
            <div class="layer-index">LAYER 03</div>
            <div class="layer-name">惠民保</div>
            <div class="layer-value">{money(result["惠民保支付"])}</div>
            <div class="layer-note">{policy["hmb"]["name"]}</div>
          </div>
          <div class="layer-card card-green">
            <div class="layer-index">LAYER 04</div>
            <div class="layer-name">福享关爱</div>
            <div class="layer-value">{money(result["福享关爱支付"])}</div>
            <div class="layer-note">无免赔额；后台项目参数计算</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="final-panel">
          <div class="final-top">
            <div>
              <div class="final-label">当前 {selected_days} 天情景 · 最终思福妥药品自付</div>
              <div class="final-value">{money(result["最终药品自付"])}</div>
            </div>
            <div class="final-meta">
              <span>日均自付<br><strong>{money(result["日均药品自付"])}</strong></span>
              <span>综合保障<br><strong>{result["综合保障比例"]:.1%}</strong></span>
              <span>累计保障<br><strong>{money(result["总保障金额"])}</strong></span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 自付逐层变化
    path_df = pd.DataFrame({
        "阶段": [
            "原始药品费用",
            "基本医保后",
            "大病医保后",
            "惠民保后",
            "福享关爱后"
        ],
        "患者药品自付": [
            result["思福妥药品费用"],
            result["医保后药品自付"],
            result["大病后药品自付"],
            result["惠民保后药品自付"],
            result["最终药品自付"]
        ]
    })

    stage_order = path_df["阶段"].tolist()

    bars = alt.Chart(path_df).mark_bar(
        size=24,
        cornerRadiusEnd=5
    ).encode(
        y=alt.Y(
            "阶段:N",
            sort=stage_order,
            title=None,
            axis=alt.Axis(labelFontSize=12, labelColor="#475467")
        ),
        x=alt.X(
            "患者药品自付:Q",
            title="患者药品自付（元）",
            axis=alt.Axis(grid=True, gridColor="#EDF1F5", titleColor="#667085")
        ),
        tooltip=[
            alt.Tooltip("阶段:N"),
            alt.Tooltip("患者药品自付:Q", format=",.0f")
        ]
    )

    text = alt.Chart(path_df).mark_text(
        align="left",
        dx=6,
        fontSize=11,
        color="#475467"
    ).encode(
        y=alt.Y("阶段:N", sort=stage_order),
        x="患者药品自付:Q",
        text=alt.Text("患者药品自付:Q", format=",.0f")
    )

    st.altair_chart(
        (bars + text).properties(height=230),
        use_container_width=True
    )

# ----------------------------------------------------------
# 8. 情景对比
# ----------------------------------------------------------
st.divider()
st.markdown('<div class="section-eyebrow">SCENARIO COMPARISON</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">3 / 7 / 14 天支付情景对比</div>', unsafe_allow_html=True)

compare_rows = [
    calculate_scenario(
        days=d,
        province=province,
        city=city,
        prior_major_cumulative=prior_major_cumulative,
        participate_hmb=participate_hmb,
        is_preexisting=is_preexisting,
        participate_care=participate_care
    )
    for d in PRODUCT["scenarios"]
]
compare_df = pd.DataFrame(compare_rows)

c1, c2, c3 = st.columns(3)
for col, d in zip([c1, c2, c3], PRODUCT["scenarios"]):
    row = compare_df.loc[compare_df["支付测算周期"] == d].iloc[0]
    with col:
        st.markdown(
            f"""
            <div class="panel">
              <div class="section-eyebrow">{d} DAYS</div>
              <div style="font-size:13px;color:#667085;margin-bottom:5px;">最终药品自付</div>
              <div style="font-size:27px;font-weight:900;color:#153B63;">{money(row["最终药品自付"])}</div>
              <div style="font-size:11px;color:#7C8795;margin-top:7px;">
                日均 {money(row["日均药品自付"])}/天 · 保障 {row["综合保障比例"]:.1%}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

tab1, tab2 = st.tabs(["日均自付趋势", "详细支付明细"])

with tab1:
    trend_df = compare_df[["支付测算周期", "日均药品自付"]].copy()
    trend_df["周期"] = trend_df["支付测算周期"].astype(str) + "天"

    line = alt.Chart(trend_df).mark_line(
        point=alt.OverlayMarkDef(size=95, filled=True),
        strokeWidth=3
    ).encode(
        x=alt.X(
            "周期:N",
            sort=["3天", "7天", "14天"],
            title=None,
            axis=alt.Axis(labelFontSize=12, labelColor="#475467")
        ),
        y=alt.Y(
            "日均药品自付:Q",
            title="日均药品自付（元/天）",
            axis=alt.Axis(grid=True, gridColor="#EDF1F5", titleColor="#667085")
        ),
        tooltip=[
            "周期:N",
            alt.Tooltip("日均药品自付:Q", format=",.0f")
        ]
    )
    st.altair_chart(line.properties(height=270), use_container_width=True)

with tab2:
    show_cols = [
        "支付测算周期",
        "用药支数",
        "思福妥药品费用",
        "基本医保支付",
        "大病医保支付",
        "惠民保支付",
        "福享关爱支付",
        "最终药品自付",
        "日均药品自付",
        "综合保障比例"
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

# ----------------------------------------------------------
# 9. 政策口径
# ----------------------------------------------------------
st.divider()
st.markdown('<div class="section-eyebrow">POLICY REFERENCE</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">当前地区政策口径</div>', unsafe_allow_html=True)

with st.expander(f"{province} · {city}｜查看后台口径与核验状态", expanded=False):
    p1, p2 = st.columns(2)

    with p1:
        st.markdown(
            f"""
            <div class="policy-row">
              <div class="policy-key">基本医保</div>
              <div class="policy-value">{policy["basic"]["note"]}</div>
            </div>
            <div class="policy-row">
              <div class="policy-key">大病医保</div>
              <div class="policy-value">{policy["major"]["note"]}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with p2:
        st.markdown(
            f"""
            <div class="policy-row">
              <div class="policy-key">惠民保</div>
              <div class="policy-value">{policy["hmb"]["note"]}</div>
            </div>
            <div class="policy-row">
              <div class="policy-key">福享关爱</div>
              <div class="policy-value">{policy["care"]["note"]}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    if not policy["hmb"]["verified"] or not policy["care"]["verified"]:
        st.warning("当前惠民保/福享关爱仍含待核验参数，正式使用前需用Local及项目正式条款确认。")

# ----------------------------------------------------------
# 10. Disclaimer
# ----------------------------------------------------------
st.markdown("""
<div class="notice" style="margin-top:16px;">
<b>Disclaimer：</b>
本工具仅供内部培训、政策认知与支付路径模拟使用，不构成医保结算、保险理赔或临床用药建议。
实际支付结果可能因患者参保身份、在职/退休状态、医院等级、门诊/住院场景、特殊人群政策、
年度封顶线、实际累计费用及当地实时政策而存在差异。所有结果以当地医保部门、保险产品正式条款及实际结算为准。
</div>
""", unsafe_allow_html=True)
