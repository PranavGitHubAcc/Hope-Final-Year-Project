import json
import random
from collections import defaultdict

# --- Step 1: Convert from original {"Context": "...", "Response": "..."} to the correct Gemini Fine-tune format ---
def convert_to_gemini_finetune_correct_format(input_jsonl_path, output_jsonl_path, system_instruction_text):
    """
    Converts a JSONL file from {"Context": "...", "Response": "..."}
    format to the CORRECT Vertex AI Gemini supervised fine-tuning format (using "contents" and "parts"),
    and includes a system instruction in each example.

    Args:
        input_jsonl_path (str): Path to your original JSONL file.
        output_jsonl_path (str): Path where the converted JSONL file will be saved.
        system_instruction_text (str): The system instruction to add to each example.
    """
    if not system_instruction_text:
        raise ValueError("system_instruction_text cannot be None or empty for this function.")

    converted_data = []
    with open(input_jsonl_path, 'r', encoding='utf-8') as infile:
        for line_num, line in enumerate(infile, 1):
            try:
                original_example = json.loads(line)
                context = original_example.get("Context")
                response = original_example.get("Response")

                if context is None or response is None:
                    print(f"Warning: Skipping line {line_num} due to missing 'Context' or 'Response' field: {line.strip()}")
                    continue

                new_example = {
                    "systemInstruction": {
                        "role": "system",
                        "parts": [{"text": system_instruction_text}]
                    },
                    "contents": [
                        {"role": "user", "parts": [{"text": context}]},
                        {"role": "model", "parts": [{"text": response}]}
                    ]
                }
                
                converted_data.append(new_example)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON on line {line_num}: {line.strip()} - {e}")
            except Exception as e:
                print(f"An unexpected error occurred on line {line_num}: {line.strip()} - {e}")

    with open(output_jsonl_path, 'w', encoding='utf-8') as outfile:
        for entry in converted_data:
            outfile.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"Conversion complete! Converted {len(converted_data)} examples to the correct Gemini format with system instruction.")
    print(f"Output saved to: {output_jsonl_path}")

# --- Step 2: Split the data into train/validation sets (with the correct format) ---
def split_finetune_data(input_jsonl_path, train_output_path, validation_output_path, split_ratio=0.8):
    """
    Splits a Gemini fine-tuning JSONL dataset (in the correct "contents" format)
    into training and validation sets. Ensures no data leakage by splitting unique user messages.

    Args:
        input_jsonl_path (str): Path to the input JSONL file in Gemini fine-tune format.
        train_output_path (str): Path where the training JSONL file will be saved.
        validation_output_path (str): Path where the validation JSONL file will be saved.
        split_ratio (float): The proportion of unique contexts to allocate to the training set.
    """
    if not (0 < split_ratio < 1):
        raise ValueError("split_ratio must be between 0 and 1 (exclusive).")

    grouped_data = defaultdict(list)
    unique_contexts = set()
    total_examples = 0

    with open(input_jsonl_path, 'r', encoding='utf-8') as infile:
        for line_num, line in enumerate(infile, 1):
            try:
                example = json.loads(line)
                
                # Extract user message from the 'contents' field
                user_message_content = None
                if "contents" in example and isinstance(example["contents"], list):
                    for turn in example["contents"]:
                        if turn.get("role") == "user" and "parts" in turn and isinstance(turn["parts"], list):
                            for part in turn["parts"]:
                                if "text" in part:
                                    user_message_content = part["text"]
                                    break # Found the user text for this turn
                        if user_message_content:
                            break # Found the first user message, break outer loop

                if not user_message_content:
                    print(f"Warning: Skipping line {line_num} due to missing or malformed user message in 'contents': {line.strip()}")
                    continue

                grouped_data[user_message_content].append(example)
                unique_contexts.add(user_message_content)
                total_examples += 1

            except json.JSONDecodeError as e:
                print(f"Error decoding JSON on line {line_num}: {line.strip()} - {e}")
            except Exception as e:
                print(f"An unexpected error occurred on line {line_num}: {line.strip()} - {e}")

    print(f"Read {total_examples} examples, with {len(unique_contexts)} unique user contexts.")

    if not unique_contexts:
        print("No valid data found to split. Exiting.")
        return

    shuffled_contexts = list(unique_contexts)
    random.shuffle(shuffled_contexts)

    split_idx = int(len(shuffled_contexts) * split_ratio)
    train_contexts = set(shuffled_contexts[:split_idx])
    validation_contexts = set(shuffled_contexts[split_idx:])

    train_data = []
    validation_data = []

    for context, examples in grouped_data.items():
        if context in train_contexts:
            train_data.extend(examples)
        elif context in validation_contexts:
            validation_data.extend(examples)

    with open(train_output_path, 'w', encoding='utf-8') as outfile:
        for entry in train_data:
            outfile.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print(f"Training data saved to: {train_output_path} ({len(train_data)} examples)")

    with open(validation_output_path, 'w', encoding='utf-8') as outfile:
        for entry in validation_data:
            outfile.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print(f"Validation data saved to: {validation_output_path} ({len(validation_data)} examples)")

