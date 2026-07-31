from __future__ import annotations

"""V2 전략 설명용 시각화 도구."""

from pathlib import Path
import argparse
import platform

import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "strategy_v2_explainer.png"
SELECTED_FONT_NAME = "sans-serif"


def configure_korean_font() -> None:
    """운영체제에 맞는 한글 폰트를 적용합니다."""

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

    rcParams["axes.unicode_minus"] = False


def make_ohlcv(
    closes: list[float],
    volumes: list[float],
    high_offset: float = 2.0,
    low_offset: float = 2.0,
) -> pd.DataFrame:
    """예시용 OHLCV 데이터프레임을 만듭니다."""

    rows = []
    for close, volume in zip(closes, volumes):
        rows.append(
            {
                "open": close - 1.0,
                "high": close + high_offset,
                "low": close - low_offset,
                "close": close,
                "volume": volume,
            }
        )
    return pd.DataFrame(rows)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """설명용 EMA와 거래량 평균 컬럼을 추가합니다."""

    result = df.copy()
    result["ema10"] = result["close"].ewm(span=10, adjust=False).mean()
    result["ema20"] = result["close"].ewm(span=20, adjust=False).mean()
    result["ema50"] = result["close"].ewm(span=50, adjust=False).mean()
    result["volume_ma20"] = result["volume"].rolling(20, min_periods=1).mean()
    return result


def plot_price_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    event_index: int | None = None,
    event_label: str | None = None,
    event_color: str = "crimson",
) -> None:
    """가격과 EMA, 이벤트 표시를 그립니다."""

    x = np.arange(len(df))
    ax.plot(x, df["close"], label="Close", color="#1f4e79", linewidth=2.2)
    ax.plot(x, df["ema10"], label="EMA10", color="#f28e2b", linewidth=1.7)
    ax.plot(x, df["ema20"], label="EMA20", color="#59a14f", linewidth=1.7)
    if "ema50" in df:
        ax.plot(x, df["ema50"], label="EMA50", color="#af7aa1", linewidth=1.5)
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


def plot_volume_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    event_index: int | None = None,
    event_label: str | None = None,
    event_color: str = "crimson",
) -> None:
    """거래량과 평균 거래량, 이벤트 표시를 그립니다."""

    x = np.arange(len(df))
    ax.bar(x, df["volume"], label="Volume", color="#76b7b2", alpha=0.8)
    ax.plot(x, df["volume_ma20"], label="Volume MA20", color="#e15759", linewidth=1.8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(alpha=0.25)
    ax.set_xlabel("Candle")
    ax.set_ylabel("Volume")

    if event_index is not None and event_label is not None:
        event_volume = float(df["volume"].iloc[event_index])
        ax.scatter(event_index, event_volume, color=event_color, s=60, zorder=5)
        ax.annotate(
            event_label,
            xy=(event_index, event_volume),
            xytext=(event_index + 1, event_volume * 1.1),
            arrowprops={"arrowstyle": "->", "color": event_color, "lw": 1.4},
            fontsize=9,
            color=event_color,
        )

    ax.legend(loc="best", fontsize=8)


def plot_top_coin_selection(ax: plt.Axes) -> None:
    """거래대금 상위 코인 선별을 막대그래프로 설명합니다."""

    tickers = [
        "KRW-BTC",
        "KRW-ETH",
        "KRW-SOL",
        "KRW-XRP",
        "KRW-DOGE",
        "KRW-ADA",
        "KRW-LINK",
        "KRW-SUI",
        "KRW-AVAX",
        "KRW-TRX",
        "KRW-ALT1",
        "KRW-ALT2",
    ]
    turnover = [980, 930, 890, 850, 800, 760, 710, 690, 660, 640, 180, 120]
    colors = ["#2e86ab" if i < 10 else "#d9d9d9" for i in range(len(tickers))]

    ax.bar(tickers, turnover, color=colors)
    ax.set_title("1. 거래대금 상위 코인만 스캔", fontsize=11, fontweight="bold")
    ax.set_ylabel("Example Turnover")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.25)


def build_bull_trend_example() -> pd.DataFrame:
    """일봉 EMA20 > EMA50 추세 예시를 만듭니다."""

    closes = [100 + i * 1.4 for i in range(60)]
    volumes = [1000 + (i % 5) * 40 for i in range(60)]
    return add_indicators(make_ohlcv(closes, volumes))


