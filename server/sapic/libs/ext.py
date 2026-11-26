# -*- coding: utf-8 -*-
"""sapic.libs.ext

Extension points: the contracts a hook package implements to plug into sapic.

A hook is a module (or package) loaded by :mod:`sapic.libs.hook`, either from
``sapic/hooks`` or from an installed distribution registered through the
``hooks_imported`` setting. What a hook *can do* is decided by its
``__catalog__`` metadata plus the functions it exports, and this module is the
only place that decides it: the auth flow, the storage resolver and the admin
API all ask here instead of probing ``getattr(module, ...)`` on their own.

Recognised catalogues:

``auth``
    A sign-in provider implementing the authorization-code contract
    (:data:`PROVIDER_FUNCS`). It owns the provider conversation only; the
    browser redirects, the state cookie, the local session and the user record
    stay in :mod:`sapic.views.auth` / :mod:`sapic.libs.users`.
``upload``
    A storage driver implementing :data:`DRIVER_FUNCS`. It stores one object and
    reports where it landed; priorities, replicas and expiry stay in
    :mod:`sapic.libs.storage`. A driver that also exports
    :data:`DRIVER_READ_FUNC` can serve a private bucket (it signs a temporary
    read address for ``/raw``); without it the backend may only be ``public``.
``processor``
    A stream processor (:data:`PROCESSOR_FUNCS`) that may rewrite the uploaded
    bytes before they are stored.
``moderator``
    A content reviewer (:data:`MODERATOR_FUNCS`) that returns a verdict for one
    stored image (sexual content, violence, ...). It never runs inside the
    upload request: a maintenance scan claims unpublished rows, asks every
    enabled moderator and persists the verdict. ``block`` only hides the image
    (``review_state``) -- deleting the row stays an administrator's decision.
``mail``
    A mail transport (:data:`MAIL_FUNCS`) that takes over from the built-in
    SMTP client while it reports itself configured; the readiness check is an
    optional :data:`MAIL_READY_FUNC` so an unconfigured hook never swallows
    verification mails.

Any other catalogue is a plain UI hook: its only job is declarative
slots/actions/datasets, so it never enters an upload or login path.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CATALOG_AUTH = "auth"
CATALOG_UPLOAD = "upload"
CATALOG_PROCESSOR = "processor"
CATALOG_MODERATOR = "moderator"
CATALOG_MAIL = "mail"

#: Extension kinds reported by :func:`kind_of` (a catalogue, plus ``ui``).
KIND_PROVIDER = "provider"
KIND_DRIVER = "driver"
KIND_PROCESSOR = "processor"
KIND_MODERATOR = "moderator"
KIND_MAIL = "mail"
KIND_UI = "ui"

#: Required by ``auth``: build the authorize URL, then trade the code for claims.
PROVIDER_FUNCS = ("oidc_authorize_url", "oidc_exchange")
#: Optional for ``auth``: declare the namespace written into ``issuer``.
PROVIDER_OPTIONAL_FUNCS = ("identity_issuer",)

#: Required by ``upload``: store one object and return where it landed.
DRIVER_FUNCS = ("upimg_save",)
#: Optional for ``upload``: remove one object (needed to delete/expire images).
DRIVER_OPTIONAL_FUNCS = ("upimg_delete",)
#: Optional for ``upload``: hand out a temporary read address of one object,
#: required only when the backend is marked ``private`` (bucket rejects
#: anonymous reads). Local objects are streamed from disk and need no URL.
DRIVER_READ_FUNC = "upimg_url"

#: Required by ``processor``: rewrite the payload before it is stored.
PROCESSOR_FUNCS = ("upimg_stream_processor",)

#: Required by ``moderator``: judge one stored image. The function receives
#: ``image`` (a plain dict, see :mod:`sapic.libs.review`) and its own ``config``,
#: and returns ``{code, verdict, message}``: ``code`` 0 means "judged",
#: ``verdict`` is ``pass`` or ``block``, anything else is retried by the next
#: scan. It must not delete or edit the row itself -- that is the caller's job.
MODERATOR_FUNCS = ("review_image",)

#: Required by ``mail``: deliver one plain-text message (``config=``, ``to=``,
#: ``subject=``, ``body=``), raising ``ValueError`` when delivery fails.
MAIL_FUNCS = ("send_mail",)
#: Optional for ``mail``: whether the saved config is complete enough to use.
#: A hook without it is called whenever it is enabled.
MAIL_READY_FUNC = "mail_ready"

#: Keys of the dict returned by ``oidc_exchange``; only ``subject`` is required.
IDENTITY_KEYS = (
    "issuer",
    "subject",
    "username",
    "nickname",
    "email",
    "email_verified",
)
REQUIRED_IDENTITY_KEYS = ("subject",)


def catalog_of(module) -> str:
    """``__catalog__`` declared by the hook, lower-cased; ``""`` when absent."""
    return str(getattr(module, "__catalog__", "") or "").strip().lower()


def missing_callables(module, names) -> list[str]:
    """Names from ``names`` that the module does not export as a callable."""
    return [name for name in names if not callable(getattr(module, name, None))]


def is_provider(module) -> bool:
    """Whether the module satisfies the sign-in provider contract."""
    return catalog_of(module) == CATALOG_AUTH and not missing_callables(
        module, PROVIDER_FUNCS
    )


def is_driver(module) -> bool:
    """Whether the module satisfies the storage driver contract."""
    return catalog_of(module) == CATALOG_UPLOAD and not missing_callables(
        module, DRIVER_FUNCS
    )


def is_processor(module) -> bool:
    """Whether the module satisfies the stream processor contract."""
    return catalog_of(module) == CATALOG_PROCESSOR and not missing_callables(
        module, PROCESSOR_FUNCS
    )


def is_moderator(module) -> bool:
    """Whether the module satisfies the content moderation contract."""
    return catalog_of(module) == CATALOG_MODERATOR and not missing_callables(
        module, MODERATOR_FUNCS
    )


def is_mailer(module) -> bool:
    """Whether the module satisfies the mail transport contract."""
    return catalog_of(module) == CATALOG_MAIL and not missing_callables(
        module, MAIL_FUNCS
    )


def supports_private_read(module) -> bool:
    """Whether the driver can serve objects it stored in a private bucket.

    A driver without :data:`DRIVER_READ_FUNC` can only hand out the URL it built
    at upload time, which a private bucket refuses; marking such a backend
    ``private`` would break every read, so the service layer refuses it.
    """
    return is_driver(module) and callable(
        getattr(module, DRIVER_READ_FUNC, None)
    )


def kind_of(module) -> str:
    """Extension kind declared by the hook, ``ui`` for anything else.

    The declared kind is reported even when the implementation is incomplete, so
    the admin page can show "declared a driver but missing ``upimg_save``"
    instead of silently filing it under UI hooks. Use :func:`is_driver` /
    :func:`is_provider` when deciding whether to actually call it.
    """
    catalog = catalog_of(module)
    if catalog == CATALOG_AUTH:
        return KIND_PROVIDER
    if catalog == CATALOG_UPLOAD:
        return KIND_DRIVER
    if catalog == CATALOG_PROCESSOR:
        return KIND_PROCESSOR
    if catalog == CATALOG_MODERATOR:
        return KIND_MODERATOR
    if catalog == CATALOG_MAIL:
        return KIND_MAIL
    return KIND_UI


def warnings_of(module) -> list[str]:
    """Contract problems worth showing to an operator; empty when complete."""
    catalog = catalog_of(module)
    problems = []
    if catalog == CATALOG_AUTH:
        problems += [
            "auth provider is missing required function: %s" % name
            for name in missing_callables(module, PROVIDER_FUNCS)
        ]
    elif catalog == CATALOG_UPLOAD:
        problems += [
            "storage driver is missing required function: %s" % name
            for name in missing_callables(module, DRIVER_FUNCS)
        ]
        if not missing_callables(module, DRIVER_FUNCS):
            problems += [
                "storage driver is missing %s: stored objects cannot be removed"
                % name
                for name in missing_callables(module, DRIVER_OPTIONAL_FUNCS)
            ]
    elif catalog == CATALOG_PROCESSOR:
        problems += [
            "processor is missing required function: %s" % name
            for name in missing_callables(module, PROCESSOR_FUNCS)
        ]
    elif catalog == CATALOG_MODERATOR:
        problems += [
            "moderator is missing required function: %s" % name
            for name in missing_callables(module, MODERATOR_FUNCS)
        ]
    elif catalog == CATALOG_MAIL:
        problems += [
            "mail transport is missing required function: %s" % name
            for name in missing_callables(module, MAIL_FUNCS)
        ]
    return problems


def _as_bool(value) -> bool:
    """Claims arrive as bool, ``"true"`` or ``1`` depending on the provider."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def normalize_identity(claims) -> dict:
    """Validate and trim the dict returned by ``oidc_exchange``.

    A provider may return ``sub`` instead of ``subject`` (the OIDC spelling),
    ``preferred_username`` instead of ``username``, and may omit ``username``
    (it then falls back to ``preferred_username`` and finally the subject).
    ``ValueError`` is raised when no subject is present, so a broken provider
    can never create a user row keyed on an empty identity.
    """
    data = claims if isinstance(claims, dict) else {}
    subject = str(data.get("subject") or data.get("sub") or "").strip()[:255]
    if not subject:
        raise ValueError("invalid oidc identity: subject is missing")

    username = (
        str(data.get("username") or data.get("preferred_username") or "").strip()[:32]
        or subject[:32]
    )
    return {
        "issuer": str(data.get("issuer") or "").strip()[:255],
        "subject": subject,
        "username": username,
        "nickname": str(
            data.get("nickname")
            or data.get("preferred_username")
            or data.get("name")
            or ""
        ).strip()[:64],
        "email": str(data.get("email") or "").strip()[:128],
        "email_verified": _as_bool(data.get("email_verified")),
    }


def normalize_issuer(value) -> str:
    """Canonical form of an issuer, used both when writing and comparing it.

    Providers disagree on the trailing slash (``https://id.example.com`` versus
    ``https://id.example.com/``), so the value stored at bind time must be
    trimmed the same way as the one the account page compares against; mixing
    the two makes an established binding look unbound.
    """
    return str(value or "").strip().rstrip("/")[:255]


def provider_issuer(module, config=None) -> str:
    """Stable namespace of the identities issued by this provider.

    ``identity_issuer(config)`` lets a provider that is not OIDC (a plain OAuth
    app, for example) declare the value it writes into ``issuer``; without the
    function the provider's configured ``issuer`` field is used. The value is
    what the account page compares against to show "已绑定".
    """
    config = dict(config or {})
    func = getattr(module, "identity_issuer", None)
    if callable(func):
        try:
            value = str(func(config) or "").strip()
        except Exception:
            logger.exception("identity_issuer() of %s failed", module)
            value = ""
        if value:
            return normalize_issuer(value)
    return normalize_issuer(config.get("issuer"))
