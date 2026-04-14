from __future__ import annotations

from dataclasses import dataclass


class KernelError(Exception):
    pass


class RetryableError(KernelError):
    pass


class BusinessError(KernelError):
    pass


class FatalError(KernelError):
    pass


class InterruptError(KernelError):
    pass


@dataclass(frozen=True)
class ExceptionDecision:
    category: str
    retry_hint: str
    fallback_hint: str


def route_exception(exc: Exception) -> ExceptionDecision:
    if isinstance(exc, RetryableError):
        return ExceptionDecision("retryable", "retry_with_backoff", "fallback_to_secondary_condition")
    if isinstance(exc, BusinessError):
        return ExceptionDecision("business", "no_retry", "abort_stage")
    if isinstance(exc, InterruptError):
        return ExceptionDecision("interrupt", "no_retry", "stop_run")
    if isinstance(exc, FatalError):
        return ExceptionDecision("fatal", "no_retry", "stop_run")
    return ExceptionDecision("unknown", "no_retry", "stop_run")
