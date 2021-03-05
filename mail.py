import smtplib
from email.mime.text import MIMEText
from email.header import Header
from logger import _logger
import yaml

def send_mail(subject='', text='', receiver=None, bcc_admin=False, args=None):
    """Send email using configs in cfg_path, with given subject, text, and receiver (or receiver list)
    Example:
       send_mail(subject, text, args=args) # send to admin only
       send_mail(subject, text, args=args, receiver='receiver@example.com', bcc_admin=True)
    """

    mail_args = args['mail']
    
    smtp_host = mail_args['smtp_host']
    smtp_port = mail_args['smtp_port']
    smtp_address = mail_args['smtp_address']
    smtp_password = mail_args['smtp_password']
    smtp_username = mail_args['smtp_username']
    if receiver is None:
        receiver = mail_args['receiver_admin']
    if isinstance(receiver, str):
        receiver = [receiver]
    receiver_bcc = mail_args['receiver_admin'] if bcc_admin else []
    
    try:
        message = MIMEText(text, 'plain', 'utf-8')
        message['From'] = Header(f'{smtp_username} <{smtp_address}>')
        message['To'] =  Header(','.join(receiver))
        if len(receiver_bcc) > 0:
            message['Bcc'] =  Header(','.join(receiver_bcc))
        message['Subject'] = Header(subject, 'utf-8')

        ## Send email
        if not mail_args['dry_run']:
            smtpObj = smtplib.SMTP_SSL(smtp_host, smtp_port)
            smtpObj.login(smtp_address, smtp_password)
            smtpObj.sendmail(smtp_address, receiver+receiver_bcc, message.as_string())
        print("Email sent:\nFrom: {sender}\nTo: {receiver}\nBcc: {bcc}\nSubject: {subject}\nText:\n{text}".format(
            sender=f'{smtp_username} <{smtp_address}>',
            receiver=','.join(receiver),
            bcc=','.join(receiver_bcc),
            subject=subject,
            text=text,
        ))

    except smtplib.SMTPException as e:
        print(f'Cannot send email. Error: {e}')
        
    return message