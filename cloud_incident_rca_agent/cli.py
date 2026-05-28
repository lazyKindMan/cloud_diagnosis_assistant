"""Command line interface for cloud incident RCA helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from cloud_incident_rca_agent.runtime import (
    LLMInvokeRequest,
    LLMProvider,
    LLMRuntimeSettings,
    LLMTask,
    build_llm_client,
    invoke_llm_task,
    llm_settings_from_env,
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


async def _run_llm_invoke(args: argparse.Namespace) -> int:
    base_settings = llm_settings_from_env()
    settings = LLMRuntimeSettings(
        provider=LLMProvider(args.provider) if args.provider else base_settings.provider,
        openai_api_key=base_settings.openai_api_key,
        openai_model=args.model or base_settings.openai_model,
    )
    client = build_llm_client(settings)
    result = await invoke_llm_task(
        client,
        LLMInvokeRequest(
            task=LLMTask(args.task),
            raw_description=args.raw_description,
        ),
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "llm-invoke":
            return asyncio.run(_run_llm_invoke(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
