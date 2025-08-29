from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
GMAIL_ADDRESS = "indextrown@gmail.com"
TO_EMAIL = "indextrown@gmail.com"

import pyupbit  # 업비트 라이브러리
import matplotlib.pyplot as plt

load_dotenv()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD").replace(" ", "")

def get_bitcoin_chart():
    # 오늘 비트코인 15분봉 데이터 가져오기
    df = pyupbit.get_ohlcv("KRW-BTC", interval="minute15", count=50)  # 최근 50개 캔들
    
    # 차트 그리기
    plt.figure(figsize=(10,5))
    plt.plot(df.index, df["close"], label="BTC/KRW (15m)")
    plt.title("오늘 비트코인 15분봉")
    plt.xlabel("시간")
    plt.ylabel("가격 (KRW)")
    plt.legend()
    plt.grid(True)
    
    # PNG 저장
    chart_path = "btc_chart.png"
    plt.savefig(chart_path)
    plt.close()
    return chart_path

def send_gmail(subject, body, image_path=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = TO_EMAIL
        msg['Subject'] = subject

        # 텍스트 본문 추가
        msg.attach(MIMEText(body, 'plain'))

        # 이미지 첨부 (옵션)
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                img_data = f.read()
                image = MIMEImage(img_data, name=os.path.basename(image_path))
                msg.attach(image)

        # Gmail 서버 접속
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        print("✅ 메일 전송 완료")

    except Exception as e:
        print("❌ 메일 전송 실패:", e)


# send_gmail("제목", "테스트")
# send_gmail("제목", "본문 내용", "cat.png")  # sample.png 이미지 첨부

# 실행 예시
chart = get_bitcoin_chart()
send_gmail("오늘의 비트코인 차트", "비트코인 15분봉 차트입니다.", chart)