import asyncio
import uuid
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from hope_updated import root_agent
from google.adk.memory import InMemoryMemoryService
from google.adk.tools import load_memory # Tool to query memory
from google.adk.agents import LlmAgent
import os
from google.adk.models.lite_llm import LiteLlm  


MODEL_GROQ = "groq/Gemma2-9b-It"
API_KEY = os.getenv("GROQ_API_KEY")
model = LiteLlm(model=MODEL_GROQ, api_key=API_KEY)

load_dotenv()

memory_recall_agent = LlmAgent(
    model=model,
    name="MemoryRecallAgent",
    instruction="Answer the user's question. Use the 'load_memory' tool "
                "if the answer might be in past conversations.",
    tools=[load_memory] # Give the agent the tool
)

async def main():

    # Create a new session service to store state
    session_service_stateful = InMemorySessionService()
    memory_service = InMemoryMemoryService()


    # If any you want any agnet to have state information, you can have intital state here.
    initial_state = {
        "name": "John Doe",
    }

    APP_NAME = "Hope"
    USER_ID = "hope"
    SESSION_ID = "session123"


    stateful_session = await session_service_stateful.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state=initial_state,
    )

    print("CREATED NEW SESSION:")
    print(f"\tSession ID: {SESSION_ID}")

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service_stateful,
        memory_service=memory_service,
    )

    # Refer to this code when making requests to the agent. Create API here.

    new_message = types.Content(
        role="user", parts=[types.Part(text="I like red SUVs." )]
    )

    for event in runner.run(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=new_message,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                print(f"Final Response: {event.content.parts[0].text}")

    print("==== Session Event Exploration ====")
    session = await session_service_stateful.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )

    # Log final Session state
    # To get the output, we can store it in "output_key" as specifiec in the agent.
    # simple use session.state.get("xyz") to get the value of xyz output key.
    print("=== Final Session State ===")
    for key, value in session.state.items():
        print(f"{key}: {value}")

    print("\n--- Adding Session 1 to Memory ---")
    await memory_service.add_session_to_memory(session)
    print("Session added to memory.")

    print("\n--- Turn 2: Recalling Information ---")

    runner2 = Runner(
        # Use the second agent, which has the memory tool
        agent=memory_recall_agent,
        app_name=APP_NAME,
        session_service=session_service_stateful, # Reuse the same service
        memory_service=memory_service   # Reuse the same service
    )

    session2_id = "session_recall"
    await runner2.session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session2_id)
    user_input2 = types.Content(parts=[types.Part(text="Guess what car I was thinking of buying?")], role="user")

    # Run the second agent
    final_response_text_2 = "(No final response)"
    async for event in runner2.run_async(user_id=USER_ID, session_id=session2_id, new_message=user_input2):
        if event.is_final_response() and event.content and event.content.parts:
            final_response_text_2 = event.content.parts[0].text
    print(f"Agent 2 Response: {final_response_text_2}")



if __name__ == "__main__":
    asyncio.run(main())