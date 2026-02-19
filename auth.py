from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse

COOKIE_NAME = "clams_auth"
COOKIE_DAYS = 30


def is_authenticated(request: Request) -> bool:
    return request.cookies.get(COOKIE_NAME) == "1"


def login_success_response(redirect_to: str = "/app") -> RedirectResponse:
    resp = RedirectResponse(redirect_to, status_code=303)
    expires = datetime.utcnow() + timedelta(days=COOKIE_DAYS)
    resp.set_cookie(
        key=COOKIE_NAME,
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
    return resp
