from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

llm=LLM(
    model="gemini/gemini-2.0-flash",
    temperature=0.1
)