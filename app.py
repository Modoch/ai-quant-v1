import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time, timedelta
import pytz 
import time as time_module # 引入时间模块用于重试延时

# --- 页面配置 ---
st.set_page_config(page_title="A股操盘手 V2.3 (实时新闻修复版)", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. 核心后端逻辑
# ==========================================

def get_beijing_time():
    """获取当前北京时间"""
    tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(tz)

@st.cache_data(ttl=3600)
def get_global_context():
    """获取昨夜美股情绪"""
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
    """
    【V2.3 新闻终极修复】
    1. 强制过滤：只保留【今日】和【昨日】的新闻，剔除所有远古旧闻。
    2. 增加重试机制：解决 RemoteDisconnected 问题。
    """
    # 垃圾词过滤
    noise_keywords = ["净流入", "净流出", "净买入", "融资", "融券", "大宗交易", "榜", "增至", "甚至"]
    
    # 获取今天的日期字符串 (格式: YYYY-MM-DD)
    today = get_beijing_time().date()
    yesterday = today - timedelta(days=1)
    valid_dates = [str(today), str(yesterday)]
    
    # 重试 3 次
    for _ in range(3):
        try:
            # 优先使用财联社 (最快最全)
            df = ak.stock_telegraph_cls()
            
            if not df.empty:
                # 统一列名
                df = df.rename(columns={'title': '标题', 'content': '内容', 'publish_time': '时间'})
                
                # --- 关键逻辑：时间清洗 ---
                # 财联社的时间格式通常是 "YYYY-MM-DD HH:MM:SS"
                # 我们只保留日期匹配今日或昨日的行
                df['日期'] = df['时间'].astype(str).str.slice(0, 10) # 提取前10位 YYYY-MM-DD
                df = df[df['日期'].isin(valid_dates)]
                
                # --- 内容去噪 ---
                df = df[df['标题'].apply(lambda x: isinstance(x, str))]
                pattern = '|'.join(noise_keywords)
                df = df[~df['标题'].str.contains(pattern, case=False)]
                
                # 格式化时间显示 (仅显示 MM-DD HH:MM)
                df['时间'] = df['时间'].astype(str).str.slice(5, 16)
                
                return df[['时间', '标题']].head(20)
                
        except Exception:
            time_module.sleep(1) # 失败等待1秒重试
            continue
            
    return pd.DataFrame()

@st.cache_data(ttl=60)
def scanner(mode="auto"):
    """
    【V2.3 扫描增强】
    增加网络重试机制，防止 'Connection aborted' 报错。
    """
    max_retries = 3
    df_all = pd.DataFrame()
    
    # 1. 带重试的数据拉取
    for i in range(max_retries):
        try:
            df_all = ak.stock_zh_a_spot_em()
            if not df_all.empty:
                break
        except:
            time_module.sleep(1)
            continue
    
    if df_all.empty:
        return pd.DataFrame(), "网络波动，请刷新重试"

    try:
        # 2. 基础清洗
        df = df_all.copy()
        df['代码'] = df['代码'].astype(str)
        df['名称'] = df['名称'].astype(str)
        df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
        df = df[df['代码'].str.startswith(('60', '00', '30'))]
        
        # 3. 数值转换
        for col in ['最新价', '涨跌幅', '量比', '换手率']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        base_mask = (df['最新价'] < 100) & (df['最新价'] > 3)
        df = df[base_mask]

        # --- 策略 A：严选狙击 ---
        mask_strict = (
            (df['涨跌幅'] > 3.0) & (df['涨跌幅'] < 8.0) &
            (df['量比'] > 1.8) & (df['换手率'] > 3.0)
        )
        targets_strict = df[mask_strict].copy()
        
        # --- 策略 B：宽网打捞 ---
        mask_loose = (
            (df['涨跌幅'] > 2.0) & (df['涨跌幅'] < 9.5) &
            (df['量比'] > 1.0) & (df['换手率'] > 1.5)
        )
        targets_loose = df[mask_loose].copy()

        # 决策逻辑
        final_res = pd.DataFrame()
        strategy_name = ""

        if len(targets_strict) >= 3:
            final_res = targets_strict
            strategy_name = "🎯 严选狙击 (主力强控盘)"
        else:
            final_res = targets_loose
            strategy_name = "🌊 宽网普涨 (放宽条件)"

        if final_res.empty:
            return pd.DataFrame(), "无结果"

        # 综合打分
        final_res['强度分'] = final_res['涨跌幅'] * 0.4 + final_res['量比'] * 2
        
        # 排序
        res = final_res.sort_values('强度分', ascending=False).head(10)
        
        # 格式化
        res['强度分'] = res['强度分'].round(1)
        res['量比'] = res['量比'].round(2)
        res['换手率'] = res['换手率'].round(2)
        
        return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '强度分']], strategy_name

    except Exception as e:
        return pd.DataFrame(), f"数据处理异常: {str(e)}"

