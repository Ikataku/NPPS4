import hmac
import ipaddress


def is_loopback_address(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def verify_admin_exp_token(expected_token: str | None, authorization: str | None) -> bool:
    if not expected_token or not authorization:
        return False
    scheme, separator, supplied_token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not supplied_token:
        return False
    return hmac.compare_digest(expected_token, supplied_token)
