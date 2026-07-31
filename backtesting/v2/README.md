# V2 하락장 대응 백테스트

`bear_market_v2_backtest.ipynb`는 업비트 OHLCV 데이터를 사용해서
2024-01-01부터 실행 시점까지 하락장 대응 전략 후보를 비교합니다.

## 포함된 전략

- `buy_and_hold`: 비트코인 현물 단순 보유 기준선
- `v1_rsi_rebound_long`: V1 RSI 반등 아이디어를 단순화한 현물 전략
- `bear_rsi_scalp_long`: 하락장에서 과매도 반등만 짧게 먹는 현물 전략
- `cash_guard_breakout_long`: 하락장에는 현금 보유, 상승 돌파 때만 진입하는 현물 전략
- `synthetic_short_breakdown`: 하락 추세 붕괴를 따라가는 가상 숏 전략
- `v2_bear_hybrid`: 하락장 숏 + 상승장 돌파 롱 하이브리드 전략
- `v2_bear_hybrid_optimized`: 최적화된 하락장 숏 규칙과 상승 돌파 롱을 섞은 후보
- `spot_cash_guard_optimized`: 현물 전용 최적화에서 찾은 방어형 돌파 후보
- `spot_cash_guard_robust`: 워크포워드 최악 구간도 플러스였던 현물 전용 후보
- `bear_spot_quick_rebound`: 하락장에서 RSI24 과매도 반등을 짧게 먹는 현물 단타 후보

## 중요 사항

- 업비트 현물 거래는 숏 포지션을 직접 지원하지 않습니다.
- `synthetic_short_breakdown`, `v2_bear_hybrid`, `v2_bear_hybrid_optimized`의 숏 구간은 선물, 마진, 인버스 상품을 사용할 때의 연구 후보입니다.
- 실거래 전에는 슬리피지, 펀딩비/차입비, 최소 주문금액, 다종목 포지션 제한, 거래소/API 장애 처리를 반드시 추가해야 합니다.

## 현재 KRW-BTC 현물 기준 결론

현재 운영 후보는 숏을 제외하고 업비트 현물 기준으로 봅니다.

- 업비트 현물 전용 robust 후보: `spot_cash_guard_robust`
  - 분봉: `minute60`
  - 추천 크론: `*/15 * * * *`
  - 조건: RSI 50 이상, 거래량 비율 1.5 이상, -3% 손절, EMA20 이탈 청산

- 하락장 현물 단타 후보: `bear_spot_quick_rebound`
  - 분봉: `minute240`
  - 추천 크론: `*/30 * * * *`
  - 조건: 하락장, 이전 RSI 24 이하, RSI 반등, 강한 양봉, 최대 4봉 보유
  - 목적: 큰 추세 수익이 아니라 하락장 중 짧은 과매도 반등만 회수

- 현물 전략 주의점:
  - 현물만으로는 하락 자체에서 직접 수익을 내기 어렵습니다.
  - 현물 후보는 크게 두 가지입니다. 하나는 하락장에는 현금을 보유하고 강한 돌파가 확인될 때만 진입하는 방어형 전략이고, 다른 하나는 `bear_spot_quick_rebound`처럼 하락장 중 과매도 반등만 짧게 먹는 단타 전략입니다.

- `minute15` 단타 후보:
  - 현재 2024년 이후 테스트에서는 60분봉/240분봉 후보를 이기지 못했습니다.
  - 15분봉을 쓰려면 더 많은 단타 전용 조건과 슬리피지 검증이 필요합니다.

- 숏 포함 후보:
  - `v2_bear_hybrid_optimized`가 전체 연구 성과는 가장 높았지만, 업비트 현물만으로는 실행할 수 없으므로 현재 운영 추천에서는 제외합니다.

## 크론 실행 기준

- 크론은 캔들 주기보다 더 자주 실행합니다.
- 대신 봇 내부에서 마지막으로 처리한 완료 캔들 시간을 저장하고, 같은 캔들에서는 중복 주문하지 않아야 합니다.
- 업비트 현물 수수료는 `FEE_RATE = 0.0005`로 반영했습니다.
- 노트북의 비용 스트레스 테스트는 수수료 외 슬리피지/불리한 체결을 왕복 0.1%~0.4%까지 추가해 확인합니다.

## 실행 템플릿

```bash
# 업비트 현물 전용 dry-run 템플릿
python develop/v2/cron_runner_template.py

# 하락장 현물 단타 dry-run 템플릿
V2_STRATEGY=bear_spot_quick_rebound python develop/v2/cron_runner_template.py

# 60분봉 현물 전략 크론 예시
*/15 * * * * cd /path/to/Bitcoin && /path/to/python develop/v2/cron_runner_template.py >> logs/v2_spot.log 2>&1

# 4시간봉 하락장 단타 보조 전략 크론 예시
*/30 * * * * cd /path/to/Bitcoin && V2_STRATEGY=bear_spot_quick_rebound /path/to/python develop/v2/cron_runner_template.py >> logs/v2_bear_quick.log 2>&1
```

## 노트북 그래프 기준

- 첫 번째 그래프는 업비트 현물 후보만 비교합니다.
- 두 번째 그래프는 숏/인버스 가상 전략까지 포함한 전체 연구 후보를 비교합니다.
- 현재 운영 판단은 첫 번째 현물 그래프와 `최종 후보 선정표` 셀을 기준으로 합니다.


## 백테스트 결과 요약

2026-05-28 KST 기준, KRW-BTC 2024년 이후 데이터를 사용해 확인한 요약입니다.

### 업비트 현물 메인 후보

`spot_cash_guard_robust`

- 분봉: `minute60`
- 추천 크론: `*/15 * * * *`
- 로직: 상승장 돌파, RSI 50 이상, 거래량 비율 1.5 이상, EMA20 이탈 청산, -3% 손절
- 현물 robust 탐색 결과:
  - 전체 기간 수익률: 약 `+70.6%`
  - 전체 기간 MDD: 약 `-16.3%`
  - 워크포워드 최악 구간 수익률: 약 `+3.0%`

### 하락장 현물 단타 보조 후보

`bear_spot_quick_rebound`

- 분봉: `minute240`
- 추천 크론: `*/30 * * * *`
- 로직: 하락장, 이전 RSI 24 이하, RSI 반등, 강한 양봉, 최대 4봉 보유
- 탐색 결과:
  - 전체 기간 수익률: 약 `+4%~5%`
  - MDD: 약 `-3.5%`
  - 워크포워드 최악 구간 수익률: 약 `+0.7%`
- 해석: 단독 메인 전략으로는 약하지만, 하락장에서 현금을 대부분 유지하면서 짧은 과매도 반등만 회수하는 보조 전략으로는 검토할 만합니다.

### 15분봉 단타 결과

테스트한 `minute15` 후보들은 60분봉/240분봉 후보를 이기지 못했습니다. 현재 보이는 15분봉 최선 후보는 `panic_reversal_long`이지만 거래 횟수가 너무 적어 실전 투입 근거로는 부족합니다.
