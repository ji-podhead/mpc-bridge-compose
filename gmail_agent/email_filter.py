import asyncio
import os
import json
import base64
import logging
from dotenv import load_dotenv
from google import genai
from google.api_core import exceptions as google_exceptions
from google.generativeai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.http import HttpServerParameters, http_client # Import für HTTP
# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

# Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MCP_SERVER_BASE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

async def categorize_email(email_body, history: list = None):
    """Categorizes email content using Gemini API."""
    logging.info(f"Categorizing email starting with: '{email_body[:100]}...'")
    gen_client = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    
    current_history = list(history or [])
    user_prompt_part = {"role": "user", "parts": [{"text": f"Categorize the following email: {email_body}"}]}
    contents_payload = current_history + [user_prompt_part]
    logging.info(f"Contents payload for Gemini: {json.dumps(contents_payload, indent=2)}")

    # MCP Client Setup
    if MCP_SERVER_BASE_URL and MCP_SERVER_BASE_URL.startswith("http"):
        logging.info(f"Using HTTP MCP client for: {MCP_SERVER_BASE_URL}")
        server_params_transport = HttpServerParameters(base_url=MCP_SERVER_BASE_URL)
        mcp_client_context = http_client(server_params_transport)
    else:
        logging.info("Using Stdio MCP client.")
        server_params_stdio = StdioServerParameters(
            command=os.getenv("MCP_STDIO_COMMAND", "mcp-flight-search"),
            args=["--connection_type", "stdio"],
            env={"SERP_API_KEY": os.getenv("SERP_API_KEY")},
        )
        mcp_client_context = stdio_client(server_params_stdio)

    try:
        async with mcp_client_context as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logging.info("MCP Session initialized for categorization.")

                mcp_tools_response = await session.list_tools()
                logging.info(f"Available MCP tools for categorization: {[tool.name for tool in mcp_tools_response.tools]}")
            tools = [
                types.Tool(
                    function_declarations=[
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": {
                                k: v
                                for k, v in tool.inputSchema.items()
                                if k not in ["additionalProperties", "$schema"]
                            },
                        }
                    ]
                )
                for tool in mcp_tools.tools
            ]

                tools_for_gemini = [
                    types.Tool(
                        function_declarations=[
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": {
                                    k: v
                                    for k, v in tool.inputSchema.items()
                                    if k not in ["additionalProperties", "$schema"]
                                },
                            }
                        ]
                    )
                    for tool in mcp_tools_response.tools
                ]

                try:
                    response = gen_client.generate_content(
                        contents=contents_payload,
                        generation_config=genai.types.GenerationConfig(temperature=0),
                        tools=tools_for_gemini,
                    )
                    logging.info(f"Raw Gemini response: {response}")
                except (google_exceptions.GoogleAPIError, Exception) as e:
                    logging.exception("Error calling Gemini API (generate_content)")
                    # Ensure history includes the user prompt even on error
                    updated_history = current_history + [user_prompt_part, {"role": "model", "parts": [{"text": "Error calling Gemini."}]}]
                    return "unknown_category_error_gemini_api", updated_history

                model_response_part = response.candidates[0].content.parts[0]
                updated_history = current_history + [user_prompt_part, {"role": "model", "parts": [model_response_part]}]

                if model_response_part.function_call:
                    function_call = model_response_part.function_call
                    logging.info(f"Model generated function call: {function_call.name} with args: {dict(function_call.args)}")
                    try:
                        tool_result = await session.call_tool(
                            function_call.name, arguments=dict(function_call.args)
                        )
                        logging.info(f"Result from MCP tool '{function_call.name}': {tool_result.content}")
                        try:
                            category_data = json.loads(tool_result.content[0].text)
                            return category_data, updated_history
                        except json.JSONDecodeError as e:
                            logging.exception(f"MCP tool '{function_call.name}' returned non-JSON response: {tool_result.content[0].text}")
                            return "error_mcp_json_decode", updated_history
                        except (IndexError, AttributeError) as e:
                            logging.exception(f"Unexpected result structure from MCP tool '{function_call.name}': {tool_result}")
                            return "error_mcp_result_structure", updated_history
                    except Exception as e:
                        logging.exception(f"Error calling MCP tool '{function_call.name}'")
                        return f"error_calling_mcp_tool_{function_call.name}", updated_history
                elif response.text:
                    logging.info(f"Model returned direct text response: {response.text}")
                    return response.text, updated_history
                else:
                    logging.warning("No function call or direct text response from model.")
                    return "unknown_no_function_call_or_text", updated_history
    except Exception as e:
        logging.exception("Error in MCP client session for categorization")
        # Ensure history includes the user prompt even on this error
        updated_history = current_history + [user_prompt_part, {"role": "model", "parts": [{"text": "Error in MCP session."}]}]
        return "error_mcp_session_categorization", updated_history


