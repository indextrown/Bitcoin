from __future__ import annotations

# ==========================
# V0 전략 시각화 도구
# ==========================
# 이 파일은 실제 주문을 넣지 않습니다.
# V0의 단일 코인 RSI 전략을 예시 그래프로 설명합니다.
#
# 포함 내용
# 1. 단일 코인만 추적하는 구조
# 2. RSI 30 이하 매수 예시
# 3. RSI 70 이상 + 수익 5% 익절 예시
# 4. RSI 70 이상 + 본전/손실 정리 예시

from pathlib import Path
import platform

import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams
import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "strategy_v0_explainer.png"
SELECTED_FONT_NAME = "sans-serif"


def configure_korean_font() -> None:
    """운영체제별 한글 폰트를 적용합니다."""

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


def make_series(values: list[float]) -> pd.DataFrame:
    """예시 종가 배열을 DataFrame으로 바꿉니다."""

    return pd.DataFrame({"close": values})


def add_indicators(df: pd.DataFrame, rsi_values: list[float]) -> pd.DataFrame:
    """설명용 MA5, MA20, RSI 컬럼을 추가합니다."""

    result = df.copy()
    result["ma5"] = result["close"].rolling(5, min_periods=1).mean()
    result["ma20"] = result["close"].rolling(20, min_periods=1).mean()
    result["rsi"] = rsi_values
    return result


def plot_price_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    event_index: int,
    event_label: str,
    event_color: str,
) -> None:
    """가격 패널과 매수/매도 화살표를 그립니다."""

    x = np.arange(len(df))
    ax.plot(x, df["close"], label="Close", color="#1f4e79", linewidth=2.2)
    ax.plot(x, df["ma5"], label="MA5", color="#f28e2b", linewidth=1.7)
    ax.plot(x, df["ma20"], label="MA20", color="#59a14f", linewidth=1.7)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlabel("Candle")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.25)

    event_price = float(df["close"].iloc[event_index])
    ax.scatter(event_index, event_price, color=event_color, s=70, zorder=5)
    ax.annotate(
        event_label,
        xy=(event_index, event_price),
        xytext=(event_index + 1, event_price * 1.04),
        arrowprops={"arrowstyle": "->", "color": event_color, "lw": 1.5},
        fontsize=9,
        color=event_color,
    )
    ax.legend(loc="best", fontsize=8)


def plot_rsi_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    title: str,
    event_index: int,
    event_label: str,
    event_color: str,
) -> None:
    """RSI 패널과 기준선, 이벤트 화살표를 그립니다."""

    x = np.arange(len(df))
    ax.plot(x, df["rsi"], label="RSI", color="#7f3c8d", linewidth=2.0)
    ax.axhline(30, color="#4e79a7", linestyle="--", linewidth=1.2, label="RSI 30")
    ax.axhline(70, color="#e15759", linestyle="--", linewidth=1.2, label="RSI 70")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlabel("Candle")
    ax.set_ylabel("RSI")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.25)

    event_rsi = float(df["rsi"].iloc[event_index])
    ax.scatter(event_index, event_rsi, color=event_color, s=70, zorder=5)
    ax.annotate(
        event_label,
        xy=(event_index, event_rsi),
        xytext=(event_index + 1, min(95, event_rsi + 10)),
        arrowprops={"arrowstyle": "->", "color": event_color, "lw": 1.5},
        fontsize=9,
        color=event_color,
    )
    ax.legend(loc="best", fontsize=8)


def plot_single_ticker_concept(ax: plt.Axes) -> None:
    """V0가 단일 코인만 추적하는 구조를 시각적으로 설명합니다."""

    labels = ["KRW-ETH", "KRW-BTC", "KRW-SOL", "KRW-XRP"]
    values = [1.0, 0.0, 0.0, 0.0]
    colors = ["#2e86ab", "#d9d9d9", "#d9d9d9", "#d9d9d9"]

    ax.bar(labels, values, color=colors)
    ax.set_ylim(0, 1.2)
    ax.set_title("1. V0는 단일 코인 1개만 추적", fontsize=11, fontweight="bold")
    ax.set_ylabel("Watch")
    ax.grid(axis="y", alpha=0.25)
    ax.annotate(
        "이 코인만 계속 확인",
        xy=(0, 1.0),
        xytext=(0.7, 0.9),
        arrowprops={"arrowstyle": "->", "color": "#2e86ab", "lw": 1.5},
        color="#2e86ab",
        fontsize=9,
    )


def build_buy_example() -> pd.DataFrame:
    """RSI 30 이하 매수 예시 데이터를 만듭니다."""

    close = [
        120, 119, 118, 117, 116, 115, 114, 113, 112, 111,
        110, 109, 108, 107, 106, 105, 104, 103, 102, 101,
        100, 99, 98, 97, 98, 99, 100,
    ]
    rsi = [
        52, 50, 48, 46, 44, 42, 40, 38, 36, 35,
        34, 33, 32, 31, 30, 29, 28, 27, 26, 25,
        24, 24, 25, 27, 30, 34, 38,
    ]
    return add_indicators(make_series(close), rsi)


def build_take_profit_example() -> pd.DataFrame:
    """RSI 70 이상에서 +5% 수익 익절 예시 데이터를 만듭니다."""

    close = [
        100, 101, 102, 103, 104, 105, 106, 108, 110, 112,
        114, 116, 118, 120, 121, 123, 124, 126, 128, 130,
        132, 134, 135, 136, 137,
    ]
    rsi = [
        44, 46, 48, 50, 52, 54, 56, 58, 60, 62,
        64, 66, 68, 69, 70, 72, 73, 74, 75, 76,
        77, 78, 77, 76, 75,
    ]
    return add_indicators(make_series(close), rsi)


def build_flat_or_loss_example() -> pd.DataFrame:
    """RSI 70 이상이지만 수익이 없어서 정리하는 예시 데이터를 만듭니다."""

    close = [
        100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
        110, 111, 112, 113, 114, 113, 112, 111, 110, 109,
        108, 107, 106, 105, 104,
    ]
    rsi = [
        46, 48, 50, 52, 54, 56, 58, 60, 62, 64,
        66, 68, 70, 72, 74, 75, 74, 73, 72, 71,
        70, 69, 68, 66, 64,
    ]
    return add_indicators(make_series(close), rsi)


def build_figure() -> plt.Figure:
    """V0 전략 설명용 멀티 패널 이미지를 생성합니다."""

    plt.style.use("seaborn-v0_8-whitegrid")
    configure_korean_font()
    fig = plt.figure(figsize=(16, 10))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0])

    ax1 = fig.add_subplot(grid[0, 0])
    plot_single_ticker_concept(ax1)

    buy_df = build_buy_example()
    ax2 = fig.add_subplot(grid[0, 1])
    plot_rsi_panel(ax2, buy_df, "2. 매수 예시: RSI 30 이하", 22, "분할 매수", "#d62728")

    take_profit_df = build_take_profit_example()
    ax3 = fig.add_subplot(grid[1, 0])
    plot_price_panel(ax3, take_profit_df, "3. 매도 예시: RSI 70 이상 + 수익 5%", 20, "익절 매도", "#2ca02c")

    flat_or_loss_df = build_flat_or_loss_example()
    ax4 = fig.add_subplot(grid[1, 1])
    plot_price_panel(ax4, flat_or_loss_df, "4. 매도 예시: RSI 70 이상 + 본전/손실", 18, "정리 매도", "#d62728")

    fig.suptitle("Bitcoin V0 Strategy Explainer", fontsize=18, fontweight="bold")
    fig.tight_layout(rect=[0, 0.02, 1, 0.96])
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
