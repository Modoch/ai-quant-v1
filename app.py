import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time
import pytz 

# --- 页面配置 ---
st.set_page_config(page_title="AI 每日量化选股 (V1.6 复刻版)", layout="wide")

# ==========================================
# 后端逻辑 (数据处理)
# ==========================================

@st.cache_data(ttl=3600)
def is_trading_day():
    """判断今日是否为 A 股交易日"""
    try:
        tz = pytz.timezone('Asia/Shanghai')
        today_str = datetime.now(tz).strftime("%Y-%m-%d")
        df = ak.tool_trade_date_hist_sina()
        trade_dates = [str(d)[:10] for d in df['trade_date'].tolist()]
        return today_str in trade_dates
    except:
        return True 

@st.cache_data(ttl=600)
def get_morning_news():
    """
    获取宏观新闻，并生成搜索链接
    """
    noise_keywords = ["资金", "净流入", "净流出", "融资", "融券", "大宗交易", "主力", "收盘", "开盘", "指数"]
    
    try:
        # 优先用东方财富（宏观面更全）
        df = ak.stock_news_em(symbol="000001")
        if df.empty:
            df = ak.stock_telegraph_cls() # 备用财联社
            df = df.rename(columns={'title': '新闻标题', 'publish_time': '发布时间'})

        if not df.empty:
            df = df.rename(columns={'发布时间': '时间', '新闻标题': '标题'})
            
            # 去噪
            pattern = '|'.join(noise_keywords)
            df = df[~df['标题'].str.contains(pattern, na=False)]
            
            return df[['时间', '标题']].head(15)
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_market_sentiment():
    """美股与仓位"""
    try:
        df_us = ak.stock_us_daily(symbol=".INX") 
        us_change = df_us['close'].pct_change().iloc[-1] * 100
        if us_change < -1.5: return "3成 (防守)", us_change
        elif us_change > 1.0: return "8成 (进攻)", us_change
        else: return "5成 (平衡)", us_change
    except:
        return "5成 (平衡)", 0.0

@st.cache_data(ttl=600)
def advanced_screening():
    """
    V1.1 核心策略复刻
    筛选逻辑：量比>1.5 + 换手>3% + 涨幅3%~7%
    """
    try:
        df_all = ak.stock_zh_a_spot_em()
    except: return pd.DataFrame()
    
    if df_all.empty: return pd.DataFrame()

    df = df_all.copy()
    
    # 1. 基础清洗
    df['名称'] = df['名称'].astype(str)
    df['代码'] = df['代码'].astype(str)
    df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
    df = df[df['代码'].str.startswith(('60', '00', '30'))]
    
    # 2. 数值转换
    for col in ['最新价', '涨跌幅', '量比', '换手率']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 3. 价格过滤
    df = df[df['最新价'] < 100]

    # 4. 核心策略 (V1.1 参数)
    # 涨幅 3% ~ 7% (严格卡死，不追高)
    # 量比 > 1.5
    # 换手率 > 3% (保证流动性)
    final_targets = df[
        (df['涨跌幅'] >= 3.0) & (df['涨跌幅'] <= 7.0) &
        (df['量比'] > 1.5) &
        (df['换手率'] > 3.0) & (df['换手率'] < 15.0)
    ].copy()

    if final_targets.empty: return pd.DataFrame()

    # 5. 综合打分
    final_targets['综合得分'] = (final_targets['量比'] * 5) + (final_targets['涨跌幅'] * 2)
    res = final_targets.sort_values(by="综合得分", ascending=False).head(3)
    
    # 6. 格式化数据 (保留2位小数)
    res['综合得分'] = res['综合得分'].round(2)
    res['量比'] = res['量比'].round(2)
    res['换手率'] = res['换手率'].round(2)
    res['涨跌幅'] = res['涨跌幅'].round(2)
    
    # 【关键】必须返回所有V1.1包含的列
    return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '综合得分']]

# ==========================================
# 前端展示 (V1.1 风格复刻)
# ==========================================

def main():
    tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(tz)
    today_str = now_time.strftime("%Y-%m-%d")
    
    # --- 侧边栏：新闻 ---
    with st.sidebar:
        st.header("📖 策略说明")
        st.info("核心逻辑：通过‘量比’监控主力强买入痕迹，利用T+1的时间差赚取情绪溢价。")
        st.divider()
        
        st.subheader("🗞️ 7x24 宏观快讯")
        st.caption("点击标题可搜索详情")
        
        with st.spinner("刷新新闻..."):
            news_df = get_morning_news()
        
        if not news_df.empty:
            for index, row in news_df.iterrows():
                time_str = str(row['时间'])[-8:]
                title = row['标题']
                # 生成百度搜索链接
                search_url = f"https://www.baidu.com/s?wd={title}"
                # 使用 Markdown 渲染可点击的链接
                st.markdown(f"⏰ {time_str} | [{title}]({search_url})")
                st.write("---") # 分割线
        else:
            st.warning("暂无重要消息")

    # --- 主界面 ---
    
    st.title("🏹 AI 每日量化选股 (V1.6 复刻版)")
    
    if is_trading_day():
        st.success(f"✅ 系统运行中 | 交易日: {today_str} | {now_time.strftime('%H:%M')}")
    else:
        st.error(f"⚠️ 休市中 | {today_str}")
        st.stop() 

    # 1. 仓位建议 (大号字体)
    pos, us_chg = get_market_sentiment()
    st.metric("核心仓位建议", pos, delta=f"美股: {us_chg:.2f}%")
    
    st.write("") 

    # 2. 核心表格 (V1.1 布局)
    st.subheader("🔥 今日主力异动高分标的 (Top 3)")
    st.caption("筛选逻辑：量比>1.5 + 换手>3% + 涨幅3%~7% (寻找大资金拉升前的惯性)")

    # 没开盘时的保护
    market_open_time = time(9, 25) 
    if now_time.time() < market_open_time:
        st.info("⏳ 还没开盘 (09:25后解锁)。请先阅读左侧新闻。")
    else:
        with st.spinner("🚀 全市场扫描中..."):
            df_result = advanced_screening()
        
        if df_result.empty:
            st.warning("今日无符合模型标的，空仓观望。")
        else:
            # 制作代码跳转链接
            def make_link(code):
                market_prefix = "sh" if code.startswith("6") else "sz"
                link = f"http://quote.eastmoney.com/{market_prefix}{code}.html"
                return f'<a target="_blank" href="{link}">{code}</a>'

            df_show = df_result.copy()
            df_show['代码'] = df_show['代码'].apply(make_link)
            
            # 【关键修正】重命名列，确保界面显示和V1.1完全一致
            df_show.columns = ['股票代码', '名称', '当前价', '涨幅%', '量比', '换手%', '综合打分']
            
            # 渲染表格
            st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.caption("💡 提示：点击【股票代码】可跳转东方财富查看详细概念与K线。")

    st.divider()

    # 3. 底部红框纪律 (V1.1 样式)
    st.subheader("🛡️ T+1 规则下的生存纪律")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.error("【买入】\n\n开盘半小时量比低于1.5不看；10:30后才封板的少看；超过3只不看。")
    with c2:
        st.error("【持有】\n\n次日开盘若低开幅度超过-2%且不回补，说明被闷杀，寻找反抽离场。")
    with c3:
        st.error("【卖出】\n\n盈利10%是门槛，达到后开启移动止盈，绝不让盈利变亏损。")

if __name__ == "__main__":
    main()
