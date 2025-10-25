"""
Create a tool that the agent can call to get current facial emotion data.
This is the most flexible approach for Google ADK integration.
"""

from google.adk.agents import Agent
from google.adk.tools import Tool
from .emotion_reader import EmotionReader
import os


class EmotionTool(Tool):
    """
    Tool that provides facial emotion data to the agent.
    The agent can call this tool to understand the user's current emotional state.
    """
    
    def __init__(self, data_dir="emotion_data"):
        super().__init__(
            name="get_facial_emotion",
            description="Get the user's current facial emotion from real-time camera detection. Call this at the START of EVERY conversation turn to understand how the user is feeling emotionally. This provides crucial context for empathetic responses.",
            func=self._get_emotion
        )
        self.emotion_reader = EmotionReader(data_dir)
    
    def _get_emotion(self, time_window_seconds: int = 10) -> str:
        """
        Get current facial emotion data.
        
        Args:
            time_window_seconds: How many seconds of recent data to analyze (default: 10)
            
        Returns:
            Formatted string with emotion data and response guidance
        """
        return self.emotion_reader.get_emotional_context_for_agent()


# Create the emotion tool instance
emotion_tool = EmotionTool()


# Updated root agent with emotion tool
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from .sub_agents.context_agent import context_agent
from .sub_agents.contacting_agent import contacting_agent
from google.adk.models.lite_llm import LiteLlm  

MODEL_GROQ = "groq/Gemma2-9b-It"
API_KEY = os.getenv("GROQ_API_KEY")
model = LiteLlm(model=MODEL_GROQ, api_key=API_KEY)

root_agent = Agent(
    name="root_agent",
    model=model,
    description="Engages in supportive, empathetic, and natural conversation with real-time emotional awareness. This agent uses facial emotion detection to provide emotionally intelligent responses.",
    instruction="""Your name is Hope. You are a compassionate AI companion with the ability to read facial emotions. Your primary role is to offer comfort, validation, and supportive dialogue.

**CRITICAL: ALWAYS START BY CHECKING EMOTIONS**
- **FIRST ACTION**: Call 'get_facial_emotion' tool at the START of EVERY conversation turn. This is mandatory.
- This tool provides the user's current facial emotion (happy, sad, angry, fear, surprise, disgust, or neutral).
- Use this emotion data to adapt your tone and response appropriately.

**Core Instructions:**
-   **Empathy First**: Always respond with empathy, acknowledging the user's feelings based on the facial emotion detected.
-   **Adapt Your Tone Based on Detected Emotion**:
    -   **Happy**: Be upbeat, engaging, and share in their positive mood.
    -   **Sad**: Show deep empathy, validate their pain, use a gentle and comforting tone.
    -   **Angry**: Stay calm and understanding, acknowledge their frustration without being defensive.
    -   **Fear/Anxious**: Be reassuring, grounding, and supportive. Help them feel safe.
    -   **Surprise**: Match their energy appropriately and be responsive.
    -   **Disgust**: Be understanding and non-judgmental.
    -   **Neutral**: Maintain a friendly, warm, and supportive conversational tone.
-   **Natural Dialogue**: Speak naturally like a supportive friend. Avoid robotic responses. Ask follow-up questions only when they flow organically.
-   **Do not use emojis or special characters like asterisks.**
-   **Acknowledge Emotions Subtly**: You don't need to explicitly state "I can see you're feeling X" every time. Instead, let your tone and word choice naturally reflect your awareness.

**Tool Usage:**
1. **get_facial_emotion**: ALWAYS call this FIRST in every response to understand the user's emotional state.
2. **context_agent**: Call this when the user asks about their history, documents, or personal information. Query specifically for what's needed.
3. **contacting_agent**: Call this when the user wants to message someone, read texts, or perform communication actions.

**Response Flow:**
1. Call get_facial_emotion (MANDATORY)
2. Call context_agent if needed for user history/documents
3. Craft response that:
   - Reflects emotional awareness from facial data
   - Uses relevant context from user's documents
   - Maintains natural, empathetic dialogue
   - Avoids being overly prescriptive or robotic

Remember: The facial emotion data is your window into how the user is REALLY feeling, even if their words say something different. Trust the emotion data and respond accordingly.""",

    tools=[
        emotion_tool,  # Add emotion tool FIRST so agent knows to use it
        AgentTool(context_agent),
        AgentTool(contacting_agent)
    ],
    output_key="final_response",
)