import asyncio
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.ui import Console
import requests
import os
import subprocess
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY=os.getenv("API_KEY")
BASE_URL="http://188.245.32.59:4000/"
API_URL = "http://localhost:8081/task/index/"
REPOS_DIR = "repos"

litellm_model_client = OpenAIChatCompletionClient(
    model="gpt-4o",
    api_key=API_KEY,
    base_url=BASE_URL,
    max_tokens=4096,
    temperature=0
)

async def handle_task(index):

    repo_dir = f"{REPOS_DIR}/repo_{index}"

    response = requests.get(f"{API_URL}{index}")
    task_content = response.json()

    instance_id = task_content["instance_id"]
    issue = task_content["Problem_statement"]
    fail_tests = json.loads(task_content.get("FAIL_TO_PASS", "[]"))
    pass_tests = json.loads(task_content.get("PASS_TO_PASS", "[]"))
    git_clone = task_content["git_clone"].split("&&")
    repo_url = git_clone[0].split()[2]
    commit_hash = git_clone[2].split()[2]

    if not os.path.isdir(repo_dir):
        subprocess.run(["git", "clone", repo_url, repo_dir])
    subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir)

    allowed_dir = os.getcwd()
    server_params = StdioServerParams(
        command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", allowed_dir]
    )

    tools = await mcp_server_tools(server_params)

    planner = AssistantAgent(
        name="planner",
        model_client=litellm_model_client,
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

    coder = AssistantAgent(
        name="coder",
        model_client=litellm_model_client,
        tools=tools,
        system_message=f"""You are a programming agent. 
        Your job is to solve the tasks given by the planner agent. 
        Write your changes in the respective files so that they are visible in `git diff`."""
    )

    tester = AssistantAgent(
        name="tester",
        model_client=litellm_model_client,
        tools=tools,
        system_message="""You are a testing agent. Your job is to check whether the changes made by the coder agent solve the task." \
        If they are incorrect, provide a possible solution that the coder agent can apply.
        You don't run any actual test suites, just take a look at the changes and tell if they are correct."""
    )

    full_prompt = (
            f"Work in the directory: {allowed_dir}/repo_{index}. This is a Git repository.\n"
            f"Your goal is to fix the problem described below.\n"
            f"All code changes must be saved to the files, so they appear in `git diff`.\n"
            f"Problem description:\n"
            f"{issue}\n\n"
            f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests."
        )

    text_mention_termination = TextMentionTermination("TERMINATE")
    max_messages_termination = MaxMessageTermination(max_messages=25)
    team = RoundRobinGroupChat([planner, coder, tester], termination_condition=text_mention_termination | max_messages_termination)
    await Console(team.run_stream(task=full_prompt))

asyncio.run(handle_task(13))