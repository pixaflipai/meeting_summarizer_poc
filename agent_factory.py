from crewai import Agent, Task


def create_summarizer_agent(text, llm):
    return Agent(
        role="Meeting Summarizer",
        goal=f"Summarize the meeting in very comprehensive and concise way: {text}",
        backstory="""You are an extremely experienced secretary who summarizes the meeting in a concise and
                    comprehensive form without skipping the important points that were discussed during the meeting.
                    This helps the company stakeholders stay updated.""",
        llm=llm,
        verbose=True,
    )

def create_consultant_agent(llm):
    return Agent(
        role="Senior AI Consultant",
        goal="Help the team to suggest breakthroughs to their current problems or suggest better approaches to reaching the goal.",
        backstory="""You are a highly experienced AI consultant specializing in Python and have been working with top firms for years.
                    You go through the discussion that happened in the meeting transcription and wherever you notice a roadblock being discussed,
                    you suggest a breakthrough.""",
        llm=llm,
        verbose=True,
    )

def create_report_generator_agent(llm):
    return Agent(
        role="Expert Report Generator",
        goal="Take the output from both of the agents and generate a high-level report",
        backstory="""You are an expert report generator who generates the reports compiling the different outputs into a single document
                    that shall be presented to the company stakeholders keeping them updated regarding the projects.""",
        llm=llm,
        verbose=True,
    )

def create_task1(text, summarizer_agent):
    return Task(
        description=f"Summarize the given {text} transcription of the meeting in a very comprehensive way in 300 words.",
        expected_output="2-3 paragraphs perfectly formatted",
        agent=summarizer_agent,
    )

def create_task2(text, consultant_agent):
    return Task(
        description=f"Go through the {text} and wherever a roadblock is encountered or a better approach to the problem is available, suggest breakthroughs.",
        expected_output="""Problem: Describe the problem \n
                           Current approach: What is the current decided approach of the team \n
                           Suggested approach: A better approach to the problem than the one currently decided by the team \n""",
        agent=consultant_agent,
    )

def create_task3(task1, task2, report_generator_agent):
    return Task(
        description=f"Take the outputs of other tasks and generate a report summary which is very high-level and can be comprehended by non-technical readers",
        expected_output="""Meeting Summary (This heading shall be in the center of the document) \n\n
                          The whole document summary in paragraphs.
                          Encountered Problems: Only list the problems in bullet points, not the breakthroughs.
                          """,
        agent=report_generator_agent,
        context=[task1, task2],
    )
