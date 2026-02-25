import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time
import pytz 

# --- 页面配置 ---
st.set_page_config(page_title="A股操盘手 V2.1 (稳定极速版)", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. 核心后端逻辑 (稳健优先)
# ==========================================

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

@st.cache_data(ttl=600)
def get_important_news():
    """
    【V2.1 暴力去噪版】
    1. 强制显示 HH:MM 时间
    2. 生成百度搜索链接
    3. 剔除所有资金流向噪音
    """
    # 垃圾词库：凡是标题里有这些词的，一行都不要
    noise_keywords = [
        "资金", "净流入", "净流出", "净买入", "融资", "融券", 
        "大宗交易", "主力", "收盘", "开盘", "指数", "成交", 
        "榜", "流向", "增至", "甚至", "连续", "日净"
    ]
    
    try:
        # 优先用东方财富（宏观面更全）
        df = ak.stock_news_em(symbol="000001")
        if df.empty:
            df = ak.stock_telegraph_cls() # 备用财联社
            df = df.rename(columns={'title': '新闻标题', 'publish_time': '发布时间'})

        if not df.empty:
            df = df.rename(columns={'发布时间': '时间', '新闻标题': '标题'})
            
            # --- 核心过滤逻辑 ---
            # 1. 只要标题是字符串的才处理
            df = df[df['标题'].apply(lambda x: isinstance(x, str))]
            
            # 2. 暴力剔除噪音
            pattern = '|'.join(noise_keywords)
            df = df[~df['标题'].str.contains(pattern, case=False)]
            
            # 3. 截取时间仅显示 HH:MM:SS
            # 兼容不同格式，统一尝试截取后8位
            df['时间'] = df['时间'].astype(str).apply(lambda x: x[-8:] if len(x) >= 8 else x)
            
            return df[['时间', '标题']].head(15)
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def scanner(exclude_industries_str):
    """
    【V2.1 极速扫描引擎】
    修复 Connection aborted 问题的关键：
    **绝对不**在循环里调用 ak.stock_individual_info_em。
    只用 broad market 数据进行计算，行业判断交给人工点击链接。
    """
    try:
        # 1. 获取全市场实时行情 (这是唯一一次网络请求，极快)
        df_all = ak.stock_zh_a_spot_em()
        
        # 2. 基础清洗
        df = df_all.copy()
        df['代码'] = df['代码'].astype(str)
        df['名称'] = df['名称'].astype(str)
        
        # 3. 排除ST、退市、北交所
        df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
        df = df[df['代码'].str.startswith(('60', '00', '30'))]
        
        # 4. 数值转换
        for col in ['最新价', '涨跌幅', '量比', '换手率']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 5. 操盘手选股公式 (量价共振)
        # 价格 < 80
        # 涨幅 2% ~ 7% (安全区间)
        # 量比 > 1.8 (主力强介入)
        # 换手 3% ~ 15% (活跃)
        mask = (
            (df['最新价'] < 80) &
            (df['涨跌幅'] > 2.0) & 
            (df['涨跌幅'] < 7.0) &
            (df['量比'] > 1.8) &
            (df['换手率'] > 3.0) & 
            (df['换手率'] < 15.0)
        )
        targets = df[mask].copy()
        
        if targets.empty: return pd.DataFrame()

        # 6. 综合打分
        targets['强度分'] = targets['涨跌幅'] * 0.4 + targets['量比'] * 2
        
        # 7. 排序取前 10
        # 注意：这里我们不再进行服务器端的“行业剔除”，防止超时。
        # 而是把所有结果返回，让用户自己在界面上看是否命中黑名单。
        res = targets.sort_values('强度分', ascending=False).head(5)
        
        # 格式化
        res['强度分'] = res['强度分'].round(1)
        res['量比'] = res['量比'].round(2)
        res['换手率'] = res['换手率'].round(2)
        
        return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '强度分']]

    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 2. 前端展示
# ==========================================

def main():
    tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(tz)
    
    # --- 侧边栏：情报 ---
    with st.sidebar:
        st.header("🌍 全球情报")
        sp500, nasdaq = get_global_context()
        
        c1, c2 = st.columns(2)
        c1.metric("标普", f"{sp500:.2f}%")
        c2.metric("纳指", f"{nasdaq:.2f}%")
        
        if nasdaq < -1.5:
            st.error("⚠️ 纳指大跌，今日回避【科技/软件】！")
            
        st.divider()
        st.subheader("📰 早盘关键消息")
        st.caption("点击标题搜索详情 | 已过滤资金噪音")
        
        news_df = get_important_news()
        if not news_df.empty:
            for i, row in news_df.iterrows():
                time_str = str(row['时间'])
                title = str(row['标题'])
                # 生成百度链接
                link = f"https://www.baidu.com/s?wd={title}"
                # 渲染可点击链接
                st.markdown(f"`{time_str}` [{title}]({link})")
                st.write("---")
        else:
            st.info("暂无重大宏观消息")

    # --- 主界面 ---
    st.title("🦅 A股操盘手 V2.1 (稳定极速版)")
    st.caption(f"当前北京时间: {now_time.strftime('%H:%M')} | 目标：周收益10%")
    
    # 风险提示区
    st.info("💡 操盘提示：如果昨晚美股大跌，请人工回避相关板块。本系统专注于挖掘【逆势抗跌】或【独立走强】的个股。")
    
    st.divider()

    # 扫描区
    st.subheader("⚔️ 猎杀时刻 (Top 5)")
    
    # 检查时间
    if now_time.hour < 9 or (now_time.hour == 9 and now_time.minute < 25):
        st.warning("⏳ 09:25 集合竞价后开启扫描。请先阅读左侧新闻。")
    else:
        if st.button("🚀 启动极速扫描", type="primary"):
            with st.spinner("正在扫描全市场量价异动..."):
                df_res = scanner("") # 传入空字符串，因不再做服务器端过滤
            
            if df_res.empty:
                st.warning("今日行情极端，未发现高分标的，建议空仓。")
            else:
                # 制作跳转链接
                def make_link(code):
                    market = "sh" if code.startswith("6") else "sz"
                    link = f"http://quote.eastmoney.com/{market}{code}.html"
                    return f'<a target="_blank" href="{link}">{code}</a>'

                df_show = df_res.copy()
                df_show['代码'] = df_show['代码'].apply(make_link)
                
                # 重命名列以匹配用户习惯
                df_show.columns = ['股票代码', '名称', '当前价', '涨幅%', '量比', '换手%', '强度分']
                
                st.success("✅ 扫描完成！请点击代码查看K线与行业：")
                st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)
                st.caption("👉 点击【股票代码】跳转东方财富，确认它【不是】你今天要回避的板块（如软件）。")

    st.divider()
    st.markdown("### 🛡️ 操盘纪律")
    c1, c2, c3 = st.columns(3)
    with c1: st.error("【买入】\n量比>1.8且K线底部放量")
    with c2: st.error("【避险】\n绝对不做昨晚美股大跌的对标板块")
    with c3: st.error("【止损】\n亏损-4%无条件离场")

if __name__ == "__main__":
    main()
