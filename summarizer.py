from crewai import Crew
from agent_factory import (
    create_summarizer_agent, create_consultant_agent,
    create_report_generator_agent, create_task1, create_task2, create_task3
)
from llm_setup import llm

def run_summary(text: str) -> str:
    """Run Crew-based summarization pipeline and return the result."""
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

    return crew.kickoff(inputs={"text": text})