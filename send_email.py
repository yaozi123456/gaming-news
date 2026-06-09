#!/usr/bin/env python3
"""发送邮件到指定163邮箱"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys
import os

SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465
SENDER = "xyokokok@163.com"
PASSWORD = os.environ.get("SMTP_PASS", "FG9TLkyRuGGghWUA")
TO = "xyokokok@163.com"

def send_email(subject, body, is_html=False):
    msg = MIMEMultipart()
    msg["From"] = SENDER
    msg["To"] = TO
    msg["Subject"] = subject
    subtype = "html" if is_html else "plain"
    msg.attach(MIMEText(body, subtype, "utf-8"))

    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(SENDER, PASSWORD)
    server.sendmail(SENDER, TO, msg.as_string())
    server.quit()
    print(f"✅ 日报已发送: {subject}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: send_email.py <subject> <body_file>")
        sys.exit(1)
    subject = sys.argv[1]
    body_file = sys.argv[2]
    with open(body_file, "r", encoding="utf-8") as f:
        body = f.read()
    send_email(subject, body)
