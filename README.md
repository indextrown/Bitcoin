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

## 빠른 업데이트
```bash
# 모든 변경사항을 stage한 뒤 "update" 메시지로 커밋하고 push
make update
```

## Setting
```bash
# 1. Python 버전 설치 (최초 1회)
pyenv install 3.11.9

# 2. 프로젝트 Python 버전 지정
pyenv local 3.11.9

# 3. 가상환경 생성
python -m venv .venv

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
python -m unittest discover -s backtesting/tests -p 'test_*.py' -v
```

## 전략 비교 백테스트
```bash
# V1, V2 전략을 같은 티커 구간에서 비교
python backtesting/backtest_v1_v2.py --ticker KRW-BTC --day-count 180 --signal-count 360
```

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
