import smtplib
from email.mime.text import MIMEText
from email.header import Header
from logger import _logger
import yaml

def send_mail(subject='', text='', receiver=None, cc_admin=False, args=None):
    """Send email using configs in cfg_path, with given subject, text, and receiver (or receiver list)
    Example:
       send_mail(subject, text, args=args) # send to admin only
       send_mail(subject, text, args=args, receiver='receiver@example.com', cc_admin=True)
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
    
    try:
        message = MIMEText(text, 'plain', 'utf-8')
        message['From'] = Header(f'{smtp_username} <{smtp_address}>')
        message['To'] =  Header(','.join(receiver))
        if cc_admin:
            message['Cc'] =  Header(','.join(mail_args['receiver_admin']))
        message['Subject'] = Header(subject, 'utf-8')

        ## Send email
        if not mail_args['dry_run']:
            smtpObj = smtplib.SMTP_SSL(smtp_host, smtp_port)
            smtpObj.login(smtp_address, smtp_password)
            smtpObj.sendmail(smtp_address, receiver, message.as_string())
        _logger.info("Email sent:\nFrom: {sender}\nTo: {receiver}\nCc: {cc}\nSubject: {subject}\nText:\n{text}".format(
            sender=f'{smtp_username} <{smtp_address}>',
            receiver=','.join(receiver),
            cc=','.join(mail_args['receiver_admin']) if cc_admin else 'None',
            subject=subject,
            text=text,
        ))

    except smtplib.SMTPException as e:
        _logger.error(f'Cannot send email. Error: {e}')
        
    return message