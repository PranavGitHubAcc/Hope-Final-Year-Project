import json
import random

def split_jsonl(input_path, train_path="train.jsonl", val_path="validation.jsonl", val_ratio=0.1, seed=42):
    """
    Splits a JSONL dataset into train and validation sets.

    Args:
        input_path (str): Path to the input JSONL file.
        train_path (str): Output path for the training split.
        val_path (str): Output path for the validation split.
        val_ratio (float): Fraction of data to use for validation (default: 0.1).
        seed (int): Random seed for reproducibility.
    """
    # Load all lines
    with open(input_path, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f if line.strip()]

    # Shuffle data
    random.seed(seed)
    random.shuffle(data)

    # Compute split index
    split_index = int(len(data) * (1 - val_ratio))
    train_data = data[:split_index]
    val_data = data[split_index:]

    # Write to separate files
    with open(train_path, "w", encoding="utf-8") as f_train:
        for item in train_data:
            f_train.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f_val:
        for item in val_data:
            f_val.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"✅ Split complete: {len(train_data)} train rows, {len(val_data)} validation rows.")

split_jsonl("fixed_dataset_complete.jsonl", "train.jsonl", "validation.jsonl", val_ratio=0.2)