async def filter_emails():
    """Fetches and filters emails by simulating a call to a Gmail MCP tool."""
    logging.info("Attempting to fetch and filter emails via MCP...")
    fetched_data = [] # Return type in case of success

    if MCP_SERVER_BASE_URL and MCP_SERVER_BASE_URL.startswith("http"):
        logging.info(f"Using HTTP MCP client for email filtering: {MCP_SERVER_BASE_URL}")
        server_params_transport = HttpServerParameters(base_url=MCP_SERVER_BASE_URL)
        mcp_client_context = http_client(server_params_transport)
    else:
        logging.info("Using Stdio MCP client for email filtering.")
        server_params_stdio = StdioServerParameters(
            command=os.getenv("MCP_STDIO_GMAIL_COMMAND", "mcp-gmail-tool"),
            args=["--connection_type", "stdio"],
        )
        mcp_client_context = stdio_client(server_params_stdio)

    try:
        async with mcp_client_context as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logging.info("MCP session initialized for email filtering.")

                available_tools_response = await session.list_tools()
                tool_names = [tool.name for tool in available_tools_response.tools]
                logging.info(f"Available MCP tools for filtering: {tool_names}")

                gmail_tool_name = "gmail_fetch_emails"
                if gmail_tool_name in tool_names:
                    dummy_args = {"query": "unread", "max_results": 10}
                    logging.info(f"Attempting to call tool: '{gmail_tool_name}' with args: {dummy_args}")
                    try:
                        result = await session.call_tool(gmail_tool_name, arguments=dummy_args)
                        logging.info(f"Raw result from '{gmail_tool_name}': {result}")
                        if result.content:
                            for part in result.content:
                                if part.text:
                                    logging.info(f"Tool '{gmail_tool_name}' response text: {part.text}")
                                    # Simulate adding to fetched_data, actual structure depends on tool output
                                    try:
                                        fetched_data.append(json.loads(part.text)) 
                                    except json.JSONDecodeError:
                                        fetched_data.append({"raw_text": part.text, "error": "not_json"})
                                elif part.tool_code: # Unlikely for this use case
                                     logging.info(f"Tool '{gmail_tool_name}' response tool_code: {part.tool_code}")
                                     fetched_data.append({"tool_code": part.tool_code})
                                else:
                                    logging.info(f"Tool '{gmail_tool_name}' response part: {part}")
                                    fetched_data.append({"unknown_part": str(part)})
                        else:
                            logging.warning(f"Tool '{gmail_tool_name}' call returned no content.")
                        return fetched_data # Return data even if empty from tool
                    except Exception as e:
                        logging.exception(f"Error calling MCP tool '{gmail_tool_name}'")
                        return [{"error": f"Failed to call {gmail_tool_name}"}] 
                else:
                    logging.warning(f"Tool '{gmail_tool_name}' not found among available MCP tools.")
                    return [{"error": f"Tool {gmail_tool_name} not found"}]
    except Exception as e:
        logging.exception("Error during MCP client operation for email filtering")
        return [{"error": "MCP client session failed for filtering"}]
    logging.info("Email filtering process finished.")
    return fetched_data # Should return data gathered or error indicators


async def main():
    """Main function to execute email filtering and categorization."""
    logging.info("Application started.")
    
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY not found. Please set it in your .env file. Categorization will fail.")
    # Configure genai early if key is present, otherwise categorize_email will handle missing key for its call
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            logging.info("Google GenAI configured successfully.")
        except Exception as e:
            logging.exception("Error configuring Google GenAI.")


    filter_results = await filter_emails()
    logging.info(f"Filter_emails function call result: {filter_results}")

    chat_history = []
    logging.info("Starting interactive email categorization agent. Type 'quit' or 'exit' to stop.")

    while True:
        try:
            email_body = input("Enter email body or command: ")
            logging.info(f"User input: '{email_body}'")
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt detected. Exiting...")
            break

        if email_body.lower() in ["quit", "exit"]:
            logging.info("Exit command received. Exiting...")
            break

        if not email_body.strip():
            logging.warning("Empty input received.")
            print("Please enter some text.")
            continue
        
        if not GEMINI_API_KEY:
            logging.error("Cannot categorize email: GEMINI_API_KEY is not set.")
            print("Error: GEMINI_API_KEY is not configured. Cannot categorize.")
            # Optionally, break here or prevent further attempts if key is missing
            continue 
        
        # Ensure genai is configured before each call, as it might clear config or if there are issues
        try:
            genai.configure(api_key=GEMINI_API_KEY)
        except Exception as e:
            logging.exception("Error re-configuring Google GenAI in loop.")
            print("Error configuring GenAI. Cannot categorize.")
            continue

        try:
            category, updated_history = await categorize_email(email_body, chat_history)
            chat_history = updated_history
            logging.info(f"Email categorized as: {category}")
            print(f"Categorized as: {category}")
        except Exception as e:
            logging.exception("Unhandled error during categorize_email call in main loop.")
            # Decide if to continue or break; for robustness, let's try to continue
            print(f"An unexpected error occurred: {e}. Please try again.")
            # Optionally, reset chat_history or part of it if the error corrupted it
            # chat_history.append({"role": "user", "parts": [{"text": email_body}]}) # Keep user part
            # chat_history.append({"role": "model", "parts": [{"text": f"Error during processing: {e}"}]}) # Add error to history


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logging.exception("Unhandled exception in asyncio.run(main()).")
    finally:
        logging.info("Application finished.")
