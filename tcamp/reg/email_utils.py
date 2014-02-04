import os
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from email.MIMEImage import MIMEImage
import html2text

from django.contrib.staticfiles.storage import staticfiles_storage

def send_html_email(subject, html_content, sender, to_addresses, images):
    text_content = html2text.html2text(html_content)
    msg = EmailMultiAlternatives(subject, text_content, sender, to_addresses)
    msg.attach_alternative(html_content, "text/html")
    
    msg.mixed_subtype = 'related'
    
    for f in images:
        fp = open(staticfiles_storage.path(f), 'rb')
        msg_img = MIMEImage(fp.read())
        fp.close()
        
        name = os.path.basename(f)
        msg_img.add_header('Content-ID', '<{}>'.format(name))
        msg_img.add_header('Content-Disposition', 'attachment', filename=name)
        msg.attach(msg_img)

    msg.send()

def send_html_email_template(subject, template, context, sender, to_addresses, images):
    html_content = render_to_string(template, context)
    send_html_email(subject, html_content, sender, to_addresses, images)