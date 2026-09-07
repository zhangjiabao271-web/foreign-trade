import hashlib
import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.models import AiRun, AiToolCall
from app.ai.provider import AiProvider, ProviderError, artifact_from_output
from app.ai.services import record_ai_event, require_run_permissions
from app.ai.tools import ApplicationTools
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.live_context import live_context
from app.core.config import Settings
from app.platform.models import AsyncJob


class RunBusy(Exception):
    """Another bounded worker execution holds the lease; retry delivery later."""


class RunRetry(Exception):
    """A transient provider failure was persisted; retry via the bounded worker policy."""


def locked_run(session: Session, organization_id: UUID, run_id: UUID) -> AiRun:
    run = session.scalar(
        select(AiRun)
        .where(
            AiRun.organization_id == organization_id, AiRun.id == run_id, AiRun.deleted_at.is_(None)
        )
        .with_for_update()
    )
    if run is None:
        raise ValueError("AI run not found in the event organization")
    return run


def source_references(value: object) -> list[dict[str, object]]:
    references: list[dict[str, object]] = []
    if isinstance(value, dict):
        data = cast(dict[str, object], value)
        source = data.get("source")
        if isinstance(source, dict):
            references.append(cast(dict[str, object], source))
        for key, child in data.items():
            if key != "source":
                references.extend(source_references(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(source_references(child))
    return references


class AiRunner:
    def __init__(
        self, factory: sessionmaker[Session], provider: AiProvider, settings: Settings
    ) -> None:
        self.factory = factory
        self.provider = provider
        self.settings = settings

    def execute(self, *, organization_id: UUID, run_id: UUID, request_id: UUID) -> None:
        lease_id = uuid4()
        with self.factory.begin() as session:
            run = locked_run(session, organization_id, run_id)
            if run.status in {"SUCCEEDED", "FAILED"}:
                return
            if (
                run.status == "RUNNING"
                and run.started_at
                and run.started_at > datetime.now(UTC) - timedelta(minutes=4)
            ):
                raise RunBusy()
            if run.created_by is None:
                raise ValueError("AI run requires an actor")
            user_id = run.created_by
            run.status = "RUNNING"
            run.lease_id = lease_id
            run.started_at = datetime.now(UTC)
            run.attempt_count += 1
            intent, subject_id, summary, model = (
                run.intent,
                run.subject_id,
                run.input_summary,
                run.model,
            )
            job = self._job(session, run)
            job.status = "RUNNING"
            job.attempt_count = run.attempt_count
            exhausted = run.attempt_count > job.max_attempts
        inputs: list[dict[str, object]] = [{"role": "user", "content": json.dumps(summary)}]
        facts: list[dict[str, object]] = []
        input_tokens = output_tokens = 0
        error_code: str | None = None
        artifact: dict[str, object] | None = None
        try:
            if exhausted:
                raise ProviderError("AI_ATTEMPTS_EXHAUSTED")
            for _ in range(4):
                with self.factory() as session:
                    authority = live_context(
                        session,
                        organization_id=organization_id,
                        user_id=user_id,
                        request_id=request_id,
                    )
                    require_run_permissions(authority, run)
                turn = self.provider.next_turn(
                    model=model, inputs=inputs, tools=ApplicationTools.definitions(intent)
                )
                input_tokens += turn.input_tokens
                output_tokens += turn.output_tokens
                inputs.extend(turn.output)
                calls = [item for item in turn.output if item.get("type") == "function_call"]
                if not calls:
                    if not facts:
                        raise ProviderError("AI_MISSING_EVIDENCE")
                    required_tool = {
                        "SEARCH": "search_companies",
                        "TIMELINE": "order_timeline",
                        "PROFIT": "order_profit",
                        "EMAIL_DRAFT": "read_order",
                        "TASK_DRAFT": "read_order",
                    }[intent]
                    if not any(fact["tool"] == required_tool for fact in facts):
                        raise ProviderError("AI_MISSING_EVIDENCE")
                    artifact = artifact_from_output(turn.output).model_dump()
                    if intent != "TASK_DRAFT":
                        artifact["task_title"] = None
                    break
                if len(calls) != 1:
                    self._reject_calls(
                        calls,
                        run_id=run_id,
                        lease_id=lease_id,
                        organization_id=organization_id,
                        user_id=user_id,
                        request_id=request_id,
                        intent=intent,
                        subject_id=subject_id,
                        error_code="AI_TOOL_LIMIT_EXCEEDED",
                    )
                    raise ProviderError("AI_TOOL_LIMIT_EXCEEDED")
                call = calls[0]
                name, call_id, raw_arguments = (
                    call.get("name"),
                    call.get("call_id"),
                    call.get("arguments"),
                )
                if (
                    not isinstance(name, str)
                    or not isinstance(call_id, str)
                    or not isinstance(raw_arguments, str)
                ):
                    self._reject_calls(
                        calls,
                        run_id=run_id,
                        lease_id=lease_id,
                        organization_id=organization_id,
                        user_id=user_id,
                        request_id=request_id,
                        intent=intent,
                        subject_id=subject_id,
                        error_code="AI_TOOL_CALL_INVALID",
                    )
                    raise ProviderError("AI_TOOL_CALL_INVALID")
                result = self._call(
                    run_id=run_id,
                    lease_id=lease_id,
                    organization_id=organization_id,
                    user_id=user_id,
                    request_id=request_id,
                    name=name,
                    call_id=call_id,
                    raw_arguments=raw_arguments,
                    intent=intent,
                    subject_id=subject_id,
                    search_term=cast(str | None, summary.get("search_term")),
                )
                facts.append({"tool": name, "result": result})
                inputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result),
                    }
                )
            if artifact is None:
                raise ProviderError("AI_TURN_LIMIT_EXCEEDED")
        except ApiProblem as error:
            error_code = error.code
        except ProviderError as error:
            error_code = error.code
        except Exception:
            error_code = "AI_EXECUTION_FAILED"
        with self.factory.begin() as session:
            current = locked_run(session, organization_id, run_id)
            if current.lease_id != lease_id:
                raise RunBusy()
            try:
                authority = live_context(
                    session, organization_id=organization_id, user_id=user_id, request_id=request_id
                )
                require_run_permissions(authority, current)
            except ApiProblem as error:
                error_code = error.code
            current.input_tokens += input_tokens
            current.output_tokens += output_tokens
            if (
                self.settings.ai_input_usd_per_million is not None
                and self.settings.ai_output_usd_per_million is not None
            ):
                current.estimated_cost_usd = (
                    Decimal(current.input_tokens) * self.settings.ai_input_usd_per_million
                    + Decimal(current.output_tokens) * self.settings.ai_output_usd_per_million
                ) / Decimal(1_000_000)
            job = self._job(session, current)
            retry = (
                error_code == "AI_PROVIDER_UNAVAILABLE" and current.attempt_count < job.max_attempts
            )
            if retry:
                current.status = "PENDING"
            else:
                current.status = "FAILED" if error_code else "SUCCEEDED"
            current.error_code = error_code
            current.completed_at = None if retry else datetime.now(UTC)
            current.lease_id = None
            if not error_code:
                current.output = {"facts": facts, "artifact": artifact, "executed_actions": []}
                current.references = source_references(facts)
            job.status = current.status
            job.progress = Decimal(0 if retry else 100)
            job.error_code = error_code
            record_ai_event(
                session,
                RequestContext(user_id, organization_id, frozenset(), request_id),
                target_id=run_id,
                action="ai.run_retry_scheduled" if retry else "ai.run_finished",
                details={"status": current.status, "error_code": error_code},
            )
        if retry:
            raise RunRetry()

    def _reject_calls(
        self,
        calls: list[dict[str, object]],
        *,
        run_id: UUID,
        lease_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        request_id: UUID,
        intent: str,
        subject_id: UUID | None,
        error_code: str,
    ) -> None:
        for index, call in enumerate(calls):
            name = call.get("name")
            # Use an ordinal receipt ID: malformed or repeated provider IDs must not
            # prevent recording every rejected request. Arguments remain hash-only.
            with suppress(ProviderError):
                self._call(
                    run_id=run_id,
                    lease_id=lease_id,
                    organization_id=organization_id,
                    user_id=user_id,
                    request_id=request_id,
                    name=name if isinstance(name, str) else "unknown",
                    call_id=f"rejected-{index}",
                    raw_arguments=json.dumps(call),
                    intent=intent,
                    subject_id=subject_id,
                    search_term=None,
                    rejection_code=error_code,
                )

    def _call(
        self,
        *,
        run_id: UUID,
        lease_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        request_id: UUID,
        name: str,
        call_id: str,
        raw_arguments: str,
        intent: str,
        subject_id: UUID | None,
        search_term: str | None,
        rejection_code: str | None = None,
    ) -> dict[str, object]:
        error_code: str | None = None
        result: dict[str, object] = {}
        try:
            if rejection_code:
                raise ProviderError(rejection_code)
            if len(raw_arguments) > 2000 or len(call_id) > 160:
                raise ProviderError("AI_TOOL_CALL_INVALID")
            arguments: object = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ProviderError("AI_TOOL_CALL_INVALID")
            with self.factory() as session:
                context = live_context(
                    session, organization_id=organization_id, user_id=user_id, request_id=request_id
                )
                result = ApplicationTools.execute(
                    session,
                    context,
                    name=name,
                    arguments=cast(dict[str, object], arguments),
                    intent=intent,
                    subject_id=subject_id,
                    search_term=search_term,
                )
        except ApiProblem as error:
            error_code = error.code
        except (ValueError, ValidationError):
            error_code = "AI_TOOL_ARGUMENTS_INVALID"
        except ProviderError as error:
            error_code = error.code
        except Exception:
            error_code = "AI_TOOL_FAILED"
        with self.factory.begin() as session:
            run = locked_run(session, organization_id, run_id)
            if run.lease_id != lease_id:
                raise RunBusy()
            receipt = AiToolCall(
                organization_id=organization_id,
                created_by=user_id,
                updated_by=user_id,
                run_id=run_id,
                call_id=f"{lease_id}:{uuid4()}:{hashlib.sha256(call_id.encode()).hexdigest()}",
                tool_name=name if name in ApplicationTools.schemas else "unknown",
                argument_summary={"sha256": hashlib.sha256(raw_arguments.encode()).hexdigest()},
                result_summary={"references": source_references(result)},
                status="DENIED" if error_code else "SUCCEEDED",
                error_code=error_code,
            )
            session.add(receipt)
            record_ai_event(
                session,
                RequestContext(user_id, organization_id, frozenset(), request_id),
                target_id=run_id,
                action="ai.tool_called",
                details={
                    "tool": receipt.tool_name,
                    "status": receipt.status,
                    "error_code": error_code,
                },
            )
        if error_code:
            raise ProviderError(error_code)
        return result

    @staticmethod
    def _job(session: Session, run: AiRun) -> AsyncJob:
        job = session.scalar(
            select(AsyncJob)
            .where(AsyncJob.organization_id == run.organization_id, AsyncJob.id == run.job_id)
            .with_for_update()
        )
        if job is None:
            raise ValueError("AI job not found in the run organization")
        return job
