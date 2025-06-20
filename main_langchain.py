import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters, stdio_client
import requests
import subprocess
from dotenv import load_dotenv
from langchain import hub
from langchain_litellm import ChatLiteLLM
from langchain_mcp_adapters.client import load_mcp_tools
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

API_KEY=os.getenv("API_KEY")
BASE_URL=os.getenv("BASE_URL")
API_URL = "http://localhost:8081/task/index/"
TEST_URL = "http://localhost:8082/test"
REPOS_DIR = "repos"
LOG_FILE = "results_langchain.log"

os.environ["OPENAI_API_KEY"] = API_KEY
os.environ["OPENAI_BASE_URL"] = BASE_URL

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", os.getcwd() + "/repos"]
)

async def handle_task(index):

    repo_dir = f"{REPOS_DIR}/repo_{index}"
    start_dir = os.getcwd()

    try:
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

        llm = ChatLiteLLM(model="gpt-4o-mini", temperature=0)

        prompt = hub.pull("hwchase17/openai-functions-agent")

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()

                # Get tools
                tools = await load_mcp_tools(session)

                # Create and run the agent
                agent = create_tool_calling_agent(llm, tools, prompt)
                agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
                await agent_executor.invoke({"input": "Create a file called fruits.txt with the content peach inside your allowed directory."})

        # Call REST service instead for evaluation changes from agent
        print(f"Calling SWE-Bench REST service with repo: {repo_dir}")
        test_payload = {
            "instance_id": instance_id,
            "repoDir": f"/repos/repo_{index}",  # mount with docker
            "FAIL_TO_PASS": fail_tests,
            "PASS_TO_PASS": pass_tests
        }
        res = requests.post(TEST_URL, json=test_payload)
        res.raise_for_status()
        result_raw = res.json().get("harnessOutput", "{}")
        result_json = json.loads(result_raw)
        if not result_json:
            raise ValueError("No data in harnessOutput – possible evaluation error or empty result")
        instance_id = next(iter(result_json))
        tests_status = result_json[instance_id]["tests_status"]
        fail_pass_results = tests_status["FAIL_TO_PASS"]
        fail_pass_total = len(fail_pass_results["success"]) + len(fail_pass_results["failure"])
        fail_pass_passed = len(fail_pass_results["success"])
        pass_pass_results = tests_status["PASS_TO_PASS"]
        pass_pass_total = len(pass_pass_results["success"]) + len(pass_pass_results["failure"])
        pass_pass_passed = len(pass_pass_results["success"])

        # Log results
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n")
            log.write(f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n")
        print(f"Test case {index} completed and logged.")

    except Exception as e:
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"Error: {e}\n")
        print(f"Error in test case {index}: {e}")

async def main():
    # for i in range(1, 301):
    await handle_task(4)


if __name__ == "__main__":
    asyncio.run(main())