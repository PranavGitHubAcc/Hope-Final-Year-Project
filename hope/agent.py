from .sub_agents.conversation_agent.agent import conversation_agent
from .sub_agents.contacting_agent.agent import contacting_agent
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.models.lite_llm import LiteLlm  
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
import os
from google.adk.models.lite_llm import LiteLlm  


MODEL_GROQ = "groq/Gemma2-9b-It"
API_KEY = os.getenv("GROQ_API_KEY")
model = LiteLlm(model=MODEL_GROQ, api_key=API_KEY)


root_agent = Agent(
    name="root_agent",
    model=model,
    description="""The main controller agent that analyzes the user's intent and routes the task to the appropriate specialized agent (Conversation or Contacting).""",
    instruction=
    """
        You are the central orchestrator of an AI companion system. Your job is to analyze the user's input and delegate the task to the correct sub-agent.

        1.  **Analyze Intent**: First, determine the user's primary goal.
            -   Does the user want to send, text, or read a message? If yes, route to the **'contacting_agent'**.
            -   Is the user asking a question, sharing feelings, or just talking? If yes, this is a conversational task. 

        2.  **Analyze Emotion (for Conversation)**: If the intent is conversational, use the **'emotion_tool'** to determine the user's emotional state from the available data (text, voice, etc.).

        3.  **Route to Conversation Agent**: After analyzing the emotion, route the user's original input AND the determined emotional state to the **'conversation_agent'** for an empathetic response.
        4. The conversation agent will return a response based on the input. Simply return the input do not add any additional information or context.

        Do not engage in any conversation yourself. Your role is to route tasks to the appropriate agents based on the user's intent and emotional state.
        Your final output should be the decision of which agent to call and the necessary inputs for that agent.
    """,
    sub_agents=[],
    tools=[AgentTool(conversation_agent), AgentTool(contacting_agent)],
)

    






