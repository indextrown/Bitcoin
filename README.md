## Clone
```bash
git clone https://github.com/indextrown/Bitcoin.git
cd Bitcoin
```

## Work
```bash
# 브랜치 생성
git checkout -b feature/기능이름

# 작업 후 push
git add .
git commit -m "feat: 기능 설명"
git push origin feature/기능이름
```

## 원격 저장소 동기화
```bash
# 다른 팀원의 원격 변경사항을 현재 브랜치에 반영
make pull

# 모든 변경사항을 stage한 뒤 "update" 메시지로 커밋하고 push
make push

# 원격 변경사항을 먼저 반영한 뒤, 로컬 변경사항을 커밋하고 push
make update
```

## Setting
```bash
# 1. Python 버전 설치 (최초 1회)
pyenv install 3.11.9

# 2. 프로젝트 Python 버전 지정
pyenv local 3.11.9

# 3. 가상환경 생성
python3 -m venv .venv

# 4. 가상환경 활성화 (Linux & macOS)
source .venv/bin/activate

# 4-1. 가상환경 활성화 (Windows)
.venv\Scripts\activate

# 5. 라이브러리 설치
pip install -r requirements.txt

# 6. 가상환경 비활성화
deactivate
```

## 이미 pyenv 환경이 있는 경우
```bash
# 1. 프로젝트 폴더 이동
cd Bitcoin

# 2. pyenv로 Python 버전 지정
pyenv local 3.10.12

# 3. (이미 만들어진 가상환경 사용)
pyenv activate bitcoin-venv

# 4. 라이브러리 설치 (최초 1회)
pip install -r requirements.txt

# 5. 작업 후 비활성화
pyenv deactivate
```

## 트레이딩과 백테스트 개념

이 프로젝트는 업비트의 과거 가격 데이터로 전략을 검증하고, 같은 판단 로직을 실제 봇에서도
재사용합니다. 아래 개념을 알면 V3·V4 전략과 백테스트 PNG를 읽기 쉬워집니다. 전략별 숫자와
매매 규칙은 [V3 설명](develop/v3/README.md), [V4 설명](develop/v4/README.md),
[V5 설명](develop/v5/README.md)에서 확인하세요.

### 티커와 캔들

| 용어 | 뜻 |
| --- | --- |
| 티커 | 거래할 마켓 이름입니다. `KRW-ETH`는 원화(KRW)로 이더리움(ETH)을 거래한다는 뜻입니다. |
| 캔들 | 일정 시간 동안의 가격 움직임을 한 줄로 묶은 데이터입니다. 시가·고가·저가·종가를 담습니다. |
| 분봉 | 분 단위 캔들입니다. `minute60`은 1시간봉, `minute240`은 4시간봉입니다. |
| OHLCV | 시가(Open), 고가(High), 저가(Low), 종가(Close), 거래량(Volume)을 묶어 부르는 이름입니다. |

V3·V4의 기본 전략 봉은 4시간봉입니다. RSI는 주로 이 4시간봉의 종가로 계산합니다. 백테스트는
크론 실행 시점을 재현하려고 4시간봉보다 짧은 원본 봉을 함께 사용합니다. 예를 들어 60분마다
실행한다고 가정하면 `minute60` 데이터를 모아, 그 시점까지 만들어진 4시간봉 상태를 계산합니다.

### RSI와 매매 신호

RSI(Relative Strength Index)는 최근 가격이 오른 힘과 내린 힘을 비교한 0~100 사이의 지표입니다.
보통 RSI가 낮으면 과매도 구간, 높으면 과매수 구간으로 해석합니다. 다만 RSI 하나만으로 다음 가격이
오르거나 내린다고 단정할 수는 없습니다. V3·V4는 RSI를 주문 여부를 판단하는 하나의 신호로 사용합니다.

| 용어 | 뜻 |
| --- | --- |
| RSI(14) | 최근 14개 전략 봉으로 계산한 RSI입니다. 괄호 안 숫자는 계산에 사용하는 봉 수입니다. |
| 매수 임계값 | RSI가 이 값 이하 또는 위로 회복했을 때 매수를 검토하는 기준입니다. |
| 매도 임계값 | RSI가 이 값 이상일 때 매도를 검토하는 기준입니다. |
| 이전 RSI | 현재 전략 봉 바로 전 전략 봉의 RSI입니다. V4의 RSI 회복 매수 조건에 사용합니다. |
| 신호 | `decide_trade()`가 RSI·잔고·평균 매수가를 보고 내린 `BUY`, `SELL`, `WAIT` 같은 판단입니다. |

