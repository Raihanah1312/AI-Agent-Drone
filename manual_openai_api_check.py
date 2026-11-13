
import os
from dotenv import load_dotenv
from agents import Agent, Runner

load_dotenv()

agent = Agent(
    name="Drone Assistant",
    model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    instructions="Jawab singkat dalam bahasa Indonesia."
)

result = Runner.run_sync(
    agent,
    "Halo, apakah AI Agent Drone saya sudah terhubung?"
)

print(result.final_output)
