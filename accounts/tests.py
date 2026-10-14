from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()

TEST_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


@override_settings(CACHES=TEST_CACHES)
class AuthAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com",
            password="TestPassword!123", is_active=True,
        )

    @patch("accounts.views.send_auth_email.delay")
    def test_register_queues_verification_email(self, send):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("register"), {
                "username": "newuser", "email": "new@example.com",
                "password": "NewPassword!123",
            }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(User.objects.get(username="newuser").is_active)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["template_name"], "verify")

    @patch("accounts.views.send_auth_email.delay")
    def test_resend_verification_does_not_disclose_account(self, send):
        inactive = User.objects.create_user(
            username="pending", email="pending@example.com",
            password="TestPassword!123", is_active=False,
        )
        with self.captureOnCommitCallbacks(execute=True):
            valid = self.client.post(reverse("resend_verification"),
                                     {"email": inactive.email}, format="json")
        missing = self.client.post(reverse("resend_verification"),
                                   {"email": "missing@example.com"}, format="json")
        active = self.client.post(reverse("resend_verification"),
                                  {"email": self.user.email}, format="json")
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.data, missing.data)
        self.assertEqual(valid.data, active.data)
        send.assert_called_once()

    @patch("accounts.views.send_auth_email.delay")
    def test_forgot_password_can_be_requested_again(self, send):
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("forgot_password"),
                                            {"email": self.user.email}, format="json")
            self.assertEqual(response.status_code, 200)
        self.assertEqual(send.call_count, 2)

    def test_login_throttled(self):
        for _ in range(10):
            response = self.client.post(reverse("login"), {
                "username": "alice", "password": "wrong"
            }, format="json")
            self.assertEqual(response.status_code, 401)
        response = self.client.post(reverse("login"), {
            "username": "alice", "password": "wrong"
        }, format="json")
        self.assertEqual(response.status_code, 429)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(reverse("login"), {
            "username": "alice", "password": "TestPassword!123"
        }, format="json")
        self.assertEqual(response.status_code, 401)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 401)

    def test_register_rejects_weak_password(self):
        response = self.client.post(reverse("register"), {
            "username": "weakuser", "email": "weak@example.com", "password": "123"
        }, format="json")
        self.assertEqual(response.status_code, 400)
