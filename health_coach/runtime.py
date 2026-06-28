"""Session runtime: wires SessionService + MemoryService to the agent and
implements the Daily Session strategy (one session per calendar day).

Note: this Runner/SessionService wiring is for local dev/testing only.
Once deployed to Agent Runtime (`adk deploy agent_engine`), the platform
wraps `root_agent` itself and serves it via its own managed
VertexAiSessionService — this module's Runner does not run in production.
The daily-session-keying logic below is written to also work unmodified
against that managed service once a production caller (e.g. a backend
proxy) reuses it, since it never relies on a custom/deterministic
session id (see the "Custom/deterministic session IDs are currently
unreliable" note in the adk skill's deployment.md).
"""

from datetime import date as date_cls

from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, Session

from health_coach.agent import root_agent
from health_coach.services import firestore_db

APP_NAME = "health_coach"

session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=memory_service,
)


async def get_or_create_daily_session(user_id: str) -> Session:
    """Resolves today's session for this user, creating one if absent.

    Implements the Daily Session strategy without a deterministic session
    id: the SessionService always auto-generates the session id, and the
    (user_id, date) -> session_id mapping is tracked ourselves in
    Firestore via `firestore_db.get_session_id_for_date` /
    `set_session_id_for_date`. This sidesteps known issues with
    custom/user-supplied session ids on the managed Agent Runtime session
    service, while behaving identically locally.

    Args:
        user_id: The user's unique id. Required with no default so
            callers can't accidentally collide two different users onto
            the same session — SessionService keys sessions by
            (app_name, user_id, session_id), so distinct user_ids never
            share a session even on the same calendar date.

    Returns:
        The existing or newly created Session for today.
    """
    today = date_cls.today().isoformat()
    session_id = firestore_db.get_session_id_for_date(user_id=user_id, date=today)

    if session_id is not None:
        session = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if session is not None:
            return session
        # Recorded id is stale (e.g. session expired/was deleted) — fall
        # through and start a new one for today.

    session = await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, state={"user:id": user_id}
    )
    firestore_db.set_session_id_for_date(user_id=user_id, date=today, session_id=session.id)
    return session
