import asyncio
from pathlib import Path
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core import CancellationToken
from autogen_agentchat.ui import Console
import requests
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

API_KEY=os.getenv("API_KEY")
BASE_URL="http://188.245.32.59:4000/"
API_URL = "http://localhost:8081/task/index/"
REPOS_DIR = "repos"

async def main() -> None:

    def write_file(content: str, file: str):
        f"""Writes {content} into {file}."""
        return subprocess.run(["echo", content, ">", file])

    repo_dir = f"{REPOS_DIR}/repo_1"

    response = requests.get(f"{API_URL}13")
    task_content = response.json()
    issue = task_content["Problem_statement"]

    # Setup server params for local filesystem access
    allowed_dir = str(Path.home() / "workspace/automated-software-engineering/repos")
    server_params = StdioServerParams(
        command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", allowed_dir]
    )

    # Get all available tools from the server
    tools = await mcp_server_tools(server_params)

    planner = AssistantAgent(
        name="planner",
        model_client=OllamaChatCompletionClient(model="llama3.1"),
        reflect_on_tool_use=True,
        model_client_stream=True,
        system_message="""
    You are a planning agent.
    Your job is to break down complex tasks into smaller, manageable subtasks.
    Your team members are:
        Coder: Solves issues by writing code into files
        Tester: Checks whether the written code solves the issue

    You only plan and delegate tasks - you do not execute them yourself.

    When assigning tasks, use this format:
    1. <agent> : <task>

    After all tasks are complete, summarize the findings and end with "TERMINATE".
    """
    )

    # Create an agent that can use all the tools
    coder = AssistantAgent(
        name="coder",
        # model_client=OpenAIChatCompletionClient(model="gpt-4o-mini", api_key=API_KEY, base_url=BASE_URL),
        model_client=OllamaChatCompletionClient(model="llama3.1"),
        tools=[write_file],  # type: ignore
        reflect_on_tool_use=True,
        model_client_stream=True,
        system_message="You are a helpful assistant that can write code into files."
    )

    tester = AssistantAgent(
        name="tester",
        model_client=OllamaChatCompletionClient(model="llama3.1"),
        reflect_on_tool_use=True,
        model_client_stream=True,
        system_message="You are a helpful assistant that can check whether a task was executed properly."
    )

    # The agent can now use any of the filesystem tools
    termination = TextMentionTermination("TERMINATE")
    team = RoundRobinGroupChat([planner, coder, tester])
    await Console(coder.run_stream(task=f"Solve the following issue: {issue} Edit the files with your changes inside the {allowed_dir}/repo_13/django. The changes have to be visible inside git diff."))

asyncio.run(main())