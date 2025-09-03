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

from hope_v3 import root_agent

# Project configuration
load_dotenv() # Load .env file at the beginning for PROJECT_ID
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")

if not PROJECT_ID or PROJECT_ID == "[your-project-id]":
    PROJECT_ID = str(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    if not PROJECT_ID:
        # Improved error message for PROJECT_ID
        raise ValueError("Project ID not found. Please set it in your .env file as 'PROJECT_ID' or as the GOOGLE_CLOUD_PROJECT environment variable.")


# Set environment variables required for ADK
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

# Agent configuration
MODEL_NAME = "gemini-2.5-flash" 
USER_ID = f"user_{uuid.uuid4()}"


def run_single_turn(query, runner, session, user_id):
    """Run a single conversation turn."""
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
                    print(f"    Text (first 50 chars): {part.text[:50]}...")
                if hasattr(part, 'function_call') and part.function_call:
                    print(f"    Function Call Name: {part.function_call.name}")
                    print(f"    Function Call Args: {part.function_call.args}")
            # --- END Enhanced debugging ---

            # Extract the actual text response for the chat loop
            if event.content.parts and hasattr(event.content.parts[0], 'text'):
                response_content = event.content.parts[0].text
            else:
                response_content = "Assistant: (No readable text response)" # Fallback

    return response_content


def chat_loop(session, runner, user_id) -> None:
    """Main chat interface loop."""
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

    # Initialize Vertex AI client
    _ = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    print("\n--- Creating Agent Engine ---")
    agent_engine = agent_engines.create() # Await the create call
    print(f"Created Agent Engine: {agent_engine.resource_name}")

    app_name = "my_agent_" + str(uuid.uuid4())[:6]
    agent_engine_id = agent_engine.name

    memory_bank_service = VertexAiMemoryBankService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine_id
    )

    session_service = VertexAiSessionService(
        project=PROJECT_ID, location=LOCATION, agent_engine_id=agent_engine_id
    )

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        memory_service=memory_bank_service,
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
    # For the second session, ensure app_name is consistent or correctly identifies the agent
    session2 = await runner.session_service.create_session(
        app_name=app_name, # Use app_name for consistency with the runner's registration
        user_id=USER_ID,
    )
    chat_loop(session2.id, runner, USER_ID)

    delete_engine = True

    if delete_engine:
        print(f"\nDeleting AgentEngine resource: {agent_engine.resource_name}")
        agent_engines.delete(resource_name=agent_engine.resource_name, force=True) # Await the delete call
        print(f"AgentEngine resource deleted: {agent_engine.resource_name}")


if __name__ == "__main__":
    asyncio.run(main())