신호가 곧 체결은 아닙니다. 실제 주문은 잔고, 최소 주문 금액, 거래소 응답을 모두 통과해야 합니다.
백테스트도 같은 이유로 신호 다음 원본 봉의 시가에 체결된 것으로 계산합니다.

### 주문과 수익률

| 용어 | 뜻 |
| --- | --- |
| 시장가 주문 | 가격을 미리 지정하지 않고, 당시 시장 가격으로 바로 매수하거나 매도하는 주문입니다. |
| 분할매수 | 원화 전액을 한 번에 쓰지 않고, 정해진 비율만 여러 번 나누어 매수하는 방식입니다. V3는 기본 20%입니다. |
| 전량 매도 | 보유한 해당 코인을 모두 매도하는 방식입니다. |
| 평균 매수가 | 여러 번 매수했을 때 보유 물량의 평균 매입 단가입니다. |
| 수익률 | 평균 매수가와 현재 가격의 차이를 비율로 나타낸 값입니다. 수수료를 고려하면 실제 수익률은 달라질 수 있습니다. |
| 익절 | 정한 수익률 이상이 되었을 때 수익을 확정하는 매도입니다. |
| 손절 | 정한 손실률 이하가 되었을 때 손실을 제한하는 매도입니다. |
| 최소 주문 금액 | 거래소가 주문을 받는 최소 원화 금액입니다. 기본값은 5,000 KRW입니다. |

V3 그래프의 `sell at break-even/loss`는 RSI가 매도 기준 이상인 시점에 수익률이 0% 이하라서
전량 매도한 경우를 뜻합니다. 단순히 손실이 났다는 이유만으로 즉시 파는 것이 아니라, V3의 RSI
매도 조건도 함께 만족해야 합니다.

### 실제 실행과 백테스트

| 구분 | 실제 봇 | 백테스트 |
| --- | --- | --- |
| 실행 시점 | 서버의 crontab이 `btc_bot.py`를 실행합니다. | `cron_interval_minutes`로 실행 주기를 가정합니다. |
| 가격 데이터 | 실행 시점에 업비트 API에서 최근 OHLCV를 조회합니다. | 업비트의 과거 OHLCV를 조회하고 로컬 캐시를 재사용합니다. |
| 주문 | 업비트에 실제 시장가 주문을 요청합니다. | 다음 원본 봉 시가, 수수료, 최소 주문 금액을 가정해 계산합니다. |
| 목적 | 현재 설정으로 실제 매매를 실행합니다. | 과거 구간에서 전략의 동작과 위험을 검토합니다. |

백테스트의 크론 주기는 실제 봇 설정이 아닙니다. 실제 서버는 30분, 1시간처럼 원하는 주기로
crontab을 설정할 수 있고, 백테스트에서는 그 주기를 가정해 결과가 어떻게 달라지는지 확인합니다.
실행 횟수가 줄면 신호를 확인하는 횟수와 가능한 체결 수도 함께 줄 수 있습니다.

PNG의 `equity`는 그 시점의 총자산입니다. 원화 잔고에 보유 코인을 당시 종가로 환산한 금액을 더해
계산합니다. 그래프가 한 줄로 평평하면 보통 아직 체결이 없었거나, 보유 코인이 없어서 가격 변화가
총자산에 반영되지 않은 상태입니다. `final equity`는 마지막 시점의 총자산, `total return`은 시작
원금 대비 수익률, `trades`는 백테스트에서 실제 체결된 주문 수입니다. 최대 낙폭(max drawdown)은
백테스트 중 총자산이 가장 높았던 시점에서 가장 크게 떨어진 비율입니다.

과거 백테스트 결과는 미래 수익이나 실제 주문 성과를 보장하지 않습니다. 기간을 나누어 다시 검증하고,
수수료·체결 차이·최대 낙폭을 함께 확인한 뒤에만 실제 crontab 등록 여부를 결정하세요.

## 폴더 구조

```text
develop/
  v0/  # 초기 운영 코드
  v1/  # V1 전략과 봇
  v2/  # V2 전략과 봇
  v3/  # V3 전략, 봇, 전용 백테스트
  v4/  # V4 RSI 회복 전략, 봇, 연구 도구, 전용 백테스트
  v4_1/  # V4.1 추세 필터 RSI 회복 전략, 봇, 연구 도구, 전용 백테스트
  v5/  # V4와 독립 운영하는 BTC 5분봉 반등 단타 봇과 전용 백테스트
backtesting/
  v2/  # V2 연구 노트북과 문서
```

