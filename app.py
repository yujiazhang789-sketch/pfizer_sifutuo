import streamlit as st
import pandas as pd
import altair as alt

# ==========================================================
# 思福妥® 四重保障模拟支付计算器 - v6
# UI参考：xacduro-insurance.netlify.app 的模块化、卡片化、内部工具呈现方式
# 逻辑基础：2026-09 最新会议口径
#
# 重要：
# - 本版聚焦“思福妥药品本身”的增量支付路径，不重建患者完整住院结算。
# - 北京基础医保固定支付金额、大病医保阶梯按当前会议口径录入。
# - 惠民保/福享关爱仍有待Local/项目正式规则确认的参数，页面会清晰标记。
# ==========================================================

st.set_page_config(
    page_title="思福妥® 四重保障模拟支付计算器",
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
# 6. 新需求辅助函数 + 补充样式
# ----------------------------------------------------------
def verification_label(flag):
    return "已核验" if flag else "待核验"


def build_source_table(policy):
    return pd.DataFrame([
        {
            "保障层级": "基本医保",
            "数据来源": "中央职场",
            "当前录入口径": f'每支固定支付 {money(policy["basic"]["fixed_pay_per_unit"])}',
            "核验状态": verification_label(policy["basic"]["verified"]),
        },
        {
            "保障层级": "大病医保",
            "数据来源": "Local MA给到",
            "当前录入口径": (
                f'起付线 {money(policy["major"]["deductible"])}；'
                f'至 {money(policy["major"]["tier1_upper"])} 按 {policy["major"]["tier1_rate"]:.0%}；'
                f'以上按 {policy["major"]["tier2_rate"]:.0%}'
            ),
            "核验状态": verification_label(policy["major"]["verified"]),
        },
        {
            "保障层级": "惠民保",
            "数据来源": "同步政策信息",
            "当前录入口径": f'{policy["hmb"]["name"]}｜{policy["hmb"]["scope"]}',
            "核验状态": verification_label(policy["hmb"]["verified"]),
        },
        {
            "保障层级": "福享关爱",
            "数据来源": "项目规则",
            "当前录入口径": "无免赔额；按当前后台项目参数测算",
            "核验状态": verification_label(policy["care"]["verified"]),
        },
    ])


def get_reductions(result):
    """用相邻阶段的差值计算每层实际减免，避免重复累计。"""
    return {
        "基本医保": max(result["思福妥药品费用"] - result["医保后药品自付"], 0.0),
        "大病医保": max(result["医保后药品自付"] - result["大病后药品自付"], 0.0),
        "惠民保": max(result["大病后药品自付"] - result["惠民保后药品自付"], 0.0),
        "福享关爱": max(result["惠民保后药品自付"] - result["最终药品自付"], 0.0),
    }


def cumulative_reduction(result):
    """累计减免 = 原始药品费用 - 最终支付。"""
    return max(result["思福妥药品费用"] - result["最终药品自付"], 0.0)


def build_daily_waterfall(result):
    """构建当前治疗周期下，不同支付情景的日均治疗费用瀑布图。"""
    days = max(int(result["支付测算周期"]), 1)
    reductions = get_reductions(result)
    original_daily = result["思福妥药品费用"] / days
    current = original_daily

    rows = [{
        "阶段": "原始日均",
        "类型": "起始",
        "下界": 0.0,
        "上界": original_daily,
        "金额": original_daily,
        "标签": money(original_daily),
    }]

    for name in ["基本医保", "大病医保", "惠民保", "福享关爱"]:
        reduction_daily = reductions[name] / days
        next_value = max(current - reduction_daily, 0.0)
        rows.append({
            "阶段": name,
            "类型": "减免",
            "下界": min(current, next_value),
            "上界": max(current, next_value),
            "金额": reduction_daily,
            "标签": f'-{money(reduction_daily)}',
        })
        current = next_value

    final_daily = result["最终药品自付"] / days
    rows.append({
        "阶段": "最终日均",
        "类型": "最终",
        "下界": 0.0,
        "上界": final_daily,
        "金额": final_daily,
        "标签": money(final_daily),
    })
    return pd.DataFrame(rows)


st.markdown("""
<style>
.path-head {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:10px;
    flex-wrap:wrap;
    margin-bottom:8px;
}
.units-pill {
    display:inline-flex;
    padding:6px 10px;
    border-radius:999px;
    background:#F2F4F7;
    color:#475467;
    font-size:11px;
    font-weight:750;
}
.layer-caption {
    font-size:10px;
    opacity:.66;
    margin-bottom:6px;
}
.result-panel {
    background:linear-gradient(135deg,#F8FBFF 0%,#EDF6FF 100%);
    border:1px solid #D6E9FA;
    border-radius:16px;
    padding:18px 20px;
    margin:8px 0 16px;
}
.result-grid {
    display:grid;
    grid-template-columns:1.35fr 1fr 1fr;
    gap:12px;
}
.metric-primary, .metric-secondary {
    border-radius:13px;
    padding:14px 15px;
}
.metric-primary {
    background:#153B63;
    color:white;
}
.metric-secondary {
    background:white;
    border:1px solid #DCE7F1;
    color:#1D2939;
}
.metric-label {
    font-size:11px;
    opacity:.72;
    margin-bottom:5px;
}
.metric-primary .metric-label {
    color:rgba(255,255,255,.72);
}
.metric-value-primary {
    font-size:34px;
    font-weight:900;
    line-height:1.08;
}
.metric-value {
    font-size:25px;
    font-weight:850;
    color:#153B63;
}
.metric-note {
    font-size:10px;
    opacity:.67;
    margin-top:5px;
    line-height:1.45;
}
.scenario-card {
    border:1px solid #E6ECF2;
    background:white;
    border-radius:14px;
    padding:13px 14px;
    min-height:118px;
}
.scenario-days {
    font-size:11px;
    color:#98A2B3;
    font-weight:800;
    letter-spacing:.08em;
}
.scenario-daily {
    font-size:26px;
    color:#153B63;
    font-weight:900;
    margin:4px 0 6px;
}
.scenario-meta {
    font-size:11px;
    color:#667085;
    line-height:1.6;
}
@media(max-width:850px) {
    .result-grid { grid-template-columns:1fr; }
}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------
# 7. Hero
# ----------------------------------------------------------
st.markdown("""
<div class="hero">
  <div class="hero-kicker">SIFUTUO ACCESS · FOUR-LAYER SUPPORT</div>
  <div class="hero-title">思福妥® 四重保障模拟支付计算器</div>
  <div class="hero-sub">
    聚焦“思福妥”四重保障——<b>基本医保 + 大病医保 + 惠民保 + 福享关爱</b>。<br>
    本模型希望打破“信息茧房”，帮助临床医生和患者全面理解四重保障政策叠加后，
    患者的真实支付情况，及不同治疗周期患者实际自付成本变化。
  </div>
  <div class="hero-badges">
    <span class="hero-badge">四重保障</span>
    <span class="hero-badge">Pilot</span>
    <span class="hero-badge">3 / 7 / 14 天情景</span>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="notice">
<b>免责声明：</b>
本工具仅模拟测算在四重保障支付下“思福妥”涉及的自付费用，患者真实治疗费用以医院实际结算为准。
目前仅呈现个别城市的Pilot，后续会持续更新。
</div>
""", unsafe_allow_html=True)

# ----------------------------------------------------------
# 8. 当前Pilot数据：先表格呈现
# ----------------------------------------------------------
st.markdown('<div class="section-eyebrow">PILOT DATA</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">当前 Pilot 数据</div>', unsafe_allow_html=True)

pilot_left, pilot_right = st.columns([0.35, 0.65], gap="large")

with pilot_left:
    province = st.selectbox("省份", list(REGIONS.keys()))
    city = st.selectbox("城市", REGIONS[province])
    policy = get_policy(province, city)

    st.markdown(
        f'<div class="status-line"><span><b>{province} · {city}</b></span>'
        f'<span class="status-pill">{policy["status"]}</span></div>',
        unsafe_allow_html=True
    )

    if (province, city) not in POLICY_DB:
        st.warning("该城市真实政策尚未录入，当前仅使用DEMO占位参数。")

with pilot_right:
    source_df = build_source_table(policy)
    st.dataframe(
        source_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "保障层级": st.column_config.TextColumn("保障层级", width="small"),
            "数据来源": st.column_config.TextColumn("数据来源", width="small"),
            "当前录入口径": st.column_config.TextColumn("当前录入口径", width="large"),
            "核验状态": st.column_config.TextColumn("核验状态", width="small"),
        }
    )

# ----------------------------------------------------------
# 9. 输入 + 四重保障结果
# ----------------------------------------------------------
st.divider()
left, right = st.columns([0.86, 1.64], gap="large")

with left:
    st.markdown('<div class="section-eyebrow">STEP 01</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">选择保障场景</div>', unsafe_allow_html=True)
    st.caption(f'惠民保：{policy["hmb"]["name"]}')

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

    st.caption("该金额仅用于判断本次思福妥费用是否进一步触发大病医保，不重复计入本次药品支付。")

    st.divider()
    st.markdown('<div class="section-eyebrow">STEP 03</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">选择治疗周期</div>', unsafe_allow_html=True)

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

    m1, m2 = st.columns(2)
    m1.metric("当前支数", f"{current_units} 支")
    m2.metric("原始药品费用", money(current_drug_cost))
    st.caption(
        f'当前测算：{money(PRODUCT["unit_price"])}/支 × '
        f'{PRODUCT["daily_units"]}支/天 × {selected_days}天'
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

    reductions = get_reductions(result)
    total_reduction = cumulative_reduction(result)

    st.markdown(
        f'<div class="path-head">'
        f'<div><div class="section-eyebrow">FOUR-LAYER PATH</div>'
        f'<div class="section-title" style="margin-bottom:0;">四重保障路径下预计可减免费用</div></div>'
        f'<div class="units-pill">{selected_days}天 · 共 {result["用药支数"]} 支</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        f'''<div class="layer-flow">
          <div class="layer-card card-blue">
            <div class="layer-index">LAYER 01</div>
            <div class="layer-name">基本医保</div>
            <div class="layer-caption">预计可减免费用</div>
            <div class="layer-value">{money(reductions["基本医保"])}</div>
            <div class="layer-note">当前按每支 {money(policy["basic"]["fixed_pay_per_unit"])} 测算</div>
          </div>
          <div class="layer-card card-gold">
            <div class="layer-index">LAYER 02</div>
            <div class="layer-name">大病医保</div>
            <div class="layer-caption">预计可减免费用</div>
            <div class="layer-value">{money(reductions["大病医保"])}</div>
            <div class="layer-note">结合年度累计基础计算本次增量减免</div>
          </div>
          <div class="layer-card card-purple">
            <div class="layer-index">LAYER 03</div>
            <div class="layer-name">惠民保</div>
            <div class="layer-caption">预计可减免费用</div>
            <div class="layer-value">{money(reductions["惠民保"])}</div>
            <div class="layer-note">{policy["hmb"]["name"]}</div>
          </div>
          <div class="layer-card card-green">
            <div class="layer-index">LAYER 04</div>
            <div class="layer-name">福享关爱</div>
            <div class="layer-caption">预计可减免费用</div>
            <div class="layer-value">{money(reductions["福享关爱"])}</div>
            <div class="layer-note">无免赔额；按后台项目参数测算</div>
          </div>
        </div>''',
        unsafe_allow_html=True
    )

    daily_pay = result["日均药品自付"]
    final_pay = result["最终药品自付"]

    st.markdown(
        f'''<div class="result-panel"><div class="result-grid">
          <div class="metric-primary">
            <div class="metric-label">日均支付</div>
            <div class="metric-value-primary">{money(daily_pay)}</div>
            <div class="metric-note">{selected_days}天治疗周期 · 平均每天患者支付</div>
          </div>
          <div class="metric-secondary">
            <div class="metric-label">最终支付</div>
            <div class="metric-value">{money(final_pay)}</div>
            <div class="metric-note">四重保障叠加后的患者药品支付</div>
          </div>
          <div class="metric-secondary">
            <div class="metric-label">累计减免</div>
            <div class="metric-value">{money(total_reduction)}</div>
            <div class="metric-note">四层预计减免费用合计</div>
          </div>
        </div></div>''',
        unsafe_allow_html=True
    )

# ----------------------------------------------------------
# 10. 日均治疗费用瀑布图
# ----------------------------------------------------------
st.divider()
st.markdown('<div class="section-eyebrow">DAILY PAYMENT WATERFALL</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">不同支付情景下日均治疗费用对比</div>', unsafe_allow_html=True)

waterfall_df = build_daily_waterfall(result)
waterfall_order = ["原始日均", "基本医保", "大病医保", "惠民保", "福享关爱", "最终日均"]

wf_bars = alt.Chart(waterfall_df).mark_bar(
    size=46,
    cornerRadiusTopLeft=4,
    cornerRadiusTopRight=4
).encode(
    x=alt.X(
        "阶段:N",
        sort=waterfall_order,
        title=None,
        axis=alt.Axis(labelAngle=0, labelFontSize=12, labelColor="#475467")
    ),
    y=alt.Y(
        "下界:Q",
        title="日均患者支付（元/天）",
        axis=alt.Axis(grid=True, gridColor="#EDF1F5", titleColor="#667085")
    ),
    y2="上界:Q",
    color=alt.Color(
        "类型:N",
        scale=alt.Scale(
            domain=["起始", "减免", "最终"],
            range=["#8DA9C4", "#6E8FB2", "#153B63"]
        ),
        legend=None
    ),
    tooltip=[
        alt.Tooltip("阶段:N"),
        alt.Tooltip("金额:Q", title="金额", format=",.0f"),
        alt.Tooltip("类型:N")
    ]
)

wf_labels = alt.Chart(waterfall_df).mark_text(
    dy=-9,
    fontSize=11,
    fontWeight="bold",
    color="#475467"
).encode(
    x=alt.X("阶段:N", sort=waterfall_order),
    y=alt.Y("上界:Q"),
    text="标签:N"
)

st.altair_chart(
    (wf_bars + wf_labels).properties(height=330),
    use_container_width=True
)

st.caption("从原始日均费用开始，依次扣除四层预计减免，得到最终日均支付。")

# ----------------------------------------------------------
# 11. 3 / 7 / 14天支付情景：只保留核心数据
# ----------------------------------------------------------
st.divider()
st.markdown('<div class="section-eyebrow">SCENARIO COMPARISON</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">3 / 7 / 14 天支付情景</div>', unsafe_allow_html=True)

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

scenario_cols = st.columns(3)
for col, d in zip(scenario_cols, PRODUCT["scenarios"]):
    row = compare_df.loc[compare_df["支付测算周期"] == d].iloc[0]
    reduction = max(row["思福妥药品费用"] - row["最终药品自付"], 0.0)
    with col:
        st.markdown(
            f'''<div class="scenario-card">
              <div class="scenario-days">{d} DAYS · {int(row["用药支数"])} 支</div>
              <div style="font-size:11px;color:#667085;margin-top:5px;">日均支付</div>
              <div class="scenario-daily">{money(row["日均药品自付"])}/天</div>
              <div class="scenario-meta">
                最终支付：{money(row["最终药品自付"])}<br>
                累计减免：{money(reduction)}
              </div>
            </div>''',
            unsafe_allow_html=True
        )

summary_df = pd.DataFrame([
    {
        "治疗周期（天）": int(row["支付测算周期"]),
        "支数": int(row["用药支数"]),
        "原始药品费用": row["思福妥药品费用"],
        "最终支付": row["最终药品自付"],
        "日均支付": row["日均药品自付"],
        "累计减免": max(row["思福妥药品费用"] - row["最终药品自付"], 0.0),
    }
    for _, row in compare_df.iterrows()
])

st.dataframe(
    summary_df.style.format({
        "原始药品费用": "¥{:,.0f}",
        "最终支付": "¥{:,.0f}",
        "日均支付": "¥{:,.0f}",
        "累计减免": "¥{:,.0f}",
    }),
    use_container_width=True,
    hide_index=True
)

# ----------------------------------------------------------
# 12. 政策说明
# ----------------------------------------------------------
with st.expander(f"{province} · {city}｜查看当前录入政策说明", expanded=False):
    st.markdown(f"**基本医保｜中央职场**  \n{policy['basic']['note']}")
    st.markdown(f"**大病医保｜Local MA给到**  \n{policy['major']['note']}")
    st.markdown(f"**惠民保｜同步政策信息**  \n{policy['hmb']['note']}")
    st.markdown(f"**福享关爱｜项目规则**  \n{policy['care']['note']}")

    if not (
        policy["basic"]["verified"]
        and policy["major"]["verified"]
        and policy["hmb"]["verified"]
        and policy["care"]["verified"]
    ):
        st.warning("部分参数仍处于待核验状态，正式使用前需完成政策/项目口径确认。")

# ----------------------------------------------------------
# 13. 工作可视化
# ----------------------------------------------------------
st.divider()
st.markdown('<div class="section-eyebrow">WORK VISUALIZATION</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">工作可视化</div>', unsafe_allow_html=True)

work_df = pd.DataFrame([
    {"工作项": "思福妥模拟计算器", "当前可视化": "四重保障支付测算 / 3·7·14天情景"},
    {"工作项": "双坦CHI PAP", "当前可视化": "项目名称已纳入；具体指标待后续接入"},
    {"工作项": "2026思福妥VBP集采-财务影响分析", "当前可视化": "项目名称已纳入；具体指标待后续接入"},
])

st.dataframe(work_df, use_container_width=True, hide_index=True)

# ----------------------------------------------------------
# 14. Disclaimer
# ----------------------------------------------------------
st.markdown("""
<div class="notice" style="margin-top:16px;">
<b>免责声明：</b>
本工具仅模拟测算在四重保障支付下“思福妥”涉及的自付费用，患者真实治疗费用以医院实际结算为准。
目前仅呈现个别城市的Pilot，后续会持续更新。
</div>
""", unsafe_allow_html=True)
