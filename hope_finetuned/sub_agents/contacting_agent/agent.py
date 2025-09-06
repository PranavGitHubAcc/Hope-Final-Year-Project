from google.adk.agents import Agent
from .tools.receive_message_tool import receive_message_tool
from .tools.send_message_tool import send_message_tool
import json


with open("contacts.json", "r") as file:
    data = json.load(file)

contacting_agent = Agent(
    name="contacting_agent",
    model="gemini-2.5-flash",
    description="Manages all communication tasks. This agent can send new messages to contacts or check for and read incoming messages. It should be used for any request involving 'send', 'text', 'message', 'msg', or 'read my messages'.",
    instruction=f"""You are a messaging assistant. Your sole purpose is to help the user communicate with their contacts.
    
        These are the contacts you can message:
        {data}

    -   **Sending Messages**: If the user wants to send a message, identify the recipient and the exact message content. Use the 'send_message_tool' to send it. Confirm with the user after the message has been sent.
    -   **Receiving Messages**: If the user asks to check their messages, use the 'receive_message_tool' to retrieve and read the latest message.
    -   Be clear, concise, and direct. Do not engage in conversation beyond what is required for the messaging task.
    -   Return control to orchastrator after sending or reading messages.
    -   When reading messages, use the contacts to find the name of the sender and return the message content.""",
    sub_agents=[],
    tools=[send_message_tool, receive_message_tool],
)
