"""
Foundry Hosted Agent — Responses protocol wrapper around the existing ADK greeting_agent.

Heavy imports (google-adk, litellm, llama-index) are deferred to the FIRST request
so the hypercorn server binds to port 8088 and the /readiness probe passes in ~1s.
The first request will be slower (~30-60s cold start); subsequent requests are fast.
"""

from azure.ai.agentserver.responses import ResponsesAgentServerHost
from azure.ai.agentserver.responses._response_context import ResponseContext
from azure.ai.agentserver.responses.models import CreateResponse
from azure.ai.agentserver.responses.streaming._text_response import TextResponse
from azure.ai.agentserver.responses.store._memory import InMemoryResponseProvider

# Server starts immediately — heavy ADK/LiteLLM imports are deferred to first request
app = ResponsesAgentServerHost(store=InMemoryResponseProvider())

# Lazy singletons, initialised on first request
_runner = None
_session_service = None


async def _get_runner():
    """Return the ADK Runner, initialising it on the first call."""
    global _runner, _session_service
    if _runner is None:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai.types import Content, Part           # google-adk 2.x — types live in google.genai
        from greeting_agent.agent import root_agent   # triggers LiteLLM + az-identity init
        _session_service = InMemorySessionService()
        _runner = Runner(
            agent=root_agent,
            app_name="greeting_agent",
            session_service=_session_service,
        )
    return _runner


@app.response_handler
async def handle_response(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal,
):
    import sys, traceback
    try:
        from google.genai.types import Content, Part   # also deferred

        input_text = await context.get_input_text()
        session_id = context.conversation_id or context.response_id or "default"
        runner = await _get_runner()
        user_msg = Content(role="user", parts=[Part(text=input_text)])

        async def token_stream():
            # ADK 2.x: run_async() raises SessionNotFoundError when an explicit session_id
            # is passed but the session doesn't exist yet — create it first.
            try:
                await _session_service.create_session(
                    app_name="greeting_agent",
                    user_id=session_id,
                    session_id=session_id,
                )
            except Exception:
                pass  # Session already exists (multi-turn) — that's fine

            async for event in runner.run_async(
                user_id=session_id,
                session_id=session_id,
                new_message=user_msg,
            ):
                if cancellation_signal.is_set():
                    return
                if event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            yield part.text

        return TextResponse(context, request, text=token_stream())

    except Exception as exc:
        print(f"HANDLER ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise


if __name__ == "__main__":
    # Port defaults to 8088 (or PORT env var) — the Foundry gateway expects 8088
    app.run()