def build_breakout_example() -> pd.DataFrame:
    """돌파 + 거래량 급증 매수 예시를 만듭니다."""

    closes = [
        100, 99, 98, 97, 96, 95, 96, 97, 98, 99,
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
        110, 111, 112, 113, 114, 115, 116, 117, 118, 126,
    ]
    volumes = [1000] * 29 + [2600]
    df = make_ohlcv(closes, volumes, high_offset=2.5, low_offset=2.0)
    df.loc[df.index[-2], "high"] = 123.0
    df.loc[df.index[-1], "high"] = 129.0
    return add_indicators(df)


def build_stop_loss_example() -> pd.DataFrame:
    """손절 예시를 만듭니다."""

    closes = [
        126, 127, 128, 129, 130, 129, 128, 126, 123, 120,
        118, 116, 114, 112, 110, 108, 107, 106, 105, 104,
    ]
    volumes = [1500] * 20
    return add_indicators(make_ohlcv(closes, volumes))


def build_trend_breakdown_example() -> pd.DataFrame:
    """EMA10 < EMA20 추세 이탈 예시를 만듭니다."""

    closes = [
        110, 112, 114, 116, 118, 120, 122, 123, 124, 125,
        124, 123, 121, 119, 117, 115, 113, 111, 109, 107,
    ]
    volumes = [1400] * 20
    return add_indicators(make_ohlcv(closes, volumes))


def build_momentum_fade_example() -> pd.DataFrame:
    """과열 후 꺾임 예시를 만듭니다."""

    closes = [
        100, 102, 104, 107, 110, 113, 116, 119, 122, 125,
        128, 131, 134, 137, 140, 142, 143, 144, 143, 141,
    ]
    volumes = [1200, 1250, 1300, 1350, 1400, 1500, 1600, 1700, 1850, 2000,
               2100, 2200, 2300, 2350, 2400, 2300, 2200, 2100, 2000, 1900]
    return add_indicators(make_ohlcv(closes, volumes))


def build_figure() -> plt.Figure:
    """V2 전략 설명용 멀티 패널 이미지를 생성합니다."""

    plt.style.use("seaborn-v0_8-whitegrid")
    configure_korean_font()
    fig = plt.figure(figsize=(18, 12))
    grid = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.05, 1.05])

    ax1 = fig.add_subplot(grid[0, 0])
    plot_top_coin_selection(ax1)

    trend_df = build_bull_trend_example()
    ax2 = fig.add_subplot(grid[0, 1])
    plot_price_panel(ax2, trend_df, "2. 일봉 추세 필터: EMA20 > EMA50", 55, "상승 추세 유지", "#2ca02c")

    breakout_df = build_breakout_example()
    ax3 = fig.add_subplot(grid[1, 0])
    plot_price_panel(ax3, breakout_df, "3. 4시간봉 돌파 진입", 29, "브레이크아웃 매수", "#d62728")

    ax4 = fig.add_subplot(grid[1, 1])
    plot_volume_panel(ax4, breakout_df, "4. 거래량 급증 확인", 29, "거래량 확인", "#ff7f0e")

    stop_df = build_stop_loss_example()
    ax5 = fig.add_subplot(grid[2, 0])
    plot_price_panel(ax5, stop_df, "5. 손절 또는 브레이크아웃 실패", 12, "리스크 정리", "#d62728")

    trend_break_df = build_trend_breakdown_example()
    ax6 = fig.add_subplot(grid[2, 1])
    plot_price_panel(ax6, trend_break_df, "6. EMA10 < EMA20 추세 이탈", 16, "추세 이탈 매도", "#9467bd")

    fig.suptitle("Bitcoin V2 Strategy Explainer", fontsize=18, fontweight="bold")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    return fig


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱합니다."""

    parser = argparse.ArgumentParser(description="Generate the V2 explainer image.")
    parser.add_argument("--show", action="store_true", help="Open the figure window after saving.")
    return parser.parse_args()


def main() -> None:
    """설명용 이미지를 저장하고 필요 시 화면에 표시합니다."""

    args = parse_args()
    fig = build_figure()
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"font: {SELECTED_FONT_NAME}")
    print(f"saved: {OUTPUT_PATH}")
    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
