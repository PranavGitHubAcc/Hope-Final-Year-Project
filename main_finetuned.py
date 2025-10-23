import asyncio
import uuid
import os
from dotenv import load_dotenv

from google.adk.runners import Runner
from google.genai import types

import vertexai
from vertexai import agent_engines
from google.adk.memory import VertexAiMemoryBankService
from google.adk.sessions import VertexAiSessionService
from google.adk.tools.agent_tool import AgentTool

# Import root_agent and your sub-agent instances from hope_v3
from hope_finetuned import root_agent
from hope_finetuned.sub_agents.contacting_agent import contacting_agent


# Project configuration
load_dotenv()
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")

if not PROJECT_ID or PROJECT_ID == "[your-project-id]":
    PROJECT_ID = str(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    if not PROJECT_ID:
        raise ValueError("Project ID not found. Please set it in your .env file as 'PROJECT_ID' or as the GOOGLE_CLOUD_PROJECT environment variable.")

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

USER_ID = f"user_{uuid.uuid4()}"


def run_single_turn(query, runner, session, user_id):
    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=user_id, session_id=session, new_message=content)

    response_content = None
    for event in events:
        if event.is_final_response():
            print("\n--- Final response received ---")
            print("All parts in final response:")
            for i, part in enumerate(event.content.parts):
                print(f"  Part {i}: type={type(part)}")
                if hasattr(part, 'text') and part.text:
                    print(f"    Text (first 100 chars): {part.text[:100]}...")
                if hasattr(part, 'function_call') and part.function_call:
                    print(f"    Function Call Name: {part.function_call.name}")
                    print(f"    Function Call Args: {part.function_call.args}")
                if hasattr(part, 'function_response') and part.function_response:
                    print(f"    Function Response Name: {part.function_response.name}")
                    print(f"    Function Response Content: {part.function_response.response}")

            if event.content.parts and hasattr(event.content.parts[0], 'text'):
                response_content = event.content.parts[0].text
            else:
                response_content = "Assistant: (No readable text response)"

    return response_content


def chat_loop(session, runner, user_id) -> None:
    print("\nStarting chat. Type 'exit' or 'quit' to end.")
    print("Every message will be automatically stored in memory.\n")

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit", "bye"]:
            print("\nAssistant: Thank you for chatting. Have a great day!")
            break

        response = run_single_turn(user_input, runner, session, user_id)
        if response:
            print(f"\nAssistant: {response}")


async def main():
    print(f"Project: {PROJECT_ID}")
    print(f"Location: {LOCATION}")
    print(f"Session User ID: {USER_ID}")

    _ = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    print("\n--- Creating Agent Engine ---")
    agent_engine = agent_engines.create()
    print(f"Created Agent Engine: {agent_engine.resource_name}")

    app_name = "my_agent_" + str(uuid.uuid4())[:6]
    agent_engine_id = agent_engine.name

    memory_bank_service = VertexAiMemoryBankService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine_id
    )

    session_service = VertexAiSessionService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine_id
    )

    # --- CUSTOM MEMORY RETRIEVAL TOOL DEFINITION ---
    # This asynchronous function will be wrapped by adk.tools.Tool
    async def recall_past_memories(query: str) -> str:
        print(f"\n[Tool Call] Calling 'recall_past_memories' with query: '{query}'")
        memories = await memory_bank_service.search_memory(app_name=app_name,user_id=USER_ID, query=query)
        if memories:
            # Format memories into a readable string for the LLM
            # You can customize this formatting
            formatted_memories = "\n".join([f"- {m.content.parts[0].text}" for m in memories.memories if m.content and m.content.parts])
            if formatted_memories == "":
                return "No relevant past memories found."
            print("Formatted Memories:\n", formatted_memories)
            return f"The user in previous conversations had mentioned:\n{formatted_memories}"
        return "No relevant past memories found."


    # --- Define all tools for the Runner ---
    runner_tools = [
        recall_past_memories, # Our custom memory tool
        AgentTool(contacting_agent) # Your contacting agent
    ]

    # Assign the concrete tool instances to root_agent's tools list
    # This makes sure the agent is aware of all tools.
    root_agent.tools = runner_tools


    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        memory_service=memory_bank_service, # Still needed for add_session_to_memory
    )


    print("\n--- Starting First Session (Information Gathering) ---")
    session1 = await runner.session_service.create_session(
        app_name=app_name,
        user_id=USER_ID,
    )
    chat_loop(session1.id, runner, USER_ID)

    completed_session = await runner.session_service.get_session(
        app_name=app_name, user_id=USER_ID, session_id=session1.id
    )

    print("\n--- Adding Session 1 to Memory Bank ---")
    await memory_bank_service.add_session_to_memory(completed_session)
    print("Session added to memory.")

    print("\n--- Starting Second Session (Memory Recall) ---")
    session2 = await runner.session_service.create_session(
        app_name=app_name, # Use app_name for consistency
        user_id=USER_ID,
    )
    chat_loop(session2.id, runner, USER_ID)

    delete_engine = True

    if delete_engine:
        print(f"\nDeleting AgentEngine resource: {agent_engine.resource_name}")
        agent_engines.delete(resource_name=agent_engine.resource_name, force=True)
        print(f"AgentEngine resource deleted: {agent_engine.resource_name}")


if __name__ == "__main__":
    asyncio.run(main())