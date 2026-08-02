# V3 RSI 분할매수 전략

V3는 RSI가 과매도 구간에 들어오면 원화 잔고를 나누어 매수하고, RSI가 과매수
구간까지 올라온 뒤 손실·본전이거나 목표 수익률에 도달했을 때 전량 매도하는 전략이다.

기본 대상은 `KRW-ETH`이고, RSI 전략 봉은 4시간봉(`minute240`)이다.

## 매매 규칙

| 구분 | 기본값 | 의미 |
| --- | ---: | --- |
| 매수 | RSI `≤ 30` | 가용 원화의 20%를 매수 |
| 매도 검토 | RSI `≥ 70` | 보유 중일 때만 매도를 검토 |
| 본전·손실 매도 | 수익률 `≤ 0%` | 매도 검토 시 전량 매도 |
| 익절 매도 | 수익률 `≥ +5%` | 매도 검토 시 전량 매도 |
| 중간 수익 | `0% < 수익률 < +5%` | RSI가 70 이상이어도 보유 유지 |
| 최소 주문 | 5,000 KRW | 이보다 작으면 매수하지 않음 |
| 수수료 가정 | 주문당 0.05% | 백테스트 매수·매도에 각각 적용 |

```text
RSI ≤ 30
  ↓
가용 원화의 20% 매수
  ↓
RSI ≥ 70 이 될 때까지 보유
  ↓
수익률 ≤ 0% ───────→ 전량 매도 (본전/손실)
수익률 ≥ +5% ──────→ 전량 매도 (익절)
그 외 (+0~+5%) ───→ 계속 보유
```

RSI가 30 이하인 상태에서 크론이 여러 번 실행되면, 매 실행마다 남은 원화의 20%를
추가 매수할 수 있다. 이것이 V3의 분할매수 방식이다.

## 실거래와 백테스트의 역할

- `btc_bot.py`는 업비트 API를 호출해 실제 주문을 낼 수 있다. `.env`의 API 키가 필요하며,
  실행 주기는 코드가 아니라 서버의 crontab에서 정한다.
- `BacktestConfig.cron_interval_minutes`는 **백테스트 전용** 가정이다. 실제 봇은 이 값을
  읽지 않는다.
- 백테스트는 크론 주기에 맞는 짧은 원본 봉으로 매 실행 시점의 부분 4시간봉을 만들고 RSI를
  계산한다. 미래 정보를 쓰지 않기 위해, 신호 판단 뒤의 다음 원본 봉 시가에 체결된 것으로
  가정한다.

## 백테스트 실행

```bash
# 기본 설정과 최근 전략 봉으로 PNG 생성
make backtest v3

# 특정 시작일부터 최신 완료 봉까지
make backtest v3 FROM=2026-01-01

# 시작일·종료일을 모두 포함해 PNG 생성
make backtest v3 FROM=2026-01-01 TO=2026-06-30

# 가격·RSI 그래프에 실제 체결한 매수·매도 지점도 표시
make backtest v3 SHOW_RSI_SIGNAL_POINTS=1

# 실제 주문 실행: 사전에 .env와 crontab 설정을 확인한다.
python3 develop/v3/btc_bot.py
```

생성 결과는 `develop/v3/backtesting/v3_backtest.png`에 저장된다. PNG에는 티커, RSI 기간,
매수·매도 기준, 수수료, 백테스트 크론 가정, 기간, 원금, 체결 수, 최종 자산, 총수익률이
함께 표시된다.

## 데이터 캐시

원본 OHLCV 데이터는 `develop/v3/backtesting/cache/`에 티커와 원본 봉 간격별 CSV·범위
메타데이터로 저장된다. 다음 실행에서는 이미 저장된 기간을 재사용하고, 요청 기간에서 비어
있는 앞·뒤 구간만 업비트 API로 추가 조회한다. 완료된 과거 봉만 캐시하며 최신 진행 중 봉은
캐시하지 않는다.

## 테스트

```bash
# 순수 RSI 신호·매매 판단 테스트
python -m unittest discover -s develop/v3/tests -p 'test_*.py' -v

# 백테스트·시각화·캐시 테스트
python -m unittest discover -s develop/v3/backtesting/tests -p 'test_*.py' -v
```

## 파일 역할

- `config.py`: 티커, RSI 봉, 분할매수·매도 기준, 백테스트 가정
- `trade_logic.py`: API 호출 없는 RSI 신호·매매 판단 순수 함수
- `btc_bot.py`: 실제 업비트 주문, Gmail 알림, 자산·거래 로그 처리
- `backtesting/backtest_logic.py`: 크론·수수료·다음 봉 시가를 가정한 순수 시뮬레이터
- `backtesting/backtest_visualizer.py`: 백테스트 결과 PNG 생성기
- `backtesting/ohlcv_cache.py`: 과거 OHLCV 범위 캐시와 API 부족 구간 조회 처리
- `tests/`: 매매 판단 단위 테스트
- `backtesting/tests/`: 시각화와 캐시를 포함한 백테스트 단위 테스트
