# streamlit run streamlit_asset_v1.py
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="자산 & RSI 모니터", layout="wide")
st.title("💰 내 자산 + RSI 추이")

# CSV 로드
try:
    df = pd.read_csv("asset_log.csv", names=["time", "price", "krw", "coin", "asset", "rsi"])
    df["time"] = pd.to_datetime(df["time"])
except FileNotFoundError:
    st.error("⚠️ asset_log.csv 파일이 없습니다.")
    st.stop()

# 중복 제거 및 정렬
df = df.drop_duplicates(subset=["time"], keep="last").sort_values("time")

# KPI
latest_asset = df["asset"].iloc[-1]
start_asset = df["asset"].iloc[0]
change_pct = (latest_asset / start_asset - 1) * 100
latest_rsi = df["rsi"].iloc[-1]

col1, col2, col3, col4 = st.columns(4)
col1.metric("📆 데이터 개수", f"{len(df)}개")
col2.metric("💰 현재 총 자산", f"{latest_asset:,.0f} 원")
col3.metric("📈 변화율", f"{change_pct:+.2f}%")
col4.metric("📊 현재 RSI", f"{latest_rsi:.2f}")

# 자산 그래프
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["time"], y=df["asset"], mode="lines+markers", name="총자산(원)", line=dict(width=2)))
fig.update_layout(title="총자산 추이", xaxis_title="시간", yaxis_title="자산 (KRW)", height=450)
st.plotly_chart(fig, use_container_width=True)

# RSI 그래프
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["time"], y=df["rsi"], mode="lines", name="RSI", line=dict(color="orange")))
fig2.add_hline(y=30, line_dash="dot", line_color="blue")
fig2.add_hline(y=70, line_dash="dot", line_color="red")
fig2.update_layout(title="RSI 추이 (4시간봉 기준)", xaxis_title="시간", yaxis_title="RSI", height=400)
st.plotly_chart(fig2, use_container_width=True)

# 최근 데이터
st.subheader("📋 최근 로그")
st.dataframe(df.tail(10))
