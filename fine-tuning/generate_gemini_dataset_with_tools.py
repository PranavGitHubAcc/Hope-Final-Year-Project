import google.generativeai as genai
import json
import os
import time
from dotenv import load_dotenv
import textwrap


def build_prompt(user_input: str, model_response: str) -> str:
    """
    Builds the complete, one-shot prompt for the LLM by injecting the
    user input and model response into a structured template.
    """
    # This is the exact prompt template we designed.
    # It provides clear instructions and a perfect example for the LLM to follow.
    prompt_template = """\
        **System Prompt:**

        You are an expert AI data engineer specializing in creating synthetic datasets for fine-tuning Google's Gemini models. Your task is to convert a given user/model conversation pair into a single, complete JSON object that follows a specific multi-turn, tool-calling format required for Vertex AI fine-tuning.

        You must follow the instructions and the provided example precisely. Your final output must be ONLY the valid JSON object, with no explanatory text, markdown, or any other characters before or after it.

        **Core Instructions:**

        1.  **Always Call the Tool:** The model's first action after the user's message MUST BE a `functionCall` to the `recall_past_memories` tool. The `query` argument must be a concise, lowercase summary of the user's message.

        2.  **Inject Personal Context (Crucial):** Before creating the JSON, you must first mentally invent a plausible, specific detail or backstory from a *hypothetical past conversation*. This detail must be directly relevant to the user's current message. Use this invented backstory to create a highly specific and personalized `functionResponse`.

            *   **Example A:** If the user says, `"I don't like John,"` you might invent the backstory that `"John is the user's rude manager."` The resulting `functionResponse` would then be: `"Retrieved relevant past memories:\n- John is the user's manager, who they have described as rude."`
            *   **Example B:** If the user says, `"I want to get a new pet,"` you could invent the backstory that `"the user's previous dog, a beagle named Max, passed away last year."` The `functionResponse` would then be: `"Retrieved relevant past memories:\n- The user's beloved beagle, Max, passed away last year."`

        3.  **Simulate Tool Output:** You must create a `functionResponse`.
            *   For approximately 70 percent of examples, generate a personalized memory based on the context you invented in step 2.
            *   For the other 30 percent of examples, the tool's response content MUST be exactly: `"No relevant past memories found."`

        4.  **Preserve and Enhance the Final Response:** You must generate the model's final text response. This response MUST be a high-quality, rewritten version of the **Original Final Model Response**.
            *   If you invented a memory, you **must** subtly weave that specific detail into the original response to show the context was used.
            *.  There is no need to always use the invented memory, but if it fits naturally, include it.
            *   If no memories were found, the original response can be used as-is or with a minor introductory phrase.

        5.  **Strict JSON Output:** The final output must be a single, perfectly formatted JSON object.

        ---

        **Example of a Perfect Transformation:**

        **[START OF EXAMPLE]**

        **Original User Input:**
        I'm going through some things with my feelings and myself. I barely sleep and I do nothing but think about how I'm worthless and how I shouldn't be here. I've never tried or contemplated suicide. I've always wanted to fix my issues, but I never get around to it. How can I change my feeling of being worthless to everyone?

        **Original Final Model Response:**
        If everyone thinks you're worthless, then maybe you need to find new people to hang out with.Seriously, the social context in which a person lives is a big influence in self-esteem.Otherwise, you can go round and round trying to understand why you're not worthless, then go back to the same crowd and be knocked down again.There are many inspirational messages you can find in social media.  Maybe read some of the ones which state that no person is worthless, and that everyone has a good purpose to their life.Also, since our culture is so saturated with the belief that if someone doesn't feel good about themselves that this is somehow terrible.Bad feelings are part of living.  They are the motivation to remove ourselves from situations and relationships which do us more harm than good.Bad feelings do feel terrible.  Your feeling of worthlessness may be good in the sense of motivating you to find out that you are much better than your feelings today.

        **Generated JSON Output:**
        ```json
        {{
        "tools": [
            {{
            "functionDeclarations": [
                {{
                "name": "recall_past_memories",
                "description": "Searches through past conversations to recall relevant memories based on a query.",
                "parameters": {{
                    "type": "OBJECT",
                    "properties": {{
                    "query": {{
                        "type": "STRING",
                        "description": "A concise summary of the user's current message to search for relevant memories."
                    }}
                    }},
                    "required": ["query"]
                }}
                }}
            ]
            }}
        ],
        "contents": [
            {{
            "role": "user",
            "parts": [{{"text": "I'm going through some things with my feelings and myself. I barely sleep and I do nothing but think about how I'm worthless and how I shouldn't be here. I've never tried or contemplated suicide. I've always wanted to fix my issues, but I never get around to it. How can I change my feeling of being worthless to everyone?"}}]
            }},
            {{
            "role": "model",
            "parts": [
                {{
                "functionCall": {{
                    "name": "recall_past_memories",
                    "args": {{
                    "query": "user feeling worthless, sleep issues, wants to change"
                    }}
                }}
                }}
            ]
            }},
            {{
            "role": "tool",
            "parts": [
                {{
                "functionResponse": {{
                    "name": "recall_past_memories",
                    "response": {{
                    "content": "Retrieved relevant past memories:\\n- User mentioned feeling left out after their friends planned a trip without them."
                    }}
                }}
                }}
            ]
            }},
            {{
            "role": "model",
            "parts": [
                {{"text": "It sounds like you're carrying a very heavy weight right now, and I hear your desire for change. I remember you mentioning how hurt you were when your friends planned a trip without you, and that social context has a huge impact on our self-esteem. Bad feelings are a part of living; they often act as a signal to move away from situations that harm us. This feeling of worthlessness, as painful as it is, might be the motivation to discover just how much more you are than these feelings today."}}
            ]
            }}
        ]
        }}
                
        **[END OF EXAMPLE]**

        ---

        **Now, complete the following task:**

        **Original User Input:**
        
        {user_input}

        **Original Final Model Response:**
        
        {model_response}
        

        **Generated JSON Output:**
        """
    return prompt_template.format(user_input=user_input, model_response=model_response)

