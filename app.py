import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime
import pytz # 用于确保时区是中国北京时间

# --- 页面配置 ---
st.set_page_config(page_title="AI 每日量化选股看板 V1.1", layout="wide")

# --- 后端逻辑：硬核数据分析 ---

@st.cache_data(ttl=3600)
def is_trading_day():
    """判断今日是否为 A 股交易日"""
    try:
        # 强制获取中国北京时间
        tz = pytz.timezone('Asia/Shanghai')
        today_str = datetime.now(tz).strftime("%Y-%m-%d")
        
        # 获取新浪交易日历
        df = ak.tool_trade_date_hist_sina()
        # 将日历中的日期统一转为字符串格式进行精准比对
        trade_dates = [str(d)[:10] for d in df['trade_date'].tolist()]
        
        return today_str in trade_dates
    except Exception as e:
        return True # 接口偶发失效时，默认放行

@st.cache_data(ttl=1800)
def get_market_sentiment():
    """美股昨夜信号作为大盘情绪参考"""
    try:
        df_us = ak.stock_us_daily(symbol=".INX") 
        us_change = df_us['close'].pct_change().iloc[-1] * 100
        
        if us_change < -1.5:
            pos = "3成（极端防守）"
        elif us_change > 1.2:
            pos = "8成（顺势而为）"
        else:
            pos = "5成（均衡博弈）"
        return pos, us_change
    except:
        return "5成（参考缺失）", 0.0

@st.cache_data(ttl=600)
def advanced_screening():
    """小资金突围逻辑：纯量价齐升过滤（彻底规避海外IP被拦截）"""
    try:
        # 获取全 A 股实时行情 (最稳定的接口)
        df_all = ak.stock_zh_a_spot_em()
    except:
        return pd.DataFrame() # 接口异常返回空表
    
    if df_all.empty:
        return pd.DataFrame()

    # 基础排雷与类型安全转换
    df = df_all.copy()
    df['名称'] = df['名称'].astype(str)
    df['代码'] = df['代码'].astype(str)
    
    # 剔除ST、退市、次新、未盈利等标识
    df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
    # 仅保留主板(60, 00)和创业板(30)
    df = df[df['代码'].str.startswith(('60', '00', '30'))]
    
    # 强制将需要计算的列转为数值类型，防止 Pandas 报错
    for col in ['最新价', '涨跌幅', '量比', '换手率']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 剔除绝对价格过高的股票（散户友好）
    df = df[df['最新价'] < 150]

    # 核心：硬核量价筛选模型
    final_targets = df[
        (df['涨跌幅'] > 3.0) & (df['涨跌幅'] < 7.5) &
        (df['量比'] > 1.5) &
        (df['换手率'] > 4.0) & (df['换手率'] < 18.0)
    ].copy()

    if final_targets.empty:
        return pd.DataFrame()

    # 综合打分：权重向“异动放量”倾斜
    final_targets['综合得分'] = (final_targets['量比'] * 5) + (final_targets['涨跌幅'] * 2)
    
    # 整理输出并保留两位小数
    res = final_targets.sort_values(by="综合得分", ascending=False).head(3)
    res['综合得分'] = res['综合得分'].round(2)
    res['量比'] = res['量比'].round(2)
    res['换手率'] = res['换手率'].round(2)
    res['涨跌幅'] = res['涨跌幅'].round(2)
    
    return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '综合得分']]

# --- 前端展示 ---

def main():
    st.title("🏹 AI 每日量化选股 (V1.1 小资金突围版)")
    
    # 时区处理，确保显示中国时间
    tz = pytz.timezone('Asia/Shanghai')
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    
    # 1. 第一关：校验是否为交易日
    if not is_trading_day():
        st.error(f"⚠️ 今日 ({today_str}) 为 A 股非交易日，市场休市。")
        st.info("💡 系统已自动停止底层数据抓取，以防报错卡死。请在下一个交易日早盘再次访问。")
        st.stop() # 【关键断点】：遇到非交易日，立刻停止向下执行代码！
        
    st.success(f"✅ 系统运行中 | 交易日: {today_str}")

    # 2. 第二关：大盘与仓位
    col_pos, col_us = st.columns(2)
    pos_advice, us_val = get_market_sentiment()
    
    with col_pos:
        st.metric("核心仓位建议", pos_advice)
    with col_us:
        st.metric("美股昨夜波动 (S&P 500)", f"{us_val:.2f}%")

    st.divider()

    # 3. 第三关：选股结果
    st.subheader("🔥 今日主力异动高分标的 (Top 3)")
    st.caption("筛选逻辑：量比>1.5 + 换手>4% + 涨幅3%~7.5% (寻找大资金拉升前的惯性)")
    
    # 增加视觉加载提示，不再干等
    with st.spinner("正在努力拉取全市场实时数据，预计需要 5-10 秒..."):
        target_df = advanced_screening()
        
    if target_df.empty:
        st.warning("当前盘面较弱，未触发量价共振逻辑，建议空仓观望。")
    else:
        target_df.columns = ['股票代码', '名称', '当前价', '涨幅%', '量比', '换手%', '综合打分']
        st.table(target_df)

    # 4. 第四关：生存纪律
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
