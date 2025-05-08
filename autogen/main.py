import os
import subprocess
import requests
import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import StructuredMessage
from autogen_agentchat.ui import Console
from autogen_ext.models.ollama import OllamaChatCompletionClient

API_URL = "http://localhost:8081/task/index/"  # API endpoint for SWE-Bench-Lite
LOG_FILE = "results.log"
REPOS_DIR = "repos"

model_client = OllamaChatCompletionClient(
    model="llama3.2:1b",
)

agent = AssistantAgent(
    name="software_engineer_agent",
    model_client=model_client,
    system_message="You are a professional software engineer."
)

async def handle_task(index):
    
    repo_dir = f"{REPOS_DIR}/repo_{index}"
    response = requests.get(f"{API_URL}{index}")
    testcase = response.json()
    prompt = testcase["Problem_statement"]
    parts = testcase["git_clone"].split("&&")
    clone_parts = parts[0].strip()
    repo_url = clone_parts.split()[2]
    checkout_part = parts[-1].strip() if len(parts) > 1 else None
    
    if not os.path.exists(repo_dir): 
        subprocess.run(["git", "clone", repo_url, repo_dir])

    if checkout_part:
            commit_hash = checkout_part.split()[-1]
            subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir)

    full_prompt = (
            f"You are a software engineer.\n"
            f"Work in the directory: repo_{index}. This is a Git repository.\n"
            f"Your goal is to fix the problem described below.\n"
            f"All code changes must be saved to the files, so they appear in `git diff`.\n"
            f"The fix will be verified by running the affected tests.\n\n"
            f"Problem description:\n"
            f"{prompt}\n\n"
            f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests."
    )

    await agent.run(task=full_prompt)
    
    
    




asyncio.run(handle_task(1))