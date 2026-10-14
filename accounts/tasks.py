import smtplib

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


@shared_task(
    autoretry_for=(smtplib.SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_auth_email(template_name, subject, recipient, context):
    html_content = render_to_string(
        f"accounts/emails/{template_name}.html",
        context,
    )

    text_content = (
        f"{subject}\n\n"
        f"UID: {context['uid']}\n"
        f"Token: {context['token']}\n"
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )

    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=False)