## 유닛 테스트
```bash
# 버전별 및 공용 테스트 실행
python -m unittest discover -s develop/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v0/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v1/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v2/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v3/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v3/backtesting/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v4/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v4_1/tests -p 'test_*.py' -v
python -m unittest discover -s develop/v5/tests -p 'test_*.py' -v
python -m unittest discover -s backtesting/tests -p 'test_*.py' -v
```

## 전략 비교 백테스트
```bash
# V1, V2 전략을 같은 티커 구간에서 비교
python backtesting/backtest_v1_v2.py --ticker KRW-BTC --day-count 180 --signal-count 360
```

## V3 백테스트 시각화
```bash
# 기본 V3 설정으로 PNG 생성
make backtest v3

# 특정 시작일부터 최신 데이터까지 PNG 생성
make backtest v3 FROM=2026-01-01

# 특정 시작일·종료일(둘 다 포함)로 PNG 생성
make backtest v3 FROM=2026-01-01 TO=2026-06-30

# 실제 매수·매도 체결 지점의 RSI를 파란·빨간 점으로 표시
make backtest v3 SHOW_RSI_SIGNAL_POINTS=1

# 가격 차트의 매수·매도 지점, RSI, 자산 곡선을 PNG로 저장
python3 develop/v3/backtesting/backtest_visualizer.py --ticker KRW-ETH --interval minute240 --count 200

# 30분마다 봇이 실행됐다고 가정해 비교 (기본값도 30분)
python3 develop/v3/backtesting/backtest_visualizer.py --cron-interval-minutes 30

# 특정 시작일부터 최신 데이터까지 조회
python3 develop/v3/backtesting/backtest_visualizer.py --from 2026-01-01

# 특정 시작일·종료일(둘 다 포함)만 조회
python3 develop/v3/backtesting/backtest_visualizer.py --from 2026-01-01 --to 2026-06-30

# 실제 매수·매도 체결 지점의 RSI를 파란·빨간 점으로 표시
python3 develop/v3/backtesting/backtest_visualizer.py --show-rsi-signal-points
```

- 공용 V3 설정은 `develop/v3/config.py`에서 변경합니다. 봇, 백테스트, PNG 표시값이 같은 설정을 사용합니다.
- `BacktestConfig.cron_interval_minutes`는 백테스트 전용 실행 주기 가정입니다. 실제 봇의 주기는 crontab에서 정하며, `btc_bot.py`는 이 값을 사용하지 않습니다.
- 백테스트는 크론 주기에 맞는 더 짧은 원본 봉과 업비트 전략 봉의 실제 시작 시각을 사용합니다. 각 원본 봉이 끝난 시점에 전략 봉을 재구성하고, 그 순간의 다음 원본 봉 시가에 체결된다고 가정합니다.
- `--from`은 포함할 시작일, `--to`는 포함할 마지막 날짜입니다. 기간을 지정하면 그 전 RSI 준비용 데이터는 내부 계산에만 사용하고 PNG·가상 자산은 지정한 기간만 표시합니다.
- 원본 OHLCV는 `develop/v3/backtesting/cache/`에 티커·원본 봉 간격별 CSV와 조회 완료 범위 메타데이터(JSON)로 저장하며 Git에는 포함하지 않습니다. 다음 실행에서는 캐시에 없는 앞·뒤 구간만 업비트 API로 받습니다. 거래소가 체결 없는 시각의 봉을 생략해도 이미 조회한 시간은 다시 호출하지 않습니다. 완료된 과거 봉만 저장하므로, 최신 진행 중 봉은 캐시하지 않습니다.
- 기본 시작 자금은 1,000,000원이며, 수수료 가정은 주문당 0.05%입니다.

## V4 RSI 회복 전략

```bash
# V4 기본 설정으로 PNG 생성 (기본: 2026-01-01부터 최신 완료 봉까지)
make backtest v4

# 기간과 실제 체결 RSI 점을 지정해 PNG 생성
make backtest v4 FROM=2026-01-01 TO=2026-08-02 SHOW_RSI_SIGNAL_POINTS=1

# V4 후보 조합을 같은 수수료·다음 봉 시가 체결 가정으로 빠르게 비교
python3 develop/v4/research.py --from 2026-01-01 --to 2026-08-02 --cron-interval-minutes 60

# 실제 주문을 실행하는 V4 봇 — 서버 crontab에 등록하기 전 반드시 백테스트를 검토
python3 develop/v4/btc_bot.py
```

