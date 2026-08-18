"""CLI entry point (spec sections 59-61): `python -m app.agent <command>`.
Every command just sends a fixed natural-language message through the
exact same handle_chat_message() path POST /agent/chat uses -- no
separate CLI-only logic, so the CLI and the API can never drift apart.

For now this only runs on-demand (spec section 59: "do not run
automatically in the background unless explicitly configured") -- wiring
one of these commands to cron/launchd is the operator's own choice, the
same way discovery's scheduler is opt-in (see app/scheduler.py).
"""

import argparse
import asyncio
import sys

from app.agent import agent as agent_module
from app.db.database import SessionLocal
from app.models.enums import AgentTaskStatus

COMMAND_MESSAGES = {
    "search": "Find jobs matching my profile",
    "prepare": "Prepare the top 5 applications",
    "review": "Review my applications",
    "weekly-review": "Show my weekly review",
    "status": "Show my applications",
}


def _print_task(task) -> None:
    print(f"Task #{task.id} -- {task.status.value}")
    print()
    if task.final_result:
        print(task.final_result.get("summary", ""))
    elif task.error_message:
        print(task.error_message)
    print()


async def _run(message: str) -> int:
    db = SessionLocal()
    try:
        task = await agent_module.handle_chat_message(db, message)
        _print_task(task)
        return 1 if task.status == AgentTaskStatus.FAILED else 0
    finally:
        db.close()


async def _run_interview(application_id: int | None) -> int:
    if application_id is None:
        print("Usage: python -m app.agent interview --application-id <id>")
        return 2
    return await _run(f"Prepare me for the interview for application {application_id}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.agent", description="AI job search agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("search", "prepare", "review", "weekly-review", "status"):
        subparsers.add_parser(name)

    interview_parser = subparsers.add_parser("interview")
    interview_parser.add_argument("--application-id", type=int, default=None)

    args = parser.parse_args()

    if args.command == "interview":
        return asyncio.run(_run_interview(args.application_id))

    return asyncio.run(_run(COMMAND_MESSAGES[args.command]))


if __name__ == "__main__":
    sys.exit(main())
