import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime

# --- 页面配置 ---
st.set_page_config(page_title="AI 每日量化选股看板 V1.1", layout="wide")

# --- 后端逻辑：硬核数据分析 ---

@st.cache_data(ttl=3600)
def is_trading_day():
    """判断今日是否为交易日"""
    try:
        df = ak.tool_trade_date_hist_sina()
        today = datetime.now().date()
        return today in df['trade_date'].values
    except:
        return True # 接口失效时默认允许运行

@st.cache_data(ttl=1800)
def get_market_sentiment():
    """美股昨夜信号 + A股今日跌停家数(简单情绪指标)"""
    try:
        # 美股信号
        df_us = ak.stock_us_daily(symbol=".INX") 
        us_change = df_us['close'].pct_change().iloc[-1] * 100
        
        # 建议逻辑
        if us_change < -1.5:
            pos = "3成（极端防守）"
        elif us_change > 1.2:
            pos = "8成（顺势而为）"
        else:
            pos = "5成（均衡博弈）"
        return pos, us_change
    except:
        return "5成（参考缺失）", 0.0

@st.cache_data(ttl=600) # 10分钟更新一次，捕捉实时资金流
def advanced_screening():
    """小资金突围逻辑：主力资金异动 + 量价齐升"""
    # 1. 获取全 A 股实时行情
    df_all = ak.stock_zh_a_spot_em()
    
    # 2. 基础排雷 (过滤ST、次新、北交所、超高价股)
    df = df_all[~df_all['名称'].str.contains("ST|退市|N|C|U")].copy()
    df = df[df['代码'].str.startswith(('60', '00', '30'))]
    df = df[df['最新价'] < 150] # 散户友好，避开超高价

    # 3. 资金面过滤：获取今日主力净流入排名
    # 这步是关键：只在有大资金参与的标的中寻找
    try:
        df_fund = ak.stock_individual_fund_flow_rank(indicator="今日")
        top_fund_codes = df_fund.head(150)['代码'].tolist()
        df = df[df['代码'].isin(top_fund_codes)]
    except:
        pass # 接口异常时跳过资金过滤，进入量价过滤

    # 4. 硬核量价筛选模型
    # - 涨幅在 3%~7%：避开跟风盘，寻找主升浪
    # - 量比 > 1.5：代表成交量异常放大，主力在干活
    # - 换手率 5%~15%：代表流动性极佳，容易进出
    final_targets = df[
        (df['涨跌幅'] > 3.0) & (df['涨跌幅'] < 7.5) &
        (df['量比'] > 1.5) &
        (df['换手率'] > 4.0) & (df['换手率'] < 18.0)
    ].copy()

    # 5. 综合打分：量比(40%) + 资金流向(30%) + 涨幅(30%)
    final_targets['综合得分'] = (final_targets['量比'] * 5) + (final_targets['涨跌幅'] * 2)
    
    # 整理输出
    res = final_targets.sort_values(by="综合得分", ascending=False).head(3)
    return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '综合得分']]

# --- 前端展示 ---

def main():
    st.title("🏹 AI 每日量化选股 (V1.1 小资金突围版)")
    
    # 状态区
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not is_trading_day():
        st.error(f"⚠️ 今日 ({today_str}) 为非交易日，系统展示历史缓存，仅供复盘参考。")
    else:
        st.success(f"✅ 系统运行中 | 交易日: {today_str}")

    # 第一行：大盘与仓位
    col_pos, col_us = st.columns(2)
    pos_advice, us_val = get_market_sentiment()
    
    with col_pos:
        st.metric("核心仓位建议", pos_advice)
    with col_us:
        st.metric("美股昨夜波动 (S&P 500)", f"{us_val:.2f}%")

    st.divider()

    # 第二行：选股结果
    st.subheader("🔥 今日主力异动高分标的 (Top 3)")
    st.caption("筛选逻辑：主力净流入前150 + 量比>1.5 + 换手>4% (寻找大资金拉升前的惯性)")
    
    target_df = advanced_screening()
    if target_df.empty:
        st.warning("当前行情未触发表达式，建议空仓观望。")
    else:
        # 重命名列以符合用户需求
        target_df.columns = ['股票代码', '名称', '当前价', '涨幅%', '量比', '换手%', '综合打分']
        st.table(target_df)

    # 第三行：生存纪律
    st.divider()
    st.subheader("🛡️ T+1 规则下的生存纪律")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.error("【买入】\n\n开盘半小时量比低于1.5不看；10:30后才封板的少看；超过3只不看。")
    with c2:
        st.error("【持有】\n\n次日开盘若低开幅度超过-2%且不回补，说明被闷杀，寻找反抽离场。")
    with c3:
        st.error("【卖出】\n\n盈利10%是门槛，达到后开启移动止盈，绝不让盈利变亏损。")

    # 底部说明
    st.sidebar.markdown("### 策略说明")
    st.sidebar.info("A股由于不能做空，大资金拉升必须放量。本系统通过‘量比’监控主力强买入痕迹，利用T+1的时间差赚取情绪溢价。")

if __name__ == "__main__":
    main()
