import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time
import pytz 

# --- 页面配置 ---
st.set_page_config(page_title="A股操盘手 V2.2 (普涨应对版)", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. 核心后端逻辑
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

@st.cache_data(ttl=300)
def get_important_news():
    """
    【V2.2 新闻修复】
    大幅放宽过滤条件。
    保留“指数”、“资金”、“成交”等宏观词汇，只过滤纯个股垃圾广告。
    """
    # 仅过滤纯粹的垃圾营销词，保留宏观描述
    noise_keywords = [
        "净流入", "净流出", "净买入", "融资", "融券", 
        "大宗交易", "榜", "增至", "甚至"
    ]
    
    try:
        # 优先用东方财富（宏观面更全）
        df = ak.stock_news_em(symbol="000001")
        if df.empty:
            df = ak.stock_telegraph_cls() 
            df = df.rename(columns={'title': '新闻标题', 'publish_time': '发布时间'})

        if not df.empty:
            df = df.rename(columns={'发布时间': '时间', '新闻标题': '标题'})
            
            # 1. 确保是字符串
            df = df[df['标题'].apply(lambda x: isinstance(x, str))]
            
            # 2. 温和去噪 (不再过滤'指数'等词)
            pattern = '|'.join(noise_keywords)
            df = df[~df['标题'].str.contains(pattern, case=False)]
            
            # 3. 截取时间
            df['时间'] = df['时间'].astype(str).apply(lambda x: x[-8:] if len(x) >= 8 else x)
            
            return df[['时间', '标题']].head(20) # 多返回一些
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=60) # 缩短缓存到1分钟，适应盘中变化
def scanner(mode="auto"):
    """
    【V2.2 自适应扫描】
    逻辑：
    1. 先尝试 V2.1 的【严选模式】（量比>1.8, 换手>3%）。
    2. 如果结果为空（说明行情特殊或普涨无龙头），自动降级为【宽网模式】（量比>1.0, 换手>1%）。
    """
    try:
        # 1. 获取全市场实时行情
        df_all = ak.stock_zh_a_spot_em()
        
        # 2. 基础清洗
        df = df_all.copy()
        df['代码'] = df['代码'].astype(str)
        df['名称'] = df['名称'].astype(str)
        df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
        df = df[df['代码'].str.startswith(('60', '00', '30'))]
        
        # 3. 数值转换
        for col in ['最新价', '涨跌幅', '量比', '换手率']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # 4. 基础池：剔除极值
        base_mask = (df['最新价'] < 100) & (df['最新价'] > 3)
        df = df[base_mask]

        # --- 策略 A：严选狙击 (V2.1 逻辑) ---
        mask_strict = (
            (df['涨跌幅'] > 3.0) & 
            (df['涨跌幅'] < 8.0) &
            (df['量比'] > 1.8) &
            (df['换手率'] > 3.0)
        )
        targets_strict = df[mask_strict].copy()
        
        # --- 策略 B：宽网打捞 (普涨行情逻辑) ---
        # 只要涨得好(>2%)，量比正常(>1.0)，换手有动静(>1%)就算
        mask_loose = (
            (df['涨跌幅'] > 2.0) & 
            (df['涨跌幅'] < 9.0) &
            (df['量比'] > 0.9) &
            (df['换手率'] > 1.0)
        )
        targets_loose = df[mask_loose].copy()

        # 决策逻辑：优先返回严选，如果严选太少，返回宽网
        final_res = pd.DataFrame()
        strategy_name = ""

        if len(targets_strict) >= 3:
            final_res = targets_strict
            strategy_name = "🎯 严选狙击模式 (主力强控盘)"
        else:
            final_res = targets_loose
            strategy_name = "🌊 宽网普涨模式 (放宽条件)"

        if final_res.empty:
            return pd.DataFrame(), "无结果"

        # 综合打分
        final_res['强度分'] = final_res['涨跌幅'] * 0.4 + final_res['量比'] * 2
        
        # 排序取前 10
        res = final_res.sort_values('强度分', ascending=False).head(10)
        
        # 格式化
        res['强度分'] = res['强度分'].round(1)
        res['量比'] = res['量比'].round(2)
        res['换手率'] = res['换手率'].round(2)
        
        return res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '强度分']], strategy_name

    except Exception as e:
        return pd.DataFrame(), f"Error: {str(e)}"

# ==========================================
# 2. 前端展示
# ==========================================

def main():
    tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(tz)
    
    # --- 侧边栏 ---
    with st.sidebar:
        st.header("🌍 全球情报")
        sp500, nasdaq = get_global_context()
        c1, c2 = st.columns(2)
        c1.metric("标普", f"{sp500:.2f}%")
        c2.metric("纳指", f"{nasdaq:.2f}%")
        
        st.divider()
        st.subheader("📰 实时宏观 (已修复)")
        st.caption("点击标题搜索 | 保留大盘动态")
        
        news_df = get_important_news()
        if not news_df.empty:
            for i, row in news_df.iterrows():
                time_str = str(row['时间'])
                title = str(row['标题'])
                link = f"https://www.baidu.com/s?wd={title}"
                # 使用 Emoji 区分不同新闻
                icon = "🔥" if "指数" in title or "大涨" in title else "📄"
                st.markdown(f"{icon} `{time_str}` [{title}]({link})")
        else:
            st.info("暂无数据，请稍后刷新")

    # --- 主界面 ---
    st.title("🦅 A股操盘手 V2.2 (普涨应对版)")
    st.caption(f"北京时间: {now_time.strftime('%H:%M:%S')} | 市场状态: 活跃")
    
    st.info("💡 更新说明：已大幅放宽新闻过滤，并增加了【宽网模式】。如果严选模式没有结果，系统会自动为你寻找涨势最好的补涨股。")
    
    st.divider()

    st.subheader("⚔️ 猎杀时刻 (Top 5)")
    
    # 检查时间
    if now_time.hour < 9 or (now_time.hour == 9 and now_time.minute < 25):
        st.warning("⏳ 09:25 集合竞价后开启扫描。")
    else:
        if st.button("🚀 立即扫描", type="primary"):
            with st.spinner("正在全市场分析..."):
                df_res, strategy_used = scanner()
            
            if df_res.empty:
                st.error("数据异常或全市场休市。")
            else:
                # 显示使用了什么策略
                st.success(f"✅ 扫描成功！当前触发：{strategy_used}")
                
                # 制作跳转链接
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
    with c1: st.error("【买入】\n不论什么模式，必须看K线是否在底部")
    with c2: st.error("【避险】\n普涨行情切忌追高7%以上的票")
    with c3: st.error("【止损】\n亏损-4%无条件离场")

if __name__ == "__main__":
    main()
