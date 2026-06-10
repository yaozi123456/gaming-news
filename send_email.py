#!/usr/bin/env python3
"""发送HTML邮件——蓝色可点击链接 + 表格渲染"""
import smtplib
import markdown
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys
import os

SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465
SENDER = "xyokokok@163.com"
PASSWORD = os.environ.get("SMTP_PASS", "FG9TLkyRuGGghWUA")
TO = "xyokokok@163.com"

CSS = """
<style>
  body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 15px; color: #333; line-height: 1.8; max-width: 680px; margin: 0 auto; padding: 20px; }
  h1 { font-size: 22px; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }
  h2 { font-size: 17px; color: #1a73e8; margin-top: 32px; margin-bottom: 12px; }
  blockquote { border-left: 3px solid #1a73e8; padding: 6px 14px; color: #666; margin: 16px 0; background: #f8f9fa; }
  a { color: #1a73e8; text-decoration: none; font-weight: 500; }
  a:hover { text-decoration: underline; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0 20px 0; }
  th { background: #1a73e8; color: #fff; padding: 8px 12px; text-align: left; font-size: 13px; }
  td { padding: 8px 12px; border-bottom: 1px solid #e0e0e0; font-size: 14px; vertical-align: top; }
  tr:hover td { background: #f0f6ff; }
  hr { border: none; border-top: 1px solid #e0e0e0; margin: 28px 0; }
  .footer { color: #999; font-size: 12px; margin-top: 30px; }
  .emoji { font-size: 16px; }
</style>
"""

def md_to_html(md_text):
    raw = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">{CSS}</head>
<body>
{raw}
</body></html>"""

def send_email(subject, md_body):
    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER
    msg["To"] = TO
    msg["Subject"] = subject

    plain_part = MIMEText(md_body, "plain", "utf-8")
    html_part = MIMEText(md_to_html(md_body), "html", "utf-8")
    msg.attach(plain_part)
    msg.attach(html_part)

    server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    server.login(SENDER, PASSWORD)
    server.sendmail(SENDER, TO, msg.as_string())
    server.quit()
    print(f"✅ 日报已发送 (HTML): {subject}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: send_email.py <subject> <body_file>")
        sys.exit(1)
    subject = sys.argv[1]
    body_file = sys.argv[2]
    with open(body_file, "r", encoding="utf-8") as f:
        body = f.read()
    send_email(subject, body)
