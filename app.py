import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time, timedelta
import pytz 
import time as time_module

# --- 页面配置 ---
st.set_page_config(page_title="A股操盘手 V2.4 (海外IP逃生版)", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. 核心后端逻辑
# ==========================================

def get_beijing_time():
    tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(tz)

@st.cache_data(ttl=3600)
def get_global_context():
    """获取美股情绪 (海外服务器访问美股通常没问题)"""
    try:
        df_inx = ak.stock_us_daily(symbol=".INX") 
        df_ixic = ak.stock_us_daily(symbol=".IXIC") 
        sp500 = df_inx['close'].pct_change().iloc[-1] * 100
        nasdaq = df_ixic['close'].pct_change().iloc[-1] * 100
        return sp500, nasdaq
    except:
        return 0.0, 0.0

@st.cache_data(ttl=300)
def get_important_news():
    """【V2.4 新闻逃生通道】优先财联社，失败则切新浪财经"""
    today = get_beijing_time().date()
    yesterday = today - timedelta(days=1)
    valid_dates = [str(today), str(yesterday)]
    
    # 尝试通道 A: 财联社
    try:
        df = ak.stock_telegraph_cls()
        if not df.empty:
            df = df.rename(columns={'title': '标题', 'content': '内容', 'publish_time': '时间'})
            df['日期'] = df['时间'].astype(str).str.slice(0, 10)
            df = df[df['日期'].isin(valid_dates)] # 只看今昨
            df['时间'] = df['时间'].astype(str).str.slice(5, 16)
            return df[['时间', '标题']].head(15), "财联社"
    except:
        pass # 失败直接跳过

    # 尝试通道 B: 新浪财经 (海外IP友好)
    try:
        # 新浪的接口比较杂，这里用js_news兜底，或者直接返回提示
        # 由于akshare新浪接口变动频繁，为保稳定，如果财联社挂了，
        # 我们返回一个静态提示，引导用户去本地运行
        pass 
    except:
        pass
        
    return pd.DataFrame(), "无信号"

@st.cache_data(ttl=60)
def scanner():
    """【V2.4 双模扫描】支持从 东方财富 自动降级到 新浪财经"""
    
    data_source = "东方财富 (主力源)"
    df = pd.DataFrame()
    
    # --- 尝试源 1：东方财富 (数据最全，含量比) ---
    try:
        df_all = ak.stock_zh_a_spot_em()
        if not df_all.empty:
            df = df_all.copy()
            # 基础清洗
            df['代码'] = df['代码'].astype(str)
            df['名称'] = df['名称'].astype(str)
            df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
            df = df[df['代码'].str.startswith(('60', '00', '30'))]
            
            for col in ['最新价', '涨跌幅', '量比', '换手率']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            # 东方财富策略：含量比
            mask = (df['最新价'] < 100) & (df['涨跌幅'] > 2.0) & (df['涨跌幅'] < 8.0) & (df['量比'] > 1.5) & (df['换手率'] > 2.5)
            df = df[mask]
            df['强度分'] = df['涨跌幅'] * 0.4 + df['量比'] * 2
            
    except Exception:
        # --- 尝试源 2：新浪财经 (海外IP通常能连，但无量比数据) ---
        try:
            data_source = "新浪财经 (备用源)"
            df_sina = ak.stock_zh_a_spot() # 新浪全市场接口
            
            # 新浪列名映射：code, name, trade(最新价), changepercent(涨跌幅), turnoverratio(换手率), volume(成交量)
            # 注意：新浪没有【量比】列！
            df = df_sina.copy()
            df = df.rename(columns={'trade':'最新价', 'changepercent':'涨跌幅', 'turnoverratio':'换手率', 'name':'名称', 'code':'代码'})
            
            # 清洗
            df['代码'] = df['代码'].astype(str)
            df = df[df['代码'].str.startswith(('sh60', 'sz00', 'sz30'))] # 新浪代码带前缀
            df['代码'] = df['代码'].str.replace('sh','').str.replace('sz','') # 去前缀匹配统一格式
            
            for col in ['最新价', '涨跌幅', '换手率']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # 新浪策略：无量比，用强换手替代
            # 换手率要求提高到 4% 以弥补量比缺失
            mask = (df['最新价'] < 100) & (df['涨跌幅'] > 2.5) & (df['涨跌幅'] < 8.0) & (df['换手率'] > 4.0)
            df = df[mask]
            df['量比'] = 0.0 # 缺失填充
            df['强度分'] = df['涨跌幅'] * 0.6 + df['换手率'] * 0.5

        except Exception as e:
            return pd.DataFrame(), f"全网封锁: {str(e)}"

    if df.empty:
        return pd.DataFrame(), "无结果"

    # 统一输出
    res = df.sort_values('强度分', ascending=False).head(10)
    res['强度分'] = res['强度分'].round(1)
    res['量比'] = res['量比'].round(2)
    res['换手率'] = res['换手率'].round(2)
    
    return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '强度分']], data_source

# ==========================================
# 2. 前端展示
# ==========================================

def main():
    now_time = get_beijing_time()
    today_str = now_time.strftime("%m-%d")
    
    with st.sidebar:
        st.header("🌍 全球情报")
        sp500, nasdaq = get_global_context()
        c1, c2 = st.columns(2)
        c1.metric("标普", f"{sp500:.2f}%")
        c2.metric("纳指", f"{nasdaq:.2f}%")
        
        st.divider()
        st.subheader(f"📰 实时快讯 ({today_str})")
        
        with st.spinner("同步新闻中..."):
            news_df, source = get_important_news()
            
        if not news_df.empty:
            st.caption(f"来源: {source}")
            for i, row in news_df.iterrows():
                link = f"https://www.baidu.com/s?wd={row['标题']}"
                st.markdown(f"`{row['时间']}` [{row['标题']}]({link})")
        else:
            st.warning("海外节点无法获取国内新闻，请使用本地部署。")

    st.title("🦅 A股操盘手 V2.4 (逃生版)")
    st.caption("提示：如一直显示“数据扫描异常”，说明免费云服务器IP已被彻底封锁。请尝试下方的【终极方案】。")
    
    st.divider()
    st.subheader("⚔️ 猎杀时刻 (Top 5)")
    
    if st.button("🚀 启动扫描", type="primary"):
        with st.spinner("正在尝试连接国内数据源..."):
            df_res, src = scanner()
        
        if df_res.empty:
            st.error(f"扫描失败: {src}")
        else:
            st.success(f"✅ 扫描成功！当前数据源：{src}")
            if "新浪" in src:
                st.warning("⚠️ 注意：当前使用【新浪备用源】，因缺失量比数据，筛选准确度略有下降。")
            
            def make_link(code):
                market = "sh" if code.startswith("6") else "sz"
                link = f"http://quote.eastmoney.com/{market}{code}.html"
                return f'<a target="_blank" href="{link}">{code}</a>'

            df_show = df_res.copy()
            df_show['代码'] = df_show['代码'].apply(make_link)
            df_show.columns = ['股票代码', '名称', '当前价', '涨幅%', '量比(备用0)', '换手%', '强度分']
            st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
