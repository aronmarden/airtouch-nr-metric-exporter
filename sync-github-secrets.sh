#!/bin/bash
#
#  DEBUGGING VERSION
#  This script will print detailed information about its execution.
#
set -e # Exit on any error

while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip empty lines and comments
  if [[ -z "$line" ]] || [[ "$line" == \#* ]]; then
    continue
  fi

  # This removes invisible carriage return characters (\r)
  line=${line%$'\r'}

  KEY=$(echo "$line" | cut -d '=' -f 1)
  VALUE=$(echo "$line" | cut -d '=' -f 2-)

  if [[ $KEY == SECRET_*_FILEPATH ]]; then
    # ... (filepath logic remains the same) ...
    FILE_PATH="$VALUE"
    if [[ ! -r "$FILE_PATH" ]]; then
      echo "⚠️  WARNING: File not found, skipping secret: $KEY -> $FILE_PATH"
      continue
    fi
    TEMP_NAME="${KEY%_FILEPATH}"
    SECRET_NAME="${TEMP_NAME#SECRET_}"
    echo "Setting secret: '$SECRET_NAME' from file: $FILE_PATH"
    gh secret set "$SECRET_NAME" < "$FILE_PATH"

  elif [[ $KEY == SECRET_* ]] && [[ $KEY != *_FILEPATH ]]; then
    SECRET_NAME="${KEY#SECRET_}"
    
    # --- Start Debug Block ---
    echo ""
    echo "==================== DEBUG START ===================="
    echo "Attempting to set secret: '$SECRET_NAME'"
    echo "Value to be set:          '$VALUE'"
    echo "Running command:          echo \"\$VALUE\" | gh secret set \"$SECRET_NAME\" --body -"
    # --- End Debug Block ---

    gh secret set "$SECRET_NAME" --body "$VALUE"
    GH_EXIT_CODE=$?

    # --- Start Exit Code Check ---
    echo "gh secret set command finished with exit code: $GH_EXIT_CODE"
    if [ $GH_EXIT_CODE -ne 0 ]; then
        echo "!!!!!!!!!!!!!!!!!!!! ERROR !!!!!!!!!!!!!!!!!!!!"
        echo "gh secret set FAILED. The secret was NOT updated."
        echo "Check your authentication with 'gh auth status' and ensure you have 'repo' scope."
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        exit 1
    else
        echo "✅ Successfully set secret: $SECRET_NAME"
    fi
    echo "==================== DEBUG END ===================="
    echo ""
  
  elif [[ $KEY == VAR_* ]]; then
    # ... (variable logic remains the same) ...
    VAR_NAME="${KEY#VAR_}"
    echo "Setting variable: $VAR_NAME"
    gh variable set "$VAR_NAME" --body "$VALUE"
  fi
done < .env