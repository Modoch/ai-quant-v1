import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time
import pytz 

# --- 页面配置 ---
st.set_page_config(page_title="AI 投资参谋 V1.3 (早盘新闻版)", layout="wide")

# --- 核心功能函数 ---

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
    """【V1.3新增】获取财联社/东财的最新财经快讯"""
    try:
        # 获取财联社电报，这是A股最核心的消息源
        df = ak.stock_telegraph_cls()
        # 只需要最新的 15 条
        df = df.head(15)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_market_sentiment():
    """美股昨夜信号 + A股大盘情绪"""
    try:
        df_us = ak.stock_us_daily(symbol=".INX") 
        us_change = df_us['close'].pct_change().iloc[-1] * 100
        if us_change < -1.5: return "3成（防守）", us_change
        elif us_change > 1.0: return "8成（进攻）", us_change
        else: return "5成（平衡）", us_change
    except:
        return "5成（平衡）", 0.0

@st.cache_data(ttl=600)
def advanced_screening():
    """量价共振选股逻辑"""
    try:
        df_all = ak.stock_zh_a_spot_em()
    except:
        return pd.DataFrame()
    
    if df_all.empty: return pd.DataFrame()

    df = df_all.copy()
    df['名称'] = df['名称'].astype(str)
    df['代码'] = df['代码'].astype(str)
    
    # 排雷
    df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
    df = df[df['代码'].str.startswith(('60', '00', '30'))]
    
    # 转换数值 & 价格过滤
    for col in ['最新价', '涨跌幅', '量比', '换手率']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df[df['最新价'] < 100]

    # 核心筛选：量价齐升 (V1.2逻辑保持不变)
    final_targets = df[
        (df['涨跌幅'] > 3.0) & (df['涨跌幅'] < 8.0) &
        (df['量比'] > 1.8) &
        (df['换手率'] > 3.0) & (df['换手率'] < 15.0)
    ].copy()

    if final_targets.empty: return pd.DataFrame()

    # 打分排序
    final_targets['综合得分'] = (final_targets['量比'] * 5) + (final_targets['涨跌幅'] * 2)
    res = final_targets.sort_values(by="综合得分", ascending=False).head(3)
    
    # 获取行业
    def get_industry(code):
        try:
            info = ak.stock_individual_info_em(symbol=code)
            return info.loc[info['item'] == '行业板块', 'value'].values[0]
        except: return "未知"
    
    res['所属行业'] = res['代码'].apply(get_industry)
    
    # 格式化
    res['综合得分'] = res['综合得分'].round(1)
    res['量比'] = res['量比'].round(2)
    
    return res[['代码', '名称', '所属行业', '最新价', '涨跌幅', '量比', '综合得分']]

# --- 辅助显示函数 ---

def highlight_keywords(text):
    """给重要新闻加红加粗"""
    keywords = ["中央", "国务院", "印发", "暴涨", "利好", "突破", "立案", "调查", "涨价"]
    for kw in keywords:
        text = text.replace(kw, f"**<span style='color:red'>{kw}</span>**")
    return text

def make_search_link(title):
    """生成百度搜索链接，方便查细节"""
    return f"https://www.baidu.com/s?wd={title}"

# --- 主程序 ---

def main():
    st.title("🦅 AI 投资参谋 V1.3 (早盘新闻版)")
    
    # 获取北京时间
    tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(tz)
    today_str = now_time.strftime("%Y-%m-%d")
    current_time_str = now_time.strftime("%H:%M")
    
    st.caption(f"📅 当前北京时间: {today_str} {current_time_str}")

    # --- 模块1：晨间必读 (News) ---
    st.header("🗞️ 7x24 核心财经快讯")
    st.caption("来源：财联社 | 点击标题可跳转搜索详情")
    
    with st.spinner("正在抓取最新电报..."):
        news_df = get_morning_news()
        
    if not news_df.empty:
        # 使用 expander 或者是滚动区域，这里用简单的列表展示
        for index, row in news_df.iterrows():
            # 财联社的数据通常包含 'title' 和 'content'
            title = row.get('title', '')
            content = row.get('content', '')
            publish_time = row.get('publish_time', '')  # 或者是 'time'
            
            # 如果 title 为空，用 content 前20个字代替
            if not title:
                title = content[:30] + "..."
            
            # 渲染一条新闻
            with st.expander(f"⏰ {publish_time} | {title}"):
                # 高亮关键词
                styled_content = highlight_keywords(content)
                st.markdown(styled_content, unsafe_allow_html=True)
                st.markdown(f"[🔍 点击搜索此新闻详情]({make_search_link(title)})")
    else:
        st.info("暂无最新快讯，或接口暂时繁忙。")

    st.divider()

    # --- 模块2：量化选股 (Stock Picking) ---
    st.header("🎯 AI 量化选股结果")

    # 1. 交易日判断
    if not is_trading_day():
        st.warning("⚠️ 今天是 A 股休市日，不执行选股逻辑。安心看新闻复盘吧。")
        st.stop()

    # 2. 开盘时间判断 (09:25 之前不选股)
    # 设定开盘时间点
    market_open_time = time(9, 25) 
    
    if now_time.time() < market_open_time:
        st.info(f"⏳ 还没开盘 (09:25后开启)。\n\nAI 正在待命，请先阅读上方新闻，建立今日的市场感觉。\n\n当前策略：早盘看消息，开盘看量价。")
    else:
        # 09:25 之后，开始显示选股结果
        col1, col2 = st.columns(2)
        pos, us_chg = get_market_sentiment()
        with col1: st.metric("今日建议仓位", pos)
        with col2: st.metric("外盘指引", f"{us_chg:.2f}%")
        
        with st.spinner("🤖 A股已开盘，AI 正在全市场扫描量价异动..."):
            df_result = advanced_screening()
        
        if df_result.empty:
            st.warning("开盘后暂无符合【量价共振】的标的，建议耐心等待或空仓。")
        else:
            # 渲染选股表格
            def make_stock_link(code):
                market_prefix = "sh" if code.startswith("6") else "sz"
                link = f"http://quote.eastmoney.com/{market_prefix}{code}.html"
                return f'<a target="_blank" href="{link}">{code}</a>'

            df_display = df_result[['代码', '名称', '所属行业', '涨跌幅', '量比', '综合得分']]
            df_display['代码'] = df_display['代码'].apply(make_stock_link)
            
            st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.success("💡 选股完成！请结合上方的【新闻热点】判断：如果选出的股票行业与新闻利好一致，胜率翻倍！")

if __name__ == "__main__":
    main()
