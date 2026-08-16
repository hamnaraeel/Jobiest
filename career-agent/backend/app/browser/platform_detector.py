"""Detects which known ATS platform an application URL belongs to, by
hostname pattern only -- used to select an adapter. Only
GenericApplicationAdapter is implemented in Step 5 (spec section 31: "Do
not build platform-specific automation yet unless it naturally fits the
generic system"); `register_adapter()` exists purely so a later step can
add GreenhouseAdapter/LeverAdapter/etc. without touching anything else --
`get_adapter()` falls back to the generic adapter for every platform that
has no registered adapter, including all of them today.
"""

from urllib.parse import urlparse

from app.models.enums import ApplicationPlatform

_HOSTNAME_PATTERNS: dict[str, ApplicationPlatform] = {
    "greenhouse.io": ApplicationPlatform.GREENHOUSE,
    "lever.co": ApplicationPlatform.LEVER,
    "myworkdayjobs.com": ApplicationPlatform.WORKDAY,
    "linkedin.com": ApplicationPlatform.LINKEDIN,
    "indeed.com": ApplicationPlatform.INDEED,
}

_ADAPTER_REGISTRY: dict[ApplicationPlatform, type] = {}


def detect_platform(url: str | None) -> ApplicationPlatform:
    if not url:
        return ApplicationPlatform.UNKNOWN
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return ApplicationPlatform.UNKNOWN
    for pattern, platform in _HOSTNAME_PATTERNS.items():
        if pattern in hostname:
            return platform
    return ApplicationPlatform.COMPANY_SITE


def register_adapter(platform: ApplicationPlatform, adapter_cls: type) -> None:
    _ADAPTER_REGISTRY[platform] = adapter_cls


def get_adapter(platform: ApplicationPlatform):
    from app.browser.adapters.generic import GenericApplicationAdapter

    adapter_cls = _ADAPTER_REGISTRY.get(platform, GenericApplicationAdapter)
    return adapter_cls()
