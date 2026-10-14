from rest_framework.throttling import AnonRateThrottle


class RegisterThrottle(AnonRateThrottle):
    scope = "auth_register"


class LoginThrottle(AnonRateThrottle):
    scope = "auth_login"


class EmailVerificationThrottle(AnonRateThrottle):
    scope = "auth_verify"


class ResendVerificationThrottle(AnonRateThrottle):
    scope = "auth_resend"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "auth_password_reset"