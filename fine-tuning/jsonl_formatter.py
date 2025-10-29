import json 
input_file = "finetuning_dataset_with_tools_complete.jsonl"
output_file = "finetuning_dataset_with_tools_formatted_complete.jsonl"

with open(input_file, "r", encoding="utf-8") as infile, open(output_file, "w", encoding="utf-8") as outfile:
    buffer = ""
    for line in infile:
        buffer += line.strip()
        # detect end of a JSON object (naively assuming each object ends with '}')
        if line.strip().endswith("}"):
            try:
                obj = json.loads(buffer)
                outfile.write(json.dumps(obj, ensure_ascii=False) + "\n")
                buffer = ""
            except json.JSONDecodeError:
                # keep buffering if not yet a full JSON
                buffer += " "
