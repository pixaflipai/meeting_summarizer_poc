import streamlit as st
import sys
import importlib
from pathlib import Path
try:
    import pysqlite3  # wheels import under this name
except Exception:
    importlib.import_module("pysqlite3")
sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
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
TRANSCRIPTS_DIR=Path("transcripts_txt")

all_files=sorted(
    TRANSCRIPTS_DIR.glob("meeting_*.txt"),
    key=lambda p:p.stat().st_mtime,
    reverse=True
)
if not all_files:
    st.warning("No transcripts found in 'transcripts_txt/'.")
    st.stop()

labels = [p.stem.replace("meeting_", "") for p in all_files]
choice = st.selectbox("Choose a meeting to summarize:", labels, index=0)
selected_path = all_files[labels.index(choice)]

if st.button("Summarize Meeting"):
    try:
        with st.spinner("Step 1/2: Extracting the text from uploaded file."):
            text = selected_path.read_text(encoding="utf-8")
            st.success(f"Loaded: {selected_path.name} ")

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
