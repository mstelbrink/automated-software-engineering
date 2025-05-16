from langchain_community.agent_toolkits import FileManagementToolkit
from autogen_ext.tools.langchain import LangChainToolAdapter
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.models.ollama import OllamaChatCompletionClient

import requests
import os
import subprocess
import asyncio
from dotenv import load_dotenv

load_dotenv()

API_KEY=os.getenv("API_KEY")
WORK_DIR=os.getenv("WORK_DIR")
BASE_URL="http://188.245.32.59:4000/"
API_URL = "http://localhost:8081/task/index/"
REPOS_DIR = "repos"

toolkit = FileManagementToolkit()

tools = [LangChainToolAdapter(tool) for tool in toolkit.get_tools()]

ollama_model_client = OllamaChatCompletionClient(
    model="llama3.1",
)

litellm_model_client = OpenAIChatCompletionClient(
    model="gpt-4o-mini",
    api_key=API_KEY,
    base_url=BASE_URL
)

agent = AssistantAgent(
    name="file_manager",
    model_client=ollama_model_client,
    tools=tools,
    system_message="You are a a file manager.",
)

async def main(index) -> None:

    repo_dir = f"{REPOS_DIR}/repo_{index}"

    response = requests.get(f"{API_URL}{index}")
    task_content = response.json()

    instance_id = task_content["instance_id"]
    issue = task_content["Problem_statement"]
    # fail tests
    # pass tests
    git_clone = task_content["git_clone"].split("&&")
    repo_url = git_clone[0].split()[2]
    repo_name = git_clone[1].split()[1]
    commit_hash = git_clone[2].split()[2]

    if not os.path.isdir(repo_dir):
        subprocess.run(["git", "clone", repo_url, repo_dir])
    subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir)

    full_prompt = (
        f"You are a helpful coder.\n"
        f"Work in the directory: {WORK_DIR}/repos/repo_{index}/{repo_name}. This is a Git repository.\n"
        f"Your goal is to fix the problem described below.\n"
        f"Work by executing the following steps:\n"
        f"1. List all directories.\n"
        f"2. Locate files that contain the error.\n"
        f"3. Copy the entire code from each file and apply your changes in your own temporary environment."
        f"3. Insert your changes from your temporary environment into the respective files. \n"
        f"All code changes must be saved to the files, so they appear in `git diff`.\n\n"
        f"Problem description:\n"
        f"{issue}\n\n"
        f"Make sure the fix is minimal and only touches what's necessary to resolve the issue."
    )

    await Console(agent.run_stream(task=full_prompt))
    await ollama_model_client.close()

asyncio.run(main(13))