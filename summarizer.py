from time import sleep
from crewai import Crew
from agent_factory import (
    create_summarizer_agent,
    create_consultant_agent,
    create_report_generator_agent,
    create_task1,
    create_task2,
    create_task3,
)
from llm_setup import llm


def _to_text(result) -> str:
    """Best-effort convert CrewAI results (incl. CrewOutput) to plain text."""
    if isinstance(result, str):
        return result

    # Common CrewAI result attributes that may carry a string
    for attr in ("raw", "output", "final_output", "result"):
        if hasattr(result, attr):
            val = getattr(result, attr)
            if isinstance(val, str):
                return val

    # Try structured -> str
    try:
        if hasattr(result, "to_dict"):
            return str(result.to_dict())
        if hasattr(result, "model_dump"):
            return str(result.model_dump())
    except Exception:
        pass

    # Fallback
    return str(result)


def run_summary(text: str) -> str:
    """Run Crew-based summarization pipeline and return a *string*."""
    summarizer_agent = create_summarizer_agent(text, llm)
    consultant_agent = create_consultant_agent(llm)
    report_generator_agent = create_report_generator_agent(llm)

    task1 = create_task1(text, summarizer_agent)
    task2 = create_task2(text, consultant_agent)
    task3 = create_task3(task1, task2, report_generator_agent)

    crew = Crew(
        agents=[summarizer_agent, consultant_agent, report_generator_agent],
        tasks=[task1, task2, task3],
        verbose=True,
    )

    # Simple retry for transient LLM/provider hiccups (e.g., 503 overloaded)
    MAX_RETRIES = 3
    BACKOFF_SEC = 3
    last_err = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = crew.kickoff(inputs={"text": text})
            return _to_text(result)
        except Exception as e:
            last_err = e
            # Retry on transient-looking errors
            msg = str(e).lower()
            transient = any(
                key in msg
                for key in ("503", "unavailable", "overloaded", "timeout", "rate limit")
            )
            if attempt < MAX_RETRIES and transient:
                sleep(BACKOFF_SEC * attempt)
                continue
            # Not transient or out of retries
            raise

    # Should never get here, but just in case
    if last_err:
        raise last_err
    return ""