def generate_synthetic_finetuning_data(
    input_file_path: str,
    output_file_path: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash-lite",
    rate_limit_delay: int = 2,
):
    """
    Reads a JSONL file, generates synthetic tool-calling data using an LLM,
    and writes it to a new JSONL file.

    Args:
        input_file_path (str): Path to the source JSONL file.
        output_file_path (str): Path to write the generated JSONL data.
        api_key (str): Your Google AI API key.
        model_name (str, optional): The generative model to use. Defaults to "gemini-1.5-pro-latest".
        rate_limit_delay (int, optional): Seconds to wait between API calls. Defaults to 2.
    """
    print(f"Starting dataset generation from '{input_file_path}'...")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    # These safety settings are important for mental health topics
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    try:
        with open(input_file_path, 'r', encoding='utf-8') as infile, \
             open(output_file_path, 'w', encoding='utf-8') as outfile:
            
            for i, line in enumerate(infile):
                try:
                    data = json.loads(line)
                    messages = data.get("messages", [])
                    
                    if len(messages) < 2 or messages[0].get("role") != "user" or messages[1].get("role") != "model":
                        print(f"  [WARN] Skipping line {i+1}: Invalid format.")
                        continue
                        
                    user_input = messages[0].get("content", "")
                    model_response = messages[1].get("content", "")

                    if not user_input or not model_response:
                        print(f"  [WARN] Skipping line {i+1}: Missing content.")
                        continue

                    prompt = build_prompt(user_input, model_response)

                    print(f"  Processing line {i+1}... ", end="", flush=True)
                    response = model.generate_content(prompt, safety_settings=safety_settings)
                    generated_text = ''.join([part.text for part in response.candidates[0].content.parts if part.text]).strip()
                    
                    # Clean markdown code blocks if the model adds them
                    if generated_text.startswith("```json"):
                        generated_text = generated_text[len("```json"):].strip()
                    if generated_text.endswith("```"):
                        generated_text = generated_text[:-3].strip()

                    
                    # Validate that the output is valid JSON before writing
                    json.loads(generated_text)
                    
                    outfile.write(generated_text + '\n')
                    print("Success.")


                except json.JSONDecodeError:
                    print(f"\n  [ERROR] Skipping line {i+1}: LLM output was not valid JSON.")
                except Exception as e:
                    print(f"\n  [ERROR] An unexpected error occurred on line {i+1}: {e}")
                
                time.sleep(rate_limit_delay)

    except FileNotFoundError:
        print(f"[FATAL] Input file not found at '{input_file_path}'")
        return

    print(f"\nGeneration complete. Synthetic dataset saved to '{output_file_path}'.")


if __name__ == '__main__':
    load_dotenv()
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    if not GOOGLE_API_KEY:
        raise ValueError("API key not found. Please set the GOOGLE_API_KEY in your .env file.")

    # DEFINE YOUR FILE PATHS HERE
    source_dataset_path = 'gemini_finetune_data.jsonl'
    synthetic_dataset_path = 'finetuning_dataset_with_tools_complete.jsonl'
    
    # Create a dummy input file if it doesn't exist, for easy testing.
    if not os.path.exists(source_dataset_path):
        print(f"Creating dummy input file: '{source_dataset_path}'")
        dummy_data = {
            "messages": [
                {"role": "user", "content": "I'm feeling really anxious about an upcoming presentation. I can't stop thinking about all the ways it could go wrong."},
                {"role": "model", "content": "It's completely normal to feel anxious before a big presentation. That feeling is just your body's way of telling you that this is important to you. Instead of focusing on what could go wrong, let's try to reframe it. What's one small thing you can prepare that would make you feel even 1% more confident?"}
            ]
        }
        with open(source_dataset_path, 'w') as f:
            f.write(json.dumps(dummy_data) + '\n')

    # Run the main generation function
    generate_synthetic_finetuning_data(
        input_file_path=source_dataset_path,
        output_file_path=synthetic_dataset_path,
        api_key=GOOGLE_API_KEY
    )
