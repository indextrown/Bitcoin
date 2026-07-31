from __future__ import annotations

# ==========================
# V1 전략 시각화 도구
# ==========================
# 이 파일은 실제 매매를 수행하지 않습니다.
# 예시 데이터를 사용해서 V1 전략의 핵심 규칙을 그래프로 설명합니다.
#
# 포함 내용
# 1. 거래대금 상위 코인만 추리는 예시
# 2. MA5 > MA20 + RSI 반등 구간의 매수 예시
# 3. 익절 매도 예시
# 4. 손절 매도 예시
# 5. 추세 이탈 매도 예시
# 6. RSI 과열 후 꺾임 매도 예시

from pathlib import Path
import platform

import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "strategy_v1_explainer.png"
SELECTED_FONT_NAME = "sans-serif"


def configure_korean_font() -> None:
    """운영체제에 맞는 한글 폰트를 적용해 그래프 글자 깨짐을 방지합니다."""

    global SELECTED_FONT_NAME

    candidate_fonts_by_os = {
        "Darwin": ["AppleGothic", "NanumGothic", "Malgun Gothic"],
        "Windows": ["Malgun Gothic", "NanumGothic", "AppleGothic"],
        "Linux": ["NanumGothic", "Noto Sans CJK KR", "DejaVu Sans"],
    }

    system_name = platform.system()
    candidates = candidate_fonts_by_os.get(system_name, ["NanumGothic", "AppleGothic"])
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}

    for font_name in candidates:
        if font_name in available_fonts:
            SELECTED_FONT_NAME = font_name
            rcParams["font.family"] = font_name
            break
    else:
        SELECTED_FONT_NAME = "DejaVu Sans"
        rcParams["font.family"] = SELECTED_FONT_NAME

    # 한글 폰트 적용 시 마이너스 기호가 네모로 보이는 문제를 함께 방지합니다.
    rcParams["axes.unicode_minus"] = False


def make_series(values: list[float]) -> pd.DataFrame:
    """예시 종가 배열을 DataFrame으로 바꿉니다."""

    return pd.DataFrame({"close": values})


def add_indicators(df: pd.DataFrame, rsi_values: list[float] | None = None) -> pd.DataFrame:
    """차트 설명용 MA5, MA20, RSI 컬럼을 추가합니다."""

    result = df.copy()
    # 설명용 그래프는 처음부터 선이 보이도록 min_periods=1로 완화합니다.
    result["ma5"] = result["close"].rolling(5, min_periods=1).mean()
    result["ma20"] = result["close"].rolling(20, min_periods=1).mean()
    if rsi_values is None:
        result["rsi"] = np.nan
    else:
        result["rsi"] = rsi_values
    return result


def plot_price_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    event_index: int | None = None,
    event_label: str | None = None,
    event_color: str = "crimson",
) -> None:
    """가격과 이동평균선, 이벤트 화살표를 그립니다."""

    x = np.arange(len(df))
    ax.plot(x, df["close"], label="Close", color="#1f4e79", linewidth=2.2)
    ax.plot(x, df["ma5"], label="MA5", color="#f28e2b", linewidth=1.8)
    ax.plot(x, df["ma20"], label="MA20", color="#59a14f", linewidth=1.8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(alpha=0.25)
    ax.set_xlabel("Candle")
    ax.set_ylabel("Price")

    if event_index is not None and event_label is not None:
        event_price = float(df["close"].iloc[event_index])
        ax.scatter(event_index, event_price, color=event_color, s=60, zorder=5)
        ax.annotate(
            event_label,
            xy=(event_index, event_price),
            xytext=(event_index + 1, event_price * 1.03),
            arrowprops={"arrowstyle": "->", "color": event_color, "lw": 1.4},
            fontsize=9,
            color=event_color,
        )

    ax.legend(loc="best", fontsize=8)


def plot_rsi_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    entry_line: float = 35.0,
    exit_line: float = 70.0,
    event_index: int | None = None,
    event_label: str | None = None,
    event_color: str = "crimson",
) -> None:
    """RSI와 기준선을 그리고 이벤트를 표시합니다."""

    x = np.arange(len(df))
    ax.plot(x, df["rsi"], label="RSI", color="#7f3c8d", linewidth=2.0)
    ax.axhline(entry_line, color="#4e79a7", linestyle="--", linewidth=1.2, label="RSI 35")
    ax.axhline(exit_line, color="#e15759", linestyle="--", linewidth=1.2, label="RSI 70")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.25)
    ax.set_xlabel("Candle")
    ax.set_ylabel("RSI")

    if event_index is not None and event_label is not None:
        event_rsi = float(df["rsi"].iloc[event_index])
        ax.scatter(event_index, event_rsi, color=event_color, s=60, zorder=5)
        ax.annotate(
            event_label,
            xy=(event_index, event_rsi),
            xytext=(event_index + 1, min(95, event_rsi + 10)),
            arrowprops={"arrowstyle": "->", "color": event_color, "lw": 1.4},
            fontsize=9,
            color=event_color,
        )

    ax.legend(loc="best", fontsize=8)


