import streamlit as st
from crewai import Crew
from agent_factory import create_summarizer_agent, create_consultant_agent, create_report_generator_agent, create_task1, create_task2, create_task3
from llm_setup import llm

st.set_page_config(page_title="Meeting Summarizer", layout="wide")
st.title("Meeting Summarizer")

st.sidebar.header("Instructions")
st.sidebar.info("""
                \n
                1. Upload the same file here. \n
                2. Click 'Analyze Repository' to start the analysis. \n
                \n
                This process may take several minutes depending on the meeting duration.
                """)

file = st.file_uploader(label="meeting.txt")

if st.button("Summarize Meeting"):
    if not file:
        st.error("Please upload the meeting transcript")
    else:
        try:
            with st.spinner("Step 1/2: Extracting the text from uploaded file."):
                text=file.read().decode("utf-8")
                st.success("Text Extraction Successful !")

            with st.spinner("Step 2/2: The AI crew is summarizing this meeting. This may take a while."):
                
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

                result = crew.kickoff(inputs={"text": text})
                st.success("Summarization Complete !")

            st.markdown(result)

        except Exception as e:
            st.error(f"An error occurred: {e}")
