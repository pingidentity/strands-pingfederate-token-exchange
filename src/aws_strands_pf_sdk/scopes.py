"""Scope-selection logic for downstream token exchange."""

from __future__ import annotations

from typing import Iterable


def normalize_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    """Normalize a scope iterable by trimming and dropping empties."""

    return tuple(scope.strip() for scope in scopes if scope and scope.strip())


def strip_scope_prefix(scopes: Iterable[str], prefix: str | None) -> tuple[str, ...]:
    """Strip a shared prefix from each scope when it is present."""

    normalized = normalize_scopes(scopes)
    if not prefix:
        return normalized
    return tuple(scope[len(prefix) :] if scope.startswith(prefix) else scope for scope in normalized)


def resolve_exchange_scopes(
    subject_scopes: Iterable[str],
    *,
    scope_prefix: str | None,
    default_scopes: Iterable[str] = (),
    prefix_to_strip: str | None = None,
) -> tuple[str, ...]:
    """Select scopes to request during token exchange.

    If `scope_prefix` matches one or more subject-token scopes, the matching
    scopes are forwarded. Otherwise `default_scopes` is returned.
    """

    normalized_subject_scopes = strip_scope_prefix(subject_scopes, prefix_to_strip)
    if scope_prefix:
        matching = tuple(scope for scope in normalized_subject_scopes if scope.startswith(scope_prefix))
        if matching:
            return matching
    return normalize_scopes(default_scopes)


def join_scopes(scopes: Iterable[str]) -> str | None:
    """Serialize scopes for an OAuth form body."""

    normalized = normalize_scopes(scopes)
    if not normalized:
        return None
    return " ".join(normalized)
