import asyncio
import json
import os
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
import requests
import subprocess
from dotenv import load_dotenv
from langchain.agents import create_tool_calling_agent, create_react_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain import hub
from prompts import planner_prompt, coder_prompt, tester_prompt

load_dotenv()

API_KEY=os.getenv("API_KEY")
BASE_URL=os.getenv("BASE_URL")
API_URL = "http://localhost:8081/task/index/"
TEST_URL = "http://localhost:8082/test"
REPOS_DIR = "repos"
LOG_FILE = "results_langchain.log"

os.environ["OPENAI_API_KEY"] = API_KEY
os.environ["OPENAI_BASE_URL"] = BASE_URL

async def handle_task(index):

    repo_dir = f"{REPOS_DIR}/repo_{index}"
    start_dir = os.getcwd()
    allowed_dir = os.getcwd() + "/repos"

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

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You are a helpful assistant"),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        client = MultiServerMCPClient(
            {
                "filesystem": {
                    "command": "npx",
                    "args": [
                        "-y",
                        "@modelcontextprotocol/server-filesystem",
                        allowed_dir
                    ],
                    "transport": "stdio",
                },
            }
        )

        planner_tools = []
        mcp_tools = await client.get_tools()

        # Create and run the agent
        planner = create_tool_calling_agent(llm, mcp_tools, prompt)
        coder = create_tool_calling_agent(llm, mcp_tools, prompt)
        tester = create_tool_calling_agent(llm, mcp_tools, prompt)

        planner_agent_executor = AgentExecutor(agent=planner, tools=planner_tools, verbose=True)
        coder_agent_executor = AgentExecutor(agent=coder, tools=mcp_tools, verbose=True)
        tester_agent_executor = AgentExecutor(agent=tester, tools=mcp_tools, verbose=True)

        for i in range(25):
            planner_output = await planner_agent_executor.ainvoke({"input": issue})
            coder_output = await coder_agent_executor.ainvoke({"input": f"Solve the following tasks:\n {planner_output}\nApply your changes to the respective files."})
            tester_output = await tester_agent_executor.ainvoke({"input": tester_prompt + "\nIf everything fits your expectations output the string TERMINATE"})
            if ("TERMINATE" in tester_output):
                break

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
    for i in range(1, 301):
        await handle_task(i)


if __name__ == "__main__":
    asyncio.run(main())