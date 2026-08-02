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

## 폴더 구조

```text
develop/
  v0/  # 초기 운영 코드
  v1/  # V1 전략과 봇
  v2/  # V2 전략과 봇
  v3/  # V3 전략, 봇, 전용 백테스트
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
