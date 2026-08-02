.PHONY: pull push update backtest v3

BACKTEST_V3_ARGS := $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO))

pull:
	@./scripts/pull.sh

push:
	@./scripts/push.sh

update:
	@./scripts/update.sh

# `make backtest v3` 또는 `make backtest`로 V3 백테스트 PNG를 생성합니다.
backtest:
	@./scripts/backtest_v3.sh $(BACKTEST_V3_ARGS)

# `make backtest v3`에서 버전 이름을 함께 쓸 수 있게 하는 표시용 목표입니다.
v3:
	@:
