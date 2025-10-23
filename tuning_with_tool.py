import json

# === CONFIG ===
input_path = "finetuning_dataset_with_tools_formatted_complete.jsonl"          # <-- your original dataset
output_path = "fixed_dataset_complete.jsonl"   # <-- corrected dataset output

fixed_lines = []
invalid_lines = 0

with open(input_path, "r", encoding="utf-8") as infile:
    for i, line in enumerate(infile, start=1):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)

            # Fix the role name
            if "contents" in obj:
                for content in obj["contents"]:
                    if content.get("role") == "tool":
                        content["role"] = "function"

            fixed_lines.append(json.dumps(obj, ensure_ascii=False))

        except json.JSONDecodeError as e:
            print(f"❌ Line {i}: Invalid JSON — {e}")
            invalid_lines += 1

# Write corrected file
with open(output_path, "w", encoding="utf-8") as outfile:
    outfile.write("\n".join(fixed_lines))

print(f"✅ Fixed dataset saved to: {output_path}")
print(f"📄 Total examples processed: {len(fixed_lines)}")
if invalid_lines:
    print(f"⚠️ {invalid_lines} invalid JSON lines were skipped.")
else:
    print("🎉 All lines valid and fixed.")
