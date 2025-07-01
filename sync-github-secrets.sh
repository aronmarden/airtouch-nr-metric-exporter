#!/bin/bash
# This script reads a .env file and syncs the values to GitHub
# as repository secrets and variables.

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) could not be found. Please install it."
    exit 1
fi

echo "Syncing secrets and variables to the GitHub repository..."

# Loop through the .env file to process secrets and variables line by line
while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip empty lines and comments
  if [[ -z "$line" ]] || [[ "$line" == \#* ]]; then
    continue
  fi

  KEY=$(echo "$line" | cut -d '=' -f 1)
  VALUE=$(echo "$line" | cut -d '=' -f 2-)

  if [[ $KEY == SECRET_*_FILEPATH ]]; then
    FILE_PATH="$VALUE"
    if [[ ! -r "$FILE_PATH" ]]; then
      echo "⚠️  WARNING: File not found, skipping secret: $KEY -> $FILE_PATH"
      continue
    fi
    TEMP_NAME="${KEY%_FILEPATH}"
    SECRET_NAME="${TEMP_NAME#SECRET_}"
    echo "Setting secret: '$SECRET_NAME' from file: $FILE_PATH"
    gh secret set "$SECRET_NAME" < "$FILE_PATH"

  elif [[ $KEY == SECRET_* ]]; then
    SECRET_NAME="${KEY#SECRET_}"
    echo "Setting secret: $SECRET_NAME"
    echo "$VALUE" | gh secret set "$SECRET_NAME" --body -
  
  elif [[ $KEY == VAR_* ]]; then
    VAR_NAME="${KEY#VAR_}"
    echo "Setting variable: $VAR_NAME"
    gh variable set "$VAR_NAME" --body "$VALUE"
  fi
done < .env

echo "Sync complete."