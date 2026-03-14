from datetime import datetime, timedelta

from fastapi import Request
from fastapi.responses import RedirectResponse

COOKIE_NAME = "clams_auth"
PREMIUM_COOKIE_NAME = "clams_premium"
USER_COOKIE_NAME = "clams_user"
COOKIE_DAYS = 30


def is_authenticated(request: Request) -> bool:
    return request.cookies.get(COOKIE_NAME) == "1" or bool(request.cookies.get(USER_COOKIE_NAME))


def is_premium(request: Request) -> bool:
    return request.cookies.get(PREMIUM_COOKIE_NAME) == "1"


def login_success_response(redirect_to: str = "/app", email: str = "") -> RedirectResponse:
    resp = RedirectResponse(redirect_to, status_code=303)
    expires = datetime.utcnow() + timedelta(days=COOKIE_DAYS)
    cookie_expires = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")

    resp.set_cookie(
        key=COOKIE_NAME,
        value="1",
        httponly=True,
        samesite="lax",
        expires=cookie_expires,
        max_age=COOKIE_DAYS * 24 * 60 * 60,
    )

    if email:
        resp.set_cookie(
            key=USER_COOKIE_NAME,
            value=email,
            httponly=True,
            samesite="lax",
            expires=cookie_expires,
            max_age=COOKIE_DAYS * 24 * 60 * 60,
        )

    return resp


def premium_success_response(redirect_to: str = "/app", email: str = "") -> RedirectResponse:
    resp = login_success_response(redirect_to=redirect_to, email=email)
    expires = datetime.utcnow() + timedelta(days=COOKIE_DAYS)
    resp.set_cookie(
        key=PREMIUM_COOKIE_NAME,
        value="1",
        httponly=True,
        samesite="lax",
        expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        max_age=COOKIE_DAYS * 24 * 60 * 60,
    )
    return resp


def logout_response(redirect_to: str = "/") -> RedirectResponse:
    resp = RedirectResponse(redirect_to, status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    resp.delete_cookie(PREMIUM_COOKIE_NAME)
    resp.delete_cookie(USER_COOKIE_NAME)
    return resp
