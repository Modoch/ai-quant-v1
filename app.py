import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time
import pytz 

# --- 页面配置 (宽屏模式) ---
st.set_page_config(page_title="AI 量化选股看板 (V1.4 终极融合版)", layout="wide")

# ==========================================
# 核心后端逻辑 (保留 V1.3.1 的双源热备与防卡死)
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
        return True # 接口挂了默认允许运行，防止误杀

@st.cache_data(ttl=600)
def get_morning_news():
    """【双源保险】获取财经快讯，优先财联社，失败则切东方财富"""
    # 通道 1：财联社
    try:
        df = ak.stock_telegraph_cls()
        if not df.empty:
            df = df.rename(columns={'title': '标题', 'content': '内容', 'publish_time': '时间'})
            return df[['时间', '标题', '内容']].head(15)
    except: pass
    
    # 通道 2：东方财富
    try:
        df_em = ak.stock_news_em(symbol="000001")
        if not df_em.empty:
            df_em = df_em.rename(columns={'发布时间': '时间', '新闻标题': '标题', '新闻内容': '内容'})
            if '内容' not in df_em.columns: df_em['内容'] = df_em['标题']
            return df_em[['时间', '标题', '内容']].head(15)
    except: pass

    return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_market_sentiment():
    """美股信号"""
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
    """量价共振选股逻辑"""
    try:
        df_all = ak.stock_zh_a_spot_em()
    except: return pd.DataFrame()
    
    if df_all.empty: return pd.DataFrame()

    df = df_all.copy()
    # 数据清洗
    df['名称'] = df['名称'].astype(str)
    df['代码'] = df['代码'].astype(str)
    df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
    df = df[df['代码'].str.startswith(('60', '00', '30'))]
    
    for col in ['最新价', '涨跌幅', '量比', '换手率']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 价格过滤
    df = df[df['最新价'] < 100]

    # 核心筛选：量价齐升
    final_targets = df[
        (df['涨跌幅'] > 3.0) & (df['涨跌幅'] < 8.0) &
        (df['量比'] > 1.8) &
        (df['换手率'] > 3.0) & (df['换手率'] < 15.0)
    ].copy()

    if final_targets.empty: return pd.DataFrame()

    # 打分
    final_targets['综合得分'] = (final_targets['量比'] * 5) + (final_targets['涨跌幅'] * 2)
    res = final_targets.sort_values(by="综合得分", ascending=False).head(3)
    
    # 【新增】获取行业概念
    def get_industry(code):
        try:
            info = ak.stock_individual_info_em(symbol=code)
            return info.loc[info['item'] == '行业板块', 'value'].values[0]
        except: return "未知"
    
    res = res.copy()
    res['行业/概念'] = res['代码'].apply(get_industry)
    
    # 格式化
    res['综合得分'] = res['综合得分'].round(1)
    res['量比'] = res['量比'].round(2)
    
    # 调整列顺序，把行业概念放在显眼位置
    return res[['代码', '名称', '行业/概念', '最新价', '涨跌幅', '量比', '综合得分']]

# ==========================================
# 前端展示 (V1.1 布局 + 侧边栏新闻)
# ==========================================

def main():
    # 获取北京时间
    tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(tz)
    today_str = now_time.strftime("%Y-%m-%d")
    
    # --- 侧边栏：新闻与策略 ---
    with st.sidebar:
        st.header("📖 策略说明")
        st.info("""
        **核心逻辑：**
        捕捉主力大资金在盘中留下的“痕迹”。
        
        **筛选标准：**
        1. **量比 > 1.8**：资金进场急切。
        2. **涨幅 3%~8%**：主升浪启动，非鱼尾。
        3. **T+1 纪律**：次日不强直接走。
        """)
        
        st.divider()
        
        st.header("🗞️ 7x24 财经快讯")
        st.caption("双源热备：财联社/东方财富")
        
        # 加载新闻
        with st.spinner("正在刷新消息..."):
            news_df = get_morning_news()
        
        if not news_df.empty:
            for index, row in news_df.iterrows():
                title = str(row.get('标题', '无标题'))
                time_str = str(row.get('时间', ''))[-8:] # 只取时分秒
                # 侧边栏用折叠框，节省空间
                with st.expander(f"⏰ {time_str} | {title[:12]}..."):
                    st.write(f"**{title}**")
                    st.caption(row.get('内容', title))
        else:
            st.warning("暂无最新快讯")

    # --- 主界面：回归 V1.1 经典布局 ---
    
    st.title("🏹 AI 每日量化选股 (V1.4 融合版)")
    
    # 状态条
    if is_trading_day():
        st.success(f"✅ 系统运行中 | 交易日: {today_str} | 北京时间: {now_time.strftime('%H:%M')}")
    else:
        st.error(f"⚠️ 休市中 | 日期: {today_str} (A股非交易日)")
        st.stop() # 休市则停止渲染右侧内容，但侧边栏新闻依然可见！

    st.divider()

    # 1. 核心大数字 (V1.1 风格)
    pos, us_chg = get_market_sentiment()
    
    c1, c2 = st.columns(2)
    with c1:
        st.metric("核心仓位建议", pos, delta_color="normal")
    with c2:
        st.metric("美股昨夜波动 (S&P 500)", f"{us_chg:.2f}%", delta=f"{us_chg:.2f}%")

    st.write("") # 留白
    st.write("") 

    # 2. 核心选股表格
    st.subheader("🔥 今日主力异动高分标的 (Top 3)")
    st.caption("筛选逻辑：量比>1.8 + 换手>3% + 涨幅3%~8% (寻找大资金拉升前的惯性)")

    # 开盘时间锁
    market_open_time = time(9, 25) 
    if now_time.time() < market_open_time:
        st.info("⏳ 还没开盘 (09:25后自动解锁)。请先阅读左侧【财经快讯】寻找今日风口。")
    else:
        with st.spinner("🚀 AI 正在全市场扫描量价异动..."):
            df_result = advanced_screening()
        
        if df_result.empty:
            st.warning("当前盘面较弱，未触发【量价共振】模型，建议空仓观望。")
        else:
            # 制作超链接表格
            def make_link(code):
                market_prefix = "sh" if code.startswith("6") else "sz"
                link = f"http://quote.eastmoney.com/{market_prefix}{code}.html"
                return f'<a target="_blank" href="{link}">{code}</a>'

            df_show = df_result.copy()
            df_show['代码'] = df_show['代码'].apply(make_link)
            
            # 渲染 HTML 表格 (保持 V1.1 的整洁感，但支持点击)
            st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)

    st.divider()

    # 3. 底部生存纪律 (V1.1 经典红框)
    st.subheader("🛡️ T+1 规则下的生存纪律")
    
    r1, r2, r3 = st.columns(3)
    with r1:
        st.error("【买入】\n\n开盘半小时量比低于1.5不看；10:30后才封板的少看；超过3只不看。")
    with r2:
        st.error("【持有】\n\n次日开盘若低开幅度超过-2%且不回补，说明被闷杀，寻找反抽离场。")
    with r3:
        st.error("【卖出】\n\n盈利10%是门槛，达到后开启移动止盈，绝不让盈利变亏损。")

if __name__ == "__main__":
    main()
