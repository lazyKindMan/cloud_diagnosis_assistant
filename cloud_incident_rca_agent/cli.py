"""Command line interface for cloud incident RCA helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence

from cloud_incident_rca_agent.runtime import (
    LLMInvokeRequest,
    LLMProvider,
    LLMRuntimeSettings,
    LLMTask,
    build_llm_client,
    invoke_llm_task,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloud-incident-rca")
    subparsers = parser.add_subparsers(dest="command", required=True)

    invoke = subparsers.add_parser("llm-invoke")
    invoke.add_argument("--provider", choices=[item.value for item in LLMProvider], default=None)
    invoke.add_argument("--model", default=None)
    invoke.add_argument("--task", choices=[item.value for item in LLMTask], required=True)
    invoke.add_argument("raw_description")
    return parser


def _build_llm_invoke_settings(args: argparse.Namespace) -> LLMRuntimeSettings:
    provider = LLMProvider(
        args.provider or os.environ.get("CLOUD_RCA_LLM_PROVIDER", LLMProvider.FAKE.value)
    )
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    return LLMRuntimeSettings(
        provider=provider,
        openai_api_key=openai_api_key if openai_api_key and openai_api_key.strip() else None,
        openai_model=args.model or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini",
    )


async def _run_llm_invoke(settings: LLMRuntimeSettings, request: LLMInvokeRequest) -> int:
    client = build_llm_client(settings)
    result = await invoke_llm_task(client, request)
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "llm-invoke":
        try:
            settings = _build_llm_invoke_settings(args)
            request = LLMInvokeRequest(
                task=LLMTask(args.task),
                raw_description=args.raw_description,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        try:
            return asyncio.run(_run_llm_invoke(settings, request))
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