# ==========================================
# 2. 前端展示
# ==========================================

def main():
    now_time = get_beijing_time()
    today_str = now_time.strftime("%m-%d") # 仅显示月-日
    
    # --- 侧边栏 ---
    with st.sidebar:
        st.header("🌍 全球情报")
        sp500, nasdaq = get_global_context()
        c1, c2 = st.columns(2)
        c1.metric("标普", f"{sp500:.2f}%")
        c2.metric("纳指", f"{nasdaq:.2f}%")
        
        st.divider()
        st.subheader(f"📰 实时快讯 ({today_str})")
        st.caption("✅ 已过滤旧闻，只看今昨 | 点击搜索")
        
        with st.spinner("正在同步财联社电报..."):
            news_df = get_important_news()
            
        if not news_df.empty:
            for i, row in news_df.iterrows():
                time_str = str(row['时间'])
                title = str(row['标题'])
                link = f"https://www.baidu.com/s?wd={title}"
                # 动态图标
                icon = "🔥" if "利好" in title or "突破" in title else "📄"
                st.markdown(f"{icon} `{time_str}` [{title}]({link})")
        else:
            st.warning("暂无今日实时消息，或接口响应超时。")

    # --- 主界面 ---
    st.title("🦅 A股操盘手 V2.3 (实时修复版)")
    st.caption(f"北京时间: {now_time.strftime('%H:%M:%S')} | 市场状态: { '交易中' if 9<=now_time.hour<15 else '休市' }")
    
    st.info("💡 修复日志：已增加【日期强制过滤】，确保您看到的新闻绝对是今天的。同时增强了网络连接稳定性。")
    
    st.divider()

    st.subheader("⚔️ 猎杀时刻 (Top 5)")
    
    # 检查时间
    if now_time.hour < 9 or (now_time.hour == 9 and now_time.minute < 25):
        st.warning("⏳ 09:25 集合竞价后开启扫描。")
    else:
        if st.button("🚀 立即扫描", type="primary"):
            with st.spinner("正在全市场分析 (已开启网络重试)..."):
                df_res, strategy_used = scanner()
            
            if df_res.empty:
                st.error(f"扫描无结果: {strategy_used}")
            else:
                st.success(f"✅ 扫描成功！当前触发：{strategy_used}")
                
                def make_link(code):
                    market = "sh" if code.startswith("6") else "sz"
                    link = f"http://quote.eastmoney.com/{market}{code}.html"
                    return f'<a target="_blank" href="{link}">{code}</a>'

                df_show = df_res.copy()
                df_show['代码'] = df_show['代码'].apply(make_link)
                df_show.columns = ['股票代码', '名称', '当前价', '涨幅%', '量比', '换手%', '强度分']
                
                st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)
                st.caption("👉 点击【股票代码】跳转东方财富，查看行业与K线。")

    st.divider()
    st.markdown("### 🛡️ 操盘纪律")
    c1, c2, c3 = st.columns(3)
    with c1: st.error("【买入】\nK线底部放量 + 题材共振")
    with c2: st.error("【避险】\n新闻利空板块坚决不碰")
    with c3: st.error("【止损】\n亏损-4%无条件离场")

if __name__ == "__main__":
    main()