# --- Step 3: Create a smaller training set (randomly picked 100 examples) ---
def create_random_small_training_set(input_train_jsonl_path, output_small_train_jsonl_path, num_examples=100):
    """
    Creates a smaller training dataset by randomly picking 'num_examples'
    from an existing train.jsonl file.
    """
    all_lines = []
    with open(input_train_jsonl_path, 'r', encoding='utf-8') as infile:
        all_lines = infile.readlines()

    if len(all_lines) < num_examples:
        print(f"Warning: Requested {num_examples} examples, but only {len(all_lines)} are available.")
        num_examples = len(all_lines)
    
    random.shuffle(all_lines) # Shuffle all available lines
    selected_lines = all_lines[:num_examples] # Pick the first `num_examples` from the shuffled list

    with open(output_small_train_jsonl_path, 'w', encoding='utf-8') as outfile:
        for line in selected_lines:
            outfile.write(line)

    print(f"Created a small training dataset with {len(selected_lines)} randomly picked examples.")
    print(f"Output saved to: {output_small_train_jsonl_path}")


# --- Main execution block ---
if __name__ == "__main__":
    original_input_file = "combined_dataset.jsonl"  # Your original file
    converted_full_file = "gemini_finetune_data_correct_format.jsonl" # Intermediate file in correct format

    # Define your system instruction here
    default_system_instruction = (
        "You are a compassionate and supportive AI assistant specializing in mental well-being. "
        "Your goal is to provide empathetic, non-judgmental, and helpful responses based on "
        "therapeutic principles. Always encourage users to seek professional help when appropriate "
        "and avoid giving definitive medical or diagnostic advice."
    )

    print("--- Step 1: Converting original data to correct Gemini fine-tune format with System Instruction ---")
    convert_to_gemini_finetune_correct_format(original_input_file, converted_full_file, default_system_instruction)

    print("\n--- Step 2: Splitting converted data into train and validation sets ---")
    train_file = "train_correct_format.jsonl"
    validation_file = "validation_correct_format.jsonl"
    split_ratio = 0.8
    split_finetune_data(converted_full_file, train_file, validation_file, split_ratio)

    print("\n--- Step 3: Creating a 100-example training subset (randomly picked) ---")
    small_train_file = "train_100_examples_random_correct_format.jsonl" # Changed filename to reflect random selection
    create_random_small_training_set(train_file, small_train_file, num_examples=100)

    print("\nAll data preparation complete!")
    print(f"Use '{small_train_file}' for your initial training data (100 examples).")
    print(f"Use '{validation_file}' for your validation data (726 examples).")
    print("Remember to upload these files to a Cloud Storage bucket for Vertex AI.")