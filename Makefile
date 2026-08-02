.PHONY: pull push update backtest v3 v4 v4_1 v5

BACKTEST_V3_ARGS := $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO)) $(if $(SHOW_RSI_SIGNAL_POINTS),--show-rsi-signal-points)
BACKTEST_V4_ARGS := $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO)) $(if $(SHOW_RSI_SIGNAL_POINTS),--show-rsi-trade-points)
BACKTEST_V4_1_ARGS := $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO)) $(if $(SHOW_RSI_SIGNAL_POINTS),--show-rsi-trade-points)
BACKTEST_V5_ARGS := $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO)) $(if $(SHOW_RSI_SIGNAL_POINTS),--show-rsi-trade-points)

ifeq ($(filter v5,$(MAKECMDGOALS)),v5)
BACKTEST_SCRIPT := ./scripts/backtest_v5.sh
BACKTEST_ARGS := $(BACKTEST_V5_ARGS)
else ifeq ($(filter v4_1,$(MAKECMDGOALS)),v4_1)
BACKTEST_SCRIPT := ./scripts/backtest_v4_1.sh
BACKTEST_ARGS := $(BACKTEST_V4_1_ARGS)
else ifeq ($(filter v4,$(MAKECMDGOALS)),v4)
BACKTEST_SCRIPT := ./scripts/backtest_v4.sh
BACKTEST_ARGS := $(BACKTEST_V4_ARGS)
else
BACKTEST_SCRIPT := ./scripts/backtest_v3.sh
BACKTEST_ARGS := $(BACKTEST_V3_ARGS)
endif

pull:
	@./scripts/pull.sh

push:
	@./scripts/push.sh

update:
	@./scripts/update.sh

# `make backtest v3` 또는 `make backtest`로 V3 백테스트 PNG를 생성합니다.
backtest:
	@$(BACKTEST_SCRIPT) $(BACKTEST_ARGS)

# `make backtest v3`에서 버전 이름을 함께 쓸 수 있게 하는 표시용 목표입니다.
v3:
	@:

# `make backtest v4`에서 버전 이름을 함께 쓸 수 있게 하는 표시용 목표입니다.
v4:
	@:

# `make backtest v4_1`에서 버전 이름을 함께 쓸 수 있게 하는 표시용 목표입니다.
v4_1:
	@:

# `make backtest v5`에서 버전 이름을 함께 쓸 수 있게 하는 표시용 목표입니다.
v5:
	@:
