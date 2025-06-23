#!/bin/bash

# --- Configuration ---
# Set the target directory to search within.
SEARCH_DIR="results/run3/jupyter"
# Set the path to the JSON file containing the full list of expected directories.
FULL_LIST_PATH="benchmark/evaluation_examples/test_jupyter.json"
# Set the path for the output JSON file.
OUTPUT_LIST_PATH="benchmark/evaluation_examples/recovery.json"

# --- Script Logic ---

# Dependency Check: This script requires 'jq' to parse JSON.
if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' is not installed. Please install it to run this script." >&2
    exit 1
fi

# Check if the search directory exists.
if [ ! -d "$SEARCH_DIR" ]; then
  echo "Error: Search directory '$SEARCH_DIR' not found." >&2
  exit 1
fi

# Check if the input JSON file exists.
if [ ! -f "$FULL_LIST_PATH" ]; then
  echo "Error: Full list file '$FULL_LIST_PATH' not found." >&2
  exit 1
fi

# Initialize an empty array to store the names of missing directories.
missing_dirs=()

# Read the JSON file content.
FULL_LIST_JSON=$(cat "$FULL_LIST_PATH")

# Use 'jq' to parse the JSON and read the directory names into a Bash array.
# The `readarray -t` command reads lines into an array.
readarray -t expected_dirs < <(echo "$FULL_LIST_JSON" | jq -r '.jupyter[]')

# Loop through each directory name from the JSON list.
for dir_name in "${expected_dirs[@]}"; do
  # Check if a directory with this name does NOT exist in the SEARCH_DIR.
  if [ ! -d "${SEARCH_DIR}/${dir_name}" ]; then
    # If the directory is missing, add its name to our array.
    missing_dirs+=("$dir_name")
  fi
done

# --- Output Results ---

# Ensure the output directory exists before trying to write the file.
mkdir -p "$(dirname "$OUTPUT_LIST_PATH")"

# Use jq to robustly create the final JSON output object.
# 1. Print each element of the bash array on a new line.
# 2. Pipe to `jq -R .` to read raw strings into jq as individual JSON strings.
# 3. Pipe to `jq -s .` to slurp all JSON strings into a single JSON array.
# 4. Pipe the resulting array into a final jq command that wraps it in the desired object.
printf "%s\n" "${missing_dirs[@]}" | jq -R . | jq -s . | jq '{"jupyter": .}' > "$OUTPUT_LIST_PATH"


# Provide feedback to the user.
if [ ${#missing_dirs[@]} -eq 0 ]; then
  echo "Success: All directories found. Empty list written to '$OUTPUT_LIST_PATH'."
else
  echo "Found ${#missing_dirs[@]} missing directories. List saved to '$OUTPUT_LIST_PATH'."
fi
