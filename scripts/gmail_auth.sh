#!/bin/bash
DESTINATION_PATH="${HOME}/gmail-mcp/gcp-oauth.keys.json"
cp  "auth/gcp-oauth.keys.json" "${DESTINATION_PATH}"
echo "----------> successfully copied gcp-oauth.keys.json to  ${DESTINATION_PATH} <----------"
cat "${DESTINATION_PATH}"
exit 0