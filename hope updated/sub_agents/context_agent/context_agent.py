from google.adk.agents import Agent
import os
from google.adk.models.lite_llm import LiteLlm  


MODEL_GROQ = "groq/Gemma2-9b-It"
API_KEY = os.getenv("GROQ_API_KEY")
model = LiteLlm(model=MODEL_GROQ, api_key=API_KEY)

file_path = "/Users/Pranav/Coding/Hope-Final-Year-Project/Patient Name_ John Doe.pdf"

from pypdf import PdfReader

document_content = ""
try:
    reader = PdfReader(file_path)
    for page in reader.pages:
        document_content += page.extract_text() or "" # Handles cases where a page might not have extractable text
except Exception as e:
    print(f"Error reading PDF with pypdf: {e}")

context_agent = Agent(
    name="context_agent",
    model=model,
    description="Processes a full document passed into its context to find specific information. Use this agent to answer a user's question by directly reading through provided text to find relevant details about their background or medical history.",
    instruction=f"""You are a specialized agent for information extraction. Your task is to carefully read the provided document to find the answer to a specific user query.

        **Your Instructions:**
        1.  You will be given a document and a user's query below.
        2.  Thoroughly read the document to locate the specific section(s) that directly answer the query.
        3.  Synthesize the information you find into a concise, factual summary that directly answers the question.
        4.  If the document does not contain the information needed, you must explicitly state: "No context found." Do not try to answer from your general knowledge.

        ---
        **DOCUMENT CONTENT:**
        {document_content}
        ---

        Only respond with the relevant information from the document. Do not include any additional commentary or general knowledge. If you cannot find the answer in the document, respond with No context found
    """,
    sub_agents=[],
    tools=[],
)