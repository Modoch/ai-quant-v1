import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time
import pytz 

# --- 页面配置 (专业暗色调) ---
st.set_page_config(page_title="A股操盘手 V2.0 (全球映射版)", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 1. 领航员逻辑：全球视野
# ==========================================

@st.cache_data(ttl=3600)
def get_global_context():
    """
    获取昨夜全球核心资产表现，作为今日A股风向标
    """
    try:
        # 美股三大指
        df_inx = ak.stock_us_daily(symbol=".INX") # 标普500
        df_ixic = ak.stock_us_daily(symbol=".IXIC") # 纳斯达克
        
        sp500_chg = df_inx['close'].pct_change().iloc[-1] * 100
        nasdaq_chg = df_ixic['close'].pct_change().iloc[-1] * 100
        
        # 核心科技股映射 (手动映射A股对标板块)
        # NVDA(英伟达) -> 算力/光模块
        # TSLA(特斯拉) -> 汽车/机器人
        # AAPL(苹果) -> 消费电子
        # MSFT(微软) -> 软件/AI应用
        
        # 注意：这里需要akshare能获取个股数据，如果接口不稳定，我们主要看纳指
        # 为了稳定性，V2.0 MVP 主要以纳指代表科技情绪
        
        return sp500_chg, nasdaq_chg
    except:
        return 0.0, 0.0

@st.cache_data(ttl=600)
def get_important_news():
    """获取宏观新闻，用于人工判断今日主线"""
    try:
        df = ak.stock_news_em(symbol="000001")
        return df[['发布时间', '新闻标题']].head(10)
    except:
        return pd.DataFrame()

# ==========================================
# 2. 操盘手逻辑：选股 + 避险
# ==========================================

@st.cache_data(ttl=300)
def scanner(exclude_industries):
    """
    核心选股引擎
    参数 exclude_industries: 用户输入的'黑名单'行业列表 (如 ['软件开发', '互联网'])
    """
    try:
        # 1. 获取全市场实时行情
        df_all = ak.stock_zh_a_spot_em()
        
        # 2. 基础清洗
        df = df_all.copy()
        df['代码'] = df['代码'].astype(str)
        df['名称'] = df['名称'].astype(str)
        
        # 3. 排除ST、退市、北交所(30/60/00开头)
        df = df[~df['名称'].str.contains("ST|退市|N|C|U")]
        df = df[df['代码'].str.startswith(('60', '00', '30'))]
        
        # 4. 数值转换
        cols = ['最新价', '涨跌幅', '量比', '换手率', '成交量']
        for col in cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 5. 【关键升级】获取个股行业 (为了速度，这里用简化逻辑，实际交易需本地数据库)
        # 由于实时拉取5000只股票行业太慢，我们采用“板块反向过滤”逻辑
        # 这里为了演示，我们假设用户输入了黑名单，我们通过名称模糊匹配或后续API匹配
        # *注：实战中，建议直接避开'概念'，这里我们用量价硬过滤*
        
        # 6. 操盘手选股公式 (每周10%目标 = 寻找爆发点)
        # 价格 < 100 (游资喜欢)
        # 涨幅 2% ~ 6% (起涨阶段，不追高，不接飞刀)
        # 量比 > 1.8 (主力明显介入)
        # 换手率 3% ~ 15% (有人气但未高潮)
        mask = (
            (df['最新价'] < 80) &
            (df['涨跌幅'] > 2.0) & 
            (df['涨跌幅'] < 6.0) &
            (df['量比'] > 1.8) &
            (df['换手率'] > 3.0) & 
            (df['换手率'] < 15.0)
        )
        targets = df[mask].copy()
        
        # 7. 综合打分
        targets['强度分'] = targets['涨跌幅'] * 0.4 + targets['量比'] * 2 + targets['换手率'] * 0.5
        targets = targets.sort_values('强度分', ascending=False).head(10) # 初选10只
        
        # 8. 【人工避险】获取这10只的行业，剔除黑名单
        final_list = []
        for index, row in targets.iterrows():
            code = row['代码']
            industry = "未知"
            try:
                # 查户口：是哪个行业的？
                info = ak.stock_individual_info_em(symbol=code)
                industry = info.loc[info['item'] == '行业板块', 'value'].values[0]
            except:
                pass
            
            # 检查是否在黑名单里
            is_blacklisted = False
            for bad_industry in exclude_industries:
                if bad_industry in industry:
                    is_blacklisted = True
                    break
            
            if not is_blacklisted:
                row['所属行业'] = industry
                final_list.append(row)
                
            if len(final_list) >= 3: # 只要前3只
                break
                
        return pd.DataFrame(final_list)

    except Exception as e:
        st.error(f"数据扫描异常: {e}")
        return pd.DataFrame()

# ==========================================
# 3. 操盘手驾驶舱 (前端)
# ==========================================

def main():
    tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(tz)
    
    # 侧边栏：情报中心
    with st.sidebar:
        st.header("🌍 全球情报中心")
        sp500, nasdaq = get_global_context()
        
        col_us1, col_us2 = st.columns(2)
        col_us1.metric("标普500", f"{sp500:.2f}%", delta=f"{sp500:.2f}%")
        col_us2.metric("纳斯达克", f"{nasdaq:.2f}%", delta=f"{nasdaq:.2f}%")
        
        if nasdaq < -1.5:
            st.error("🚨 警告：昨夜美股科技重挫！\n今日严禁接力科技/软件/AI板块。")
        elif nasdaq > 1.5:
            st.success("🔥 提示：美股科技大涨，关注A股映射（光模块/算力）。")
            
        st.divider()
        st.subheader("📰 早盘关键消息")
        news = get_important_news()
        if not news.empty:
            for i, row in news.iterrows():
                title = row['新闻标题']
                st.caption(f"• {title}")
                
    # 主界面
    st.title("🦅 A股操盘手 V2.0 (狙击模式)")
    st.caption(f"目标：周收益10% | 当前时间: {now_time.strftime('%H:%M')}")
    
    # --- 模块1：风险控制 (The Shield) ---
    st.markdown("### 🛡️ 风险屏蔽 (黑名单)")
    st.info("💡 操盘手直觉：如果昨晚AI软件股大跌，请在下方屏蔽【软件开发】、【互联网服务】。")
    
    # 用户输入要屏蔽的行业
    user_input = st.text_input("🚫 输入今日要回避的板块 (用空格隔开，例如：软件 房地产)", "")
    exclude_list = user_input.split() if user_input else []
    
    if exclude_list:
        st.warning(f"已启动风控，正在剔除包含以下关键词的股票：{exclude_list}")
    
    st.divider()

    # --- 模块2：猎杀时刻 (The Sword) ---
    st.markdown("### ⚔️ 猎杀时刻 (Top 3)")
    
    # 交易时间判断
    if now_time.hour < 9 or (now_time.hour == 9 and now_time.minute < 25):
        st.warning("⏳ 9:25 集合竞价结束后开启扫描。现在请阅读侧边栏新闻，设定上方的【回避板块】。")
    else:
        if st.button("🚀 启动量化扫描", type="primary"):
            with st.spinner("正在进行：全市场扫描 -> 量价过滤 -> 行业黑名单剔除..."):
                df_res = scanner(exclude_list)
            
            if df_res.empty:
                st.error("今日行情极端或全部命中黑名单，建议空仓休息！")
            else:
                # 格式化显示
                df_show = df_res[['代码', '名称', '所属行业', '最新价', '涨跌幅', '量比', '换手率', '强度分']].copy()
                
                # 链接跳转
                def make_link(code):
                    market = "sh" if code.startswith("6") else "sz"
                    return f'<a target="_blank" href="http://quote.eastmoney.com/{market}{code}.html">{code}</a>'
                
                df_show['代码'] = df_show['代码'].apply(make_link)
                
                # 颜色高亮
                st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)
                
                st.success("✅ 锁定目标！请点击代码查看K线形态：\n1. 必须是低位放量或突破形态。\n2. 必须不在你刚才屏蔽的【软件】板块中。")

    st.divider()
    st.markdown("**💰 操盘纪律：** 每周10%不是靠每天涨2%，而是靠抓到一个涨停板后，即使回撤也能保住利润。**看不懂的板块（如昨晚大跌的软件），绝对不做！**")

if __name__ == "__main__":
    main()