def plot_top_coin_selection(ax: plt.Axes) -> None:
    """거래대금 상위 코인만 선택하는 과정을 막대그래프로 설명합니다."""

    tickers = [
        "KRW-BTC",
        "KRW-ETH",
        "KRW-SOL",
        "KRW-XRP",
        "KRW-DOGE",
        "KRW-ADA",
        "KRW-AVAX",
        "KRW-LINK",
        "KRW-DOT",
        "KRW-TRX",
        "KRW-ALT1",
        "KRW-ALT2",
    ]
    turnover = [980, 910, 860, 800, 760, 710, 690, 650, 620, 600, 120, 95]
    colors = ["#2e86ab" if i < 10 else "#cfcfcf" for i in range(len(tickers))]

    ax.bar(tickers, turnover, color=colors)
    ax.set_title("1. 거래대금 상위 10개 코인만 스캔", fontsize=11, fontweight="bold")
    ax.set_ylabel("Example Turnover")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.25)
    ax.annotate(
        "Top 10 채택",
        xy=(8.8, 620),
        xytext=(6.5, 900),
        arrowprops={"arrowstyle": "->", "color": "#2e86ab", "lw": 1.4},
        color="#2e86ab",
        fontsize=9,
    )
    ax.annotate(
        "거래량 부족으로 제외",
        xy=(10.6, 110),
        xytext=(8.6, 320),
        arrowprops={"arrowstyle": "->", "color": "#888888", "lw": 1.4},
        color="#666666",
        fontsize=9,
    )


def build_buy_example() -> pd.DataFrame:
    """상승 추세 + RSI 반등 매수 예시 데이터를 만듭니다."""

    close = [
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
        110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
        117, 116, 115, 116, 118, 120, 123, 126,
    ]
    rsi = [
        55, 56, 57, 58, 59, 60, 61, 60, 59, 58,
        57, 56, 54, 52, 50, 48, 45, 42, 39, 36,
        34, 31, 29, 33, 37, 42, 48, 54,
    ]
    return add_indicators(make_series(close), rsi)


def build_take_profit_example() -> pd.DataFrame:
    """익절 도달 후 매도하는 예시 데이터를 만듭니다."""

    close = [
        100, 101, 102, 103, 104, 105, 106, 108, 110, 112,
        114, 116, 118, 120, 121, 123, 125, 127, 129, 131,
        133, 135, 136, 137, 138,
    ]
    rsi = [
        44, 46, 48, 50, 52, 54, 55, 57, 59, 61,
        63, 64, 65, 66, 67, 68, 69, 70, 71, 72,
        73, 74, 72, 70, 68,
    ]
    return add_indicators(make_series(close), rsi)