- V4는 RSI가 40 아래에서 위로 회복할 때 전액 진입하고, +3% 익절·-10% 손절·RSI 75 이상 청산을 사용합니다.
- V4 백테스트 기본 크론 가정은 60분이며, 실제 실행 주기는 서버 crontab에서 정합니다.
- V4 연구 도구는 현재 기간 수익률만 최대화하지 않도록 앞 기간으로 후보를 고르고 뒷 기간도 따로 비교합니다. 백테스트 수익은 미래 수익이나 실거래 성과를 보장하지 않습니다.
- V4도 V3와 동일한 원본 OHLCV CSV 캐시를 재사용합니다. 전략 결과는 캐시하지 않습니다.

## V4.1 추세 필터 RSI 회복 전략

```bash
# V4.1 PNG 생성: 기본값은 RSI 40 회복 + 현재가 SMA(50) 위 + +3% 익절·-5% 손절
make backtest v4_1

# 기간과 실제 체결 RSI 점을 지정해 PNG 생성
make backtest v4_1 FROM=2026-01-01 TO=2026-08-02 SHOW_RSI_SIGNAL_POINTS=1

# SMA 기간·손절·익절·쿨다운 후보를 같은 체결 가정으로 비교
python3 develop/v4_1/research.py --from 2026-01-01 --to 2026-08-02 --cron-interval-minutes 60

# 실제 주문 실행 — crontab 등록 전에는 기간을 나눈 연구 결과를 먼저 검토
python3 develop/v4_1/btc_bot.py
```

- V4.1은 RSI 회복 신호에 4시간봉 SMA(50) 추세 필터를 더해, 긴 하락 구간의 일시적 반등 진입을 줄입니다.
- 손절이 체결되면 24시간 동안 재매수하지 않습니다. 이 상태는 `develop/v4_1/trade_state.json`에 저장되며 Git에는 포함하지 않습니다.
- 2026-01-01~2026-08-02의 60분 크론 가정에서 V4.1은 +6.38%, 최대 낙폭 -2.43%, 4회 체결이었습니다. 표본이 작고 기간별 최선의 SMA가 달랐으므로, 이 결과만으로 실거래 수익을 기대하면 안 됩니다.
- 자세한 규칙, 백테스트 가정, 결과 한계는 [V4.1 설명](develop/v4_1/README.md)에서 확인합니다.

## V5 독립 BTC 단타 전략

```bash
# V5 기본 설정으로 PNG 생성 (기본: 2026-07-01부터 최신 완료 5분봉까지)
make backtest v5

# 기간과 실제 가상 체결 RSI 점을 지정해 PNG 생성
make backtest v5 FROM=2026-07-01 TO=2026-08-02 SHOW_RSI_SIGNAL_POINTS=1

# 실제 주문을 실행하는 V5 봇 — V4와 별도 crontab 주기로 등록할 수 있음
python3 develop/v5/btc_bot.py
```

- V4는 `KRW-ETH`에 최대 700,000원, V5는 `KRW-BTC`에 최대 300,000원을 새 매수 한 번에 사용합니다. 이 배분은 [`develop/portfolio.py`](develop/portfolio.py)에서 조정합니다.
- V5는 5분봉 RSI(7)가 40을 회복하고, 직전 종가가 볼린저 하단 밴드(20, 2.5σ) 아래였다가 돌아오며, 현재가가 SMA(50) 위일 때만 진입합니다. 매수 후에는 수수료 뒤 순이익 +0.1%를 목표로 지정가 매도를 냅니다.
- V5의 크론 가정은 백테스트 전용입니다. 실제 실행 주기는 V4와 별개로 서버 crontab에서 결정하며, `btc_bot.py`는 `cron_interval_minutes`를 읽지 않습니다.
- 시장가 매수·지정가 매도 사이의 상태는 `develop/v5/trade_state.json`에 저장합니다. 상태가 없는데 V5 BTC 보유분이 있으면 자동 주문을 멈추므로, 수동 확인 후에만 재개하세요.
- 자세한 자금 분리 방식, 주문 상태 흐름, 백테스트 가정은 [V5 설명](develop/v5/README.md)에서 확인합니다.

## V2 시각화
```bash
# V2 전략 설명 이미지 생성
python develop/v2/strategy_v2_visualizer.py
```

## V2 실행 봇
```bash
# 기본은 주문 없는 dry-run
python develop/v2/v2_bot.py

# 실제 주문 실행
python develop/v2/v2_bot.py --live
```

## V0 실행 봇
```bash
# V0 봇 실행
python develop/v0/btc_bot.py
```

## 문법 검사
```bash
# 라이브러리 파일 문법만 빠르게 확인
python -m py_compile develop/upbit_develop_library.py

# 라이브러리 파일과 공용 테스트의 문법을 한 번에 확인
python -m py_compile develop/upbit_develop_library.py develop/tests/test_upbit_develop_library.py develop/tests/test_syntax_check.py
```
