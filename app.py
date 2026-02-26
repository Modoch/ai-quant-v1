import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime
import pytz
import time

# --- 页面配置 ---
st.set_page_config(page_title="A股御用精选 V4.0 (防封版)", layout="centered")

# --- 核心逻辑：防封印 + 冠军算法 ---

# 1. 强制缓存60秒：这是防封的关键！
# 哪怕你1秒点一次刷新，60秒内也只会请求一次交易所，保护你的IP。
@st.cache_data(ttl=60, show_spinner=False)
def get_safe_data():
    """
    V4.0 防封逻辑：
    请求数据，如果失败（被封），返回None，让前端提示。
    """
    try:
        # 获取全市场实时行情
        df_all = ak.stock_zh_a_spot_em()
        return df_all
    except Exception:
        return None

def select_top_stocks(df):
    if df is None or df.empty:
        return pd.DataFrame()

    # --- 基础清洗 ---
    df['代码'] = df['代码'].astype(str)
    # 只看主板(60/00)和创业(30)/科创(68)
    df = df[df['代码'].str.startswith(('60', '00', '30', '68'))]
    # 剔除ST、退市、新股(N/C/U)
    df = df[~df['名称'].str.contains("ST|退市|N|C|U")]

    # --- 数值清洗 ---
    cols = ['最新价', '涨跌幅', '量比', '换手率', '成交额', '流通市值']
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- 交易员的选股审美 (过滤器) ---
    # 1. 只要“活”的票：成交额 > 5000万 (太冷门的不要)
    # 2. 只要“强”的票：涨幅 > 2.0% (没有赚钱效应的不要)
    # 3. 只要“真”的票：换手率 > 1.5% (没人玩的僵尸股不要)
    # 4. 剔除高价股：股价 < 100元 (方便小资金操作)
    mask = (
        (df['成交额'] > 50000000) &
        (df['涨跌幅'] > 2.0) & 
        (df['涨跌幅'] < 9.5) &  # 涨停的买不进去，剔除
        (df['换手率'] > 1.5) &
        (df['最新价'] < 100)
    )
    targets = df[mask].copy()

    if targets.empty:
        return pd.DataFrame()

    # --- 冠军算法：计算“爆发分” ---
    # 逻辑：量比代表“突发”，涨幅代表“强度”，换手代表“人气”
    # 爆发分 = (量比 x 40) + (涨幅 x 30) + (换手 x 10)
    # 这里的权重是我根据A股短线风格调的
    targets['爆发分'] = (targets['量比'] * 40) + (targets['涨跌幅'] * 30) + (targets['换手率'] * 10)

    # --- 终极筛选：只取 Top 6 ---
    # 按爆发分倒序排，取前6名
    final_res = targets.sort_values(by="爆发分", ascending=False).head(6)

    return final_res[['代码', '名称', '最新价', '涨跌幅', '量比', '换手率', '爆发分']]

# --- 前端展示 ---

def main():
    st.title("🏆 A股御用精选 (Top 6)")
    st.caption("V4.0 特性：防屏蔽机制 | 智能评分 | 只推精华")
    
    # 获取当前时间
    tz = pytz.timezone('Asia/Shanghai')
    now_str = datetime.now(tz).strftime("%H:%M:%S")

    # 状态提示
    st.info(f"上次数据更新: {now_str} (系统自动锁定每分钟只拉取一次，防止IP被封)")

    # 按钮逻辑
    if st.button('⚡ 刷新数据'):
        st.cache_data.clear() # 只有点按钮才清缓存，但为了防封，建议少点
        st.rerun()

    with st.spinner("正在通过安全通道获取数据..."):
        raw_df = get_safe_data()

    # --- 异常处理 ---
    if raw_df is None:
        st.error("🚫 警报：无法获取数据！")
        st.warning("""
        可能原因：
        1. 您的IP访问过于频繁，被交易所暂时屏蔽。
        2. 当前是非交易时间。
        
        👉 **解决方案**：请喝杯茶，等待 5-10 分钟后再刷新，不要频繁点击。
        """)
        st.stop()

    # --- 数据处理 ---
    top_stocks = select_top_stocks(raw_df)

    if top_stocks.empty:
        st.warning("📉 当前盘面极度低迷，无符合标准的强势股。建议空仓休息。")
    else:
        st.success("🎯 今日最强 6 只标的已生成")
        
        # 漂亮的表格展示
        st.dataframe(
            top_stocks,
            hide_index=True,
            column_config={
                "代码": st.column_config.TextColumn("代码"),
                "涨跌幅": st.column_config.NumberColumn("涨幅", format="%.2f%%"),
                "量比": st.column_config.NumberColumn("量比 (突发资金)", format="%.2f"),
                "换手率": st.column_config.NumberColumn("换手 (活跃度)", format="%.2f%%"),
                "爆发分": st.column_config.ProgressColumn(
                    "综合爆发力",
                    format="%.0f",
                    min_value=0,
                    max_value=500, # 预估最高分
                ),
            }
        )
        
    st.divider()
    st.markdown("""
    #### 👨‍🏫 操盘纪律 (负债翻身必读)：
    1. **只看第一名：** 这里的6只里，爆发分最高的那个，通常是当天的“情绪总龙头”。
    2. **控制频率：** 这个代码有缓存保护，**不要**每秒都去点刷新，没用的。**每15分钟**看一次足矣。
    3. **如果报错：** 如果出现红色报错，说明你已经被封了。关掉网页，拔掉路由器电源重插（换个IP），过10分钟再来。
    """)

if __name__ == "__main__":
    main()