def build_stop_loss_example() -> pd.DataFrame:
    """진입 후 -3% 이하로 밀리는 손절 예시 데이터를 만듭니다."""

    close = [
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
        110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
        120, 118, 116, 114, 112,
    ]
    rsi = [
        52, 53, 54, 55, 56, 57, 58, 58, 57, 56,
        55, 54, 53, 52, 50, 48, 46, 45, 44, 42,
        40, 37, 34, 30, 27,
    ]
    return add_indicators(make_series(close), rsi)


def build_trend_breakdown_example() -> pd.DataFrame:
    """MA5가 MA20 아래로 내려가는 추세 이탈 예시 데이터를 만듭니다."""

    close = [
        100, 102, 104, 106, 108, 110, 112, 114, 116, 118,
        120, 121, 122, 123, 124, 125, 126, 125, 123, 121,
        118, 115, 112, 110, 108, 106,
    ]
    rsi = [
        55, 56, 57, 58, 59, 60, 61, 62, 63, 64,
        65, 66, 66, 65, 64, 62, 60, 57, 53, 49,
        45, 41, 38, 35, 33, 31,
    ]
    return add_indicators(make_series(close), rsi)


def build_overbought_pullback_example() -> pd.DataFrame:
    """RSI 70 이상 과열 뒤 꺾이는 매도 예시 데이터를 만듭니다."""

    close = [
        100, 101, 103, 105, 108, 111, 114, 117, 120, 123,
        126, 129, 132, 135, 138, 140, 142, 143, 144, 145,
        144, 143, 142, 141, 140,
    ]
    rsi = [
        48, 50, 53, 56, 59, 62, 65, 68, 70, 72,
        74, 76, 78, 80, 82, 83, 84, 82, 79, 76,
        72, 69, 66, 63, 60,
    ]
    return add_indicators(make_series(close), rsi)


def build_figure() -> plt.Figure:
    """V1 전략 설명용 멀티 패널 이미지를 생성합니다."""

    plt.style.use("seaborn-v0_8-whitegrid")
    configure_korean_font()
    fig = plt.figure(figsize=(18, 12))
    grid = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.1, 1.1])

    ax1 = fig.add_subplot(grid[0, 0])
    plot_top_coin_selection(ax1)

    buy_df = build_buy_example()
    ax2 = fig.add_subplot(grid[0, 1])
    plot_price_panel(ax2, buy_df, "2. 매수 예시: MA5 > MA20 + RSI 반등", 24, "매수 진입", "#d62728")

    take_profit_df = build_take_profit_example()
    ax3 = fig.add_subplot(grid[1, 0])
    plot_price_panel(ax3, take_profit_df, "3. 익절 예시: 수익률 +5% 이상", 20, "익절 매도", "#2ca02c")

    stop_loss_df = build_stop_loss_example()
    ax4 = fig.add_subplot(grid[1, 1])
    plot_price_panel(ax4, stop_loss_df, "4. 손절 예시: 수익률 -3% 이하", 23, "손절 매도", "#d62728")

    trend_break_df = build_trend_breakdown_example()
    ax5 = fig.add_subplot(grid[2, 0])
    plot_price_panel(ax5, trend_break_df, "5. 추세 이탈 예시: MA5 < MA20", 23, "추세 이탈 매도", "#9467bd")

    overbought_df = build_overbought_pullback_example()
    ax6 = fig.add_subplot(grid[2, 1])
    plot_rsi_panel(ax6, overbought_df, "6. RSI 과열 후 꺾임 예시", event_index=21, event_label="과열 꺾임 매도", event_color="#ff7f0e")

    fig.suptitle("Bitcoin V1 Strategy Explainer", fontsize=18, fontweight="bold")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    return fig


def main() -> None:
    """설명용 이미지를 저장하고 화면에 표시합니다."""

    fig = build_figure()
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"font: {SELECTED_FONT_NAME}")
    print(f"saved: {OUTPUT_PATH}")
    plt.show()


if __name__ == "__main__":
    main()
