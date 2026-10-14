from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    urlsafe_base64_decode,
    urlsafe_base64_encode,
)
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    RegisterSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ProfileSerializer,
    ChangePasswordSerializer,
    LogoutSerializer,
    ResendVerificationSerializer,
)
from .tasks import send_auth_email

from .throttles import (
    RegisterThrottle,
    LoginThrottle,
    EmailVerificationThrottle,
    ResendVerificationThrottle,
    PasswordResetThrottle,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    def perform_create(self, serializer):
        user = serializer.save()

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        transaction.on_commit(
            lambda: send_auth_email.delay(
                template_name="verify",
                subject="Verify your NotifyHub account",
                recipient=user.email,
                context={
                    "username": user.username,
                    "uid": uid,
                    "token": token,
                },
            )
        )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [EmailVerificationThrottle]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")

        if not isinstance(uid, str) or not isinstance(token, str):
            return Response(
                {"detail": "Invalid verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (
                TypeError,
                ValueError,
                OverflowError,
                User.DoesNotExist,
        ):
            return Response(
                {"detail": "Invalid verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_active or not default_token_generator.check_token(
                user, token
        ):
            return Response(
                {"detail": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = True
        user.save(update_fields=["is_active"])

        return Response({
            "detail": "Email verified successfully."
        })


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
        ).first()

        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            recipient = user.email

            transaction.on_commit(
                lambda: send_auth_email.delay(
                    template_name="reset_password",
                    subject="Reset your NotifyHub password",
                    recipient=recipient,
                    context={
                        "username": user.username,
                        "uid": uid,
                        "token": token,
                    },
                )
            )

        return Response({
            "detail": (
                "If the account exists, "
                "a password reset email will be sent."
            )
        })


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            user_id = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(
                pk=user_id,
                is_active=True,
            )
        except (
                TypeError,
                ValueError,
                OverflowError,
                User.DoesNotExist,
        ):
            return Response(
                {"detail": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(
                user, data["token"]
        ):
            return Response(
                {"detail": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(data["password"])
        user.save(update_fields=["password"])

        return Response({
            "detail": "Password reset successfully."
        })


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(
            serializer.validated_data["new_password"]
        )
        user.save(update_fields=["password"])

        return Response({
            "detail": "Password changed successfully."
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(
                serializer.validated_data["refresh"]
            )

            if str(token["user_id"]) != str(request.user.pk):
                return Response(
                    {"detail": "Invalid refresh token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token.blacklist()

        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "detail": "Logged out successfully."
        })


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ResendVerificationThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(
            email__iexact=email, is_active=False
        ).first()

        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            recipient = user.email
            username = user.username
            transaction.on_commit(
                lambda: send_auth_email.delay(
                    template_name="verify",
                    subject="Verify your NotifyHub account",
                    recipient=recipient,
                    context={"username": username, "uid": uid, "token": token},
                )
            )

        return Response({
            "detail": "If verification is required, an email will be sent."
        })
