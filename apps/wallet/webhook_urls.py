from django.urls import path

from apps.wallet.webhooks import mobile_money_webhook

urlpatterns = [
    path("mobile-money/", mobile_money_webhook, name="mobile-money-webhook"),
]
