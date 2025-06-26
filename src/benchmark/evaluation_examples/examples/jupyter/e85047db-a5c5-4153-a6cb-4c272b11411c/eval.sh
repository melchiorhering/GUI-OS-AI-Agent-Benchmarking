#!/bin/bash
# eval.sh

# ─── Log File Path ────────────────────────────────────────────────────────────
LOG_FILE="/home/user/eval.log"

# Clear the log file at the start of each run
echo "" > "$LOG_FILE"

# Redirect all subsequent stdout and stderr to the log file.
# 'exec' replaces the current shell process with one that has redirected output.
exec > >(tee -a "$LOG_FILE") 2>&1

echo "──────────────────────────────────────────────────"
echo "🚀 Eval Script Started"
echo "→ Log File: $LOG_FILE"
echo "──────────────────────────────────────────────────"

# This script validates that a Jupyter server is running on the correct port
# AND that it is configured to serve the correct notebook.

URL_TO_CHECK="http://localhost:1036/notebooks/Aragon_Conviction_Voting_Model.ipynb"

# Ensure NOTEBOOK_FILENAME is set. It's not in the original snippet,
# but referenced later. For this example, let's assume a default or expect it to be set externally.
: "${NOTEBOOK_FILENAME:=Aragon_Conviction_Voting_Model.ipynb}"

echo "Checking URL: $URL_TO_CHECK"
echo "Expected Notebook: $NOTEBOOK_FILENAME"


# Use curl to fetch headers (-i) and check the response.
# -s: Silent mode.
# -L: Follow one redirect to get the final URL if needed (optional but good practice).
# --max-time 10: Set a timeout.
# --connect-timeout 5: Fail faster if nothing is listening.
# The output will contain the full HTTP response headers.
RESPONSE_HEADERS=$(curl -s -i --max-time 10 --connect-timeout 5 "$URL_TO_CHECK")

echo "Received HTTP Headers:"
echo "$RESPONSE_HEADERS"

# First, check if we got a 302 redirect, which is the primary signal.
# We use grep to check the first line of the headers for "302 Found".
# The `<<<` syntax is a "here string", feeding the variable to grep's stdin.
if ! grep -q "HTTP/1.1 302 Found" <<< "$RESPONSE_HEADERS"; then
    echo "FAILURE: Did not receive an HTTP 302 redirect from $URL_TO_CHECK."
    exit 1
fi

# Second, check if the redirect location contains the correct notebook filename.
# The `Location:` header contains the URL to redirect to.
if grep -q "Location: .*$NOTEBOOK_FILENAME" <<< "$RESPONSE_HEADERS"; then
    echo "SUCCESS: Server is running on port 1036 and serving the correct notebook ($NOTEBOOK_FILENAME)."
    exit 0
else
    echo "FAILURE: Server is running, but it is not serving the correct notebook. Redirect location did not contain '$NOTEBOOK_FILENAME'."
    # For debugging, you can print the headers that were found:
    # echo "DEBUG: Headers received:" # Already echoing above, so commented out for brevity.
    # echo "$RESPONSE_HEADERS"
    exit 1
fi
