import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Função para enviar e-mail
def send_email(subject, body):
    from_email = "binancerobotrader@gmail.com"  # Substitua com seu e-mail
    from_password = "xktq vxdx xrqy acxn"  # Substitua pela sua senha de app gerada no Gmail
    to_email = "hlinsightconsultoria@gmail.com"  # Substitua pelo e-mail do destinatário

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Falha ao enviar e-mail: {e}")
