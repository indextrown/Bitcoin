from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
GMAIL_ADDRESS = "indextrown@gmail.com"
TO_EMAIL = "indextrown@gmail.com"

import pyupbit  # 업비트 라이브러리
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

load_dotenv()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD").replace(" ", "")

def get_bitcoin_chart():
    # 오늘 비트코인 15분봉 데이터 가져오기
    df = pyupbit.get_ohlcv("KRW-BTC", interval="minute15", count=50)  # 최근 50개 캔들
    
    # 차트 그리기
    plt.figure(figsize=(10,5))
    plt.plot(df.index, df["close"], label="BTC/KRW (15m)")
    plt.title("오늘 비트코인 15분봉")
    plt.xlabel("시간")
    plt.ylabel("가격 (KRW)")
    plt.legend()
    plt.grid(True)
    
    # PNG 저장
    chart_path = "btc_chart.png"
    plt.savefig(chart_path)
    plt.close()
    return chart_path

def send_gmail(subject, body, image_path=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = TO_EMAIL
        msg['Subject'] = subject

        # 텍스트 본문 추가
        msg.attach(MIMEText(body, 'plain'))

        # 이미지 첨부 (옵션)
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                img_data = f.read()
                image = MIMEImage(img_data, name=os.path.basename(image_path))
                msg.attach(image)

        # Gmail 서버 접속
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        print("✅ 메일 전송 완료")

    except Exception as e:
        print("❌ 메일 전송 실패:", e)


# send_gmail("제목", "테스트")
# send_gmail("제목", "본문 내용", "cat.png")  # sample.png 이미지 첨부

# 실행 예시
# chart = get_bitcoin_chart()
# send_gmail("오늘의 비트코인 차트", "비트코인 15분봉 차트입니다.", chart)



#################################################################################
def calculate_rsi(series, period=14):
    """RSI 계산 함수"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_coin_chart(
    ticker="KRW-BTC",
    interval="minute15",
    count=100,
    ma1=5,
    ma2=20,
    rsi_interval="minute60",     # ✅ RSI는 별도 interval로 계산 가능
    rsi_label_interval=1         # ✅ RSI 차트 x축 라벨 표시 간격(시간 단위)
):
    """
    코인 차트를 그려 PNG로 저장하고 경로를 반환합니다.
    - 가격 차트: interval 기준
    - MA1, MA2 표시
    - RSI(14): rsi_interval 기준
    """

    # 메인 차트 데이터
    df = pyupbit.get_ohlcv(ticker, interval=interval, count=count)
    if df is None or df.empty:
        raise ValueError(f"데이터를 불러오지 못했습니다: {ticker}, {interval}")

    # 이동평균선 계산
    df[f"MA{ma1}"] = df["close"].rolling(ma1).mean()
    df[f"MA{ma2}"] = df["close"].rolling(ma2).mean()

    # RSI 데이터 (사용자가 지정한 interval)
    df_rsi = pyupbit.get_ohlcv(ticker, interval=rsi_interval, count=count)
    df_rsi["RSI"] = calculate_rsi(df_rsi["close"], period=14)

    # ✅ Subplot 구성 (가격 + RSI)
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12,8), sharex=False,
        gridspec_kw={'height_ratios': [3,1]}
    )

    # ① 가격 차트
    ax1.plot(df.index, df["close"], label=f"{ticker} ({interval})", color="black")
    ax1.plot(df.index, df[f"MA{ma1}"], linestyle="--", label=f"MA{ma1}", color="blue")
    ax1.plot(df.index, df[f"MA{ma2}"], linestyle="--", label=f"MA{ma2}", color="purple")
    ax1.set_title(f"{ticker} {interval} 차트 + RSI({rsi_interval})")
    ax1.set_ylabel("가격 (KRW)")
    ax1.legend()
    ax1.grid(True)

    # 가격 차트 x축: 1시간 간격
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    # ② RSI 차트
    ax2.plot(df_rsi.index, df_rsi["RSI"], linestyle="--", color="red", label=f"RSI(14, {rsi_interval})")
    ax2.axhline(70, color="gray", linestyle="--", linewidth=0.7)
    ax2.axhline(30, color="gray", linestyle="--", linewidth=0.7)
    ax2.set_ylabel("RSI")
    ax2.set_ylim(0, 100)
    ax2.legend()
    ax2.grid(True)

    # RSI 차트 x축: 기본 6시간 간격
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=rsi_label_interval))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()

    # PNG 저장
    chart_path = f"{ticker.replace('-', '_')}_{interval}_with_rsi.png"
    plt.savefig(chart_path, dpi=300, bbox_inches="tight")
    plt.close()

    return chart_path

# ETH 15분봉 + RSI(60분봉)
# chart = get_coin_chart("KRW-ETH", interval="minute15", rsi_interval="minute60")

# send_gmail("오늘의 ETH 차트", "ETH 15분봉 차트입니다.", chart)


#################################################################################



def get_coin_chart2(
    ticker="KRW-BTC",
    interval="minute15",
    count=100,
    ma1=5,
    ma2=20,
    rsi_interval="minute60",
    rsi_label_interval=1,
    pos_before3=-3,    # MA5 before3 찍을 위치
    pos_before2=-2,    # MA5 before2 찍을 위치
    pos_now=-1,        # MA5 now 찍을 위치
    buy_pos=-1,        # 매수 체결가 위치
    sell_pos=-1,       # 지정가 매도 위치
    buy_price=None,    # 매수 체결가 (초록 ▲)
    target_sell_price=None  # 지정가 매도 단가 (파랑 ▼)
):
    """
    코인 차트를 그려 PNG로 저장하고 경로를 반환합니다.
    - MA5: 갈색2개(-3, -2), 초록점(-1)
    - 매수 단가: 초록 삼각형 ▲ (buy_pos 위치)
    - 지정가 매도 단가: 파란 삼각형 ▼ (sell_pos 위치)
    """

    def calculate_rsi(series, period=14):
        """RSI 계산 함수"""
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    # 메인 차트 데이터
    df = pyupbit.get_ohlcv(ticker, interval=interval, count=count)
    if df is None or df.empty:
        raise ValueError(f"데이터를 불러오지 못했습니다: {ticker}, {interval}")

    # 이동평균선 계산
    df[f"MA{ma1}"] = df["close"].rolling(ma1, min_periods=1).mean()
    df[f"MA{ma2}"] = df["close"].rolling(ma2, min_periods=1).mean()

    # RSI 데이터
    df_rsi = pyupbit.get_ohlcv(ticker, interval=rsi_interval, count=count)
    df_rsi["RSI"] = calculate_rsi(df_rsi["close"], period=14)

    # ✅ Subplot 구성
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12,8), sharex=False,
        gridspec_kw={'height_ratios': [3,1]}
    )

    # ① 가격 차트
    ax1.plot(df.index, df["close"], label=f"{ticker} ({interval})", color="black")
    ax1.plot(df.index, df[f"MA{ma1}"], linestyle="--", label=f"MA{ma1}", color="blue")
    ax1.plot(df.index, df[f"MA{ma2}"], linestyle="--", label=f"MA{ma2}", color="purple")
    ax1.set_title(f"{ticker} {interval} 차트 + RSI({rsi_interval})")
    ax1.set_ylabel("가격 (KRW)")
    ax1.legend()
    ax1.grid(True)

    ma5_series = df[f"MA{ma1}"].dropna()

    # 📍 MA5 포인트
    if len(ma5_series) >= abs(pos_before3):
        ax1.scatter(ma5_series.index[pos_before3], ma5_series.iloc[pos_before3],
                    color="brown", s=60, zorder=5, label="MA5_before3")
    if len(ma5_series) >= abs(pos_before2):
        ax1.scatter(ma5_series.index[pos_before2], ma5_series.iloc[pos_before2],
                    color="brown", s=60, zorder=5, label="MA5_before2")
    if len(ma5_series) >= abs(pos_now):
        ax1.scatter(ma5_series.index[pos_now], ma5_series.iloc[pos_now],
                    color="lime", s=80, zorder=5, label="MA5_now")

    # 📍 매수/지정가 매도 포인트
    if buy_price is not None and len(df) >= abs(buy_pos):
        ax1.scatter(df.index[buy_pos], buy_price,
                    color="lime", s=120, zorder=5, marker="^", label="매수")
    if target_sell_price is not None and len(df) >= abs(sell_pos):
        ax1.scatter(df.index[sell_pos], target_sell_price,
                    color="blue", s=120, zorder=5, marker="v", label="지정가매도")

    # 가격 차트 x축
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    # ② RSI 차트
    ax2.plot(df_rsi.index, df_rsi["RSI"], linestyle="--", color="red", label=f"RSI(14, {rsi_interval})")
    ax2.axhline(70, color="gray", linestyle="--", linewidth=0.7)
    ax2.axhline(30, color="gray", linestyle="--", linewidth=0.7)
    ax2.set_ylabel("RSI")
    ax2.set_ylim(0, 100)
    ax2.legend()
    ax2.grid(True)

    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=rsi_label_interval))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()

    # PNG 저장
    chart_path = f"{ticker.replace('-', '_')}_{interval}_with_rsi.png"
    plt.savefig(chart_path, dpi=300, bbox_inches="tight")
    plt.close()

    return chart_path



chart = get_coin_chart2(
    "KRW-ETH",
    interval="minute15",
    rsi_interval="minute60",
    pos_before3=-7,
    pos_before2=-6,
    pos_now=-5,
    buy_pos=-5,
    sell_pos=-5,
    buy_price=6081200,        # 실제 매수 체결가
    target_sell_price=6142000 # 지정가 매도 가격
)


send_gmail("오늘의 ETH 차트", "ETH 15분봉 차트입니다.", chart)