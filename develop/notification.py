"""자동매매 스크립트에서 재사용하는 알림 유틸입니다."""

from __future__ import annotations

import smtplib
from collections.abc import Iterable
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_gmail(
    subject: str,
    body: str,
    sender: str,
    recipients: Iterable[str],
    app_password: str | None,
) -> bool:
    """Gmail SMTP로 일반 텍스트 메일을 전송합니다.

    설정이 비어 있거나 전송에 실패하면 ``False``를 반환하고, 예외를 호출자에게
    전파하지 않습니다. 자동매매 실행 자체가 메일 전송 실패로 중단되지 않도록 하기
    위함입니다.
    """

    recipient_list = list(recipients)
    if not (sender and app_password and recipient_list):
        print("✉️ Gmail 설정이 없어서 메일 전송 생략")
        return False

    try:
        message = MIMEMultipart()
        message["From"] = sender
        message["To"] = ", ".join(recipient_list)
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.send_message(message)
    except Exception as error:
        print(f"❌ 메일 전송 실패: {error}")
        return False

    return True
