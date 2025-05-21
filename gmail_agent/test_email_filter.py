import asyncio
import json
import logging
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

# Attempt to import from sibling directory 'gmail_agent'
try:
    from gmail_agent import email_filter
    from mcp import ClientSession # Import ClientSession for type checking if needed
    from mcp.client.http import HttpServerParameters
    from google.api_core import exceptions as google_exceptions
except ImportError:
    # Fallback for simpler test execution environments if needed
    # This assumes email_filter.py is in the same directory or PYTHONPATH is set
    import email_filter
    from mcp import ClientSession
    from mcp.client.http import HttpServerParameters
    from google.api_core import exceptions as google_exceptions


# Suppress logging during tests to keep output clean
logging.disable(logging.CRITICAL)

# Mocked environment variables
MOCKED_ENV_VARS_STDIO = {
    "GEMINI_API_KEY": "test_gemini_api_key_stdio",
    "MCP_SERVER_URL": "", # Default to stdio
    "MCP_STDIO_COMMAND": "test_mcp_command_stdio",
    "SERP_API_KEY": "test_serp_api_key_stdio",
    "MCP_STDIO_GMAIL_COMMAND": "test_gmail_stdio_cmd_filter"
}

MOCKED_ENV_VARS_HTTP = {
    "GEMINI_API_KEY": "test_gemini_api_key_http",
    "MCP_SERVER_URL": "http://localhost:8080/test_mcp_http",
    "MCP_STDIO_COMMAND": "test_mcp_command_http_fallback", # For categorize if http fails
    "MCP_STDIO_GMAIL_COMMAND": "test_gmail_stdio_cmd_http_fallback" # For filter_emails if http fails
}


class TestCategorizeEmail(unittest.IsolatedAsyncioTestCase): # Using IsolatedAsyncioTestCase for better async test isolation

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.http_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_successful_categorization_function_call_stdio(self, mock_generative_model, mock_http_client, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock()
        mock_gemini_response.candidates = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts[0].function_call = MagicMock(
            name="test_tool_stdio", args={"param": "val_stdio"}
        )
        mock_gemini_response.text = None
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_tool_result_content = MagicMock()
        mock_tool_result_content.text = json.dumps({"category": "promotions_stdio"})
        mock_mcp_session.call_tool = AsyncMock(return_value=MagicMock(content=[mock_tool_result_content]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session) as mock_cs_constructor:
            category, history = await email_filter.categorize_email("Test email body stdio")

        self.assertEqual(category, {"category": "promotions_stdio"})
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "model")
        self.assertIsNotNone(history[1]["parts"][0].function_call)
        
        mock_stdio_client.assert_called_once_with(
            email_filter.StdioServerParameters(
                command=MOCKED_ENV_VARS_STDIO["MCP_STDIO_COMMAND"],
                args=["--connection_type", "stdio"],
                env={"SERP_API_KEY": MOCKED_ENV_VARS_STDIO["SERP_API_KEY"]},
            )
        )
        mock_http_client.assert_not_called()
        mock_gemini_instance.generate_content.assert_called_once()
        mock_cs_constructor.assert_called_once_with(mock_stdio_read, mock_stdio_write)

    @patch.dict(os.environ, MOCKED_ENV_VARS_HTTP, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.http_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_successful_categorization_function_call_http(self, mock_generative_model, mock_http_client, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock()
        mock_gemini_response.candidates = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts[0].function_call = MagicMock(
            name="test_tool_http", args={"param": "val_http"}
        )
        mock_gemini_response.text = None
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_http_read, mock_http_write = AsyncMock(), AsyncMock()
        mock_http_client.return_value.__aenter__.return_value = (mock_http_read, mock_http_write)
        
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_tool_result_content = MagicMock()
        mock_tool_result_content.text = json.dumps({"category": "social_http"})
        mock_mcp_session.call_tool = AsyncMock(return_value=MagicMock(content=[mock_tool_result_content]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session) as mock_cs_constructor:
            category, history = await email_filter.categorize_email("Test email body http")

        self.assertEqual(category, {"category": "social_http"})
        self.assertEqual(len(history), 2)
        
        mock_http_client.assert_called_once_with(
            HttpServerParameters(base_url=MOCKED_ENV_VARS_HTTP["MCP_SERVER_URL"])
        )
        mock_stdio_client.assert_not_called()
        mock_cs_constructor.assert_called_once_with(mock_http_read, mock_http_write)


    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_model_returns_direct_text(self, mock_generative_model, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock()
        mock_gemini_response.candidates = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts = [MagicMock(text="direct_category")]
        mock_gemini_response.candidates[0].content.parts[0].function_call = None
        mock_gemini_response.text = "direct_category"
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            category, history = await email_filter.categorize_email("Direct text email")

        self.assertEqual(category, "direct_category")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]["parts"][0].text, "direct_category")
        mock_mcp_session.call_tool.assert_not_called()

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_gemini_api_error(self, mock_generative_model, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_instance.generate_content = AsyncMock(side_effect=google_exceptions.InternalServerError("Gemini boom"))

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        
        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            category, history = await email_filter.categorize_email("Email causing Gemini error")

        self.assertEqual(category, "unknown_category_error_gemini_api")
        self.assertEqual(len(history), 2)
        self.assertIn("Error calling Gemini", history[1]["parts"][0]["text"])

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_mcp_tool_call_non_json_response(self, mock_generative_model, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock()
        mock_gemini_response.candidates = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts[0].function_call = MagicMock(name="test_tool", args={})
        mock_gemini_response.text = None
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_tool_result_content = MagicMock()
        mock_tool_result_content.text = "This is not JSON"
        mock_mcp_session.call_tool = AsyncMock(return_value=MagicMock(content=[mock_tool_result_content]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            category, history = await email_filter.categorize_email("Email with non-JSON tool response")

        self.assertEqual(category, "error_mcp_json_decode")
        self.assertEqual(len(history), 2)

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_mcp_tool_call_error(self, mock_generative_model, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock() # Setup for function call
        mock_gemini_response.candidates = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts[0].function_call = MagicMock(name="failing_tool", args={})
        mock_gemini_response.text = None
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_mcp_session.call_tool = AsyncMock(side_effect=Exception("MCP tool exploded"))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            category, history = await email_filter.categorize_email("Email with failing MCP tool")
        self.assertEqual(category, "error_calling_mcp_tool_failing_tool")

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_context_history_usage(self, mock_generative_model, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock()
        mock_gemini_response.candidates = [MagicMock()]
        mock_gemini_response.candidates[0].content.parts = [MagicMock(text="response to history")]
        mock_gemini_response.candidates[0].content.parts[0].function_call = None
        mock_gemini_response.text = "response to history"
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))

        initial_history = [
            {"role": "user", "parts": [{"text": "Hello model"}]},
            {"role": "model", "parts": [{"text": "Hello user"}]}
        ]
        
        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            category, new_history = await email_filter.categorize_email("Another email", history=initial_history)

        self.assertEqual(category, "response to history")
        self.assertEqual(len(new_history), 4)
        args, kwargs = mock_gemini_instance.generate_content.call_args
        passed_contents = kwargs['contents']
        self.assertEqual(passed_contents[0], initial_history[0])
        self.assertEqual(passed_contents[1], initial_history[1])
        self.assertTrue(passed_contents[2]["parts"][0]["text"].endswith("Another email"))

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client') # stdio_client fails
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_mcp_session_error_categorize(self, mock_generative_model, mock_stdio_client):
        mock_stdio_client.return_value.__aenter__.side_effect = Exception("Stdio client failed to start")
        
        # Gemini mock not strictly needed as MCP client fails before Gemini call
        mock_gemini_instance = mock_generative_model.return_value 
        mock_gemini_instance.generate_content = AsyncMock()

        category, history = await email_filter.categorize_email("Email with MCP session error")
        self.assertEqual(category, "error_mcp_session_categorization")
        self.assertEqual(len(history), 2) # User prompt, and model part with error message
        self.assertIn("Error in MCP session", history[1]["parts"][0]["text"])

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.genai.GenerativeModel')
    async def test_no_function_call_or_text(self, mock_generative_model, mock_stdio_client):
        mock_gemini_instance = mock_generative_model.return_value
        mock_gemini_response = MagicMock()
        mock_gemini_response.candidates = [MagicMock()]
        # Simulate a part that is neither function_call nor has text
        part_without_call_or_text = MagicMock()
        part_without_call_or_text.function_call = None
        # To fully simulate, ensure the 'text' attribute doesn't exist or is None on the Part itself
        # if the library relies on Part.text directly instead of Response.text
        # For this mock, if part.text is not set, it's None by default.
        # And Response.text is also None.
        mock_gemini_response.candidates[0].content.parts = [part_without_call_or_text]
        mock_gemini_response.text = None # Crucial: no overall text response either
        mock_gemini_instance.generate_content = AsyncMock(return_value=mock_gemini_response)

        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            category, history = await email_filter.categorize_email("Email with no useful response")

        self.assertEqual(category, "unknown_no_function_call_or_text")
        self.assertEqual(len(history), 2)
        # The model part in history will be the raw part received
        self.assertEqual(history[1]["parts"][0], part_without_call_or_text)


class TestFilterEmails(unittest.IsolatedAsyncioTestCase):

    @patch.dict(os.environ, MOCKED_ENV_VARS_HTTP, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.http_client')
    async def test_successful_gmail_fetch_http(self, mock_http_client, mock_stdio_client):
        mock_http_read, mock_http_write = AsyncMock(), AsyncMock()
        mock_http_client.return_value.__aenter__.return_value = (mock_http_read, mock_http_write)

        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_tool_list = MagicMock(tools=[MagicMock(name="gmail_fetch_emails")])
        mock_mcp_session.list_tools = AsyncMock(return_value=mock_tool_list)
        mock_email_data = [{"id": "email_http", "snippet": "Hello http"}]
        mock_tool_result_content = MagicMock(text=json.dumps(mock_email_data))
        mock_mcp_session.call_tool = AsyncMock(return_value=MagicMock(content=[mock_tool_result_content]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            results = await email_filter.filter_emails()

        self.assertEqual(results, mock_email_data)
        mock_http_client.assert_called_once_with(
            HttpServerParameters(base_url=MOCKED_ENV_VARS_HTTP["MCP_SERVER_URL"])
        )
        mock_stdio_client.assert_not_called()
        mock_mcp_session.call_tool.assert_called_once_with("gmail_fetch_emails", arguments={"query": "unread", "max_results": 10})

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    @patch('gmail_agent.email_filter.http_client')
    async def test_successful_gmail_fetch_stdio(self, mock_http_client, mock_stdio_client):
        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)

        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_tool_list = MagicMock(tools=[MagicMock(name="gmail_fetch_emails")])
        mock_mcp_session.list_tools = AsyncMock(return_value=mock_tool_list)
        mock_email_data = [{"id": "email_stdio", "snippet": "Hello stdio"}]
        mock_tool_result_content = MagicMock(text=json.dumps(mock_email_data))
        mock_mcp_session.call_tool = AsyncMock(return_value=MagicMock(content=[mock_tool_result_content]))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            results = await email_filter.filter_emails()

        self.assertEqual(results, mock_email_data)
        mock_stdio_client.assert_called_once_with(
            email_filter.StdioServerParameters(
                command=MOCKED_ENV_VARS_STDIO["MCP_STDIO_GMAIL_COMMAND"],
                args=["--connection_type", "stdio"],
            )
        )
        mock_http_client.assert_not_called()

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    async def test_gmail_tool_not_found(self, mock_stdio_client):
        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_mcp_session.list_tools = AsyncMock(return_value=MagicMock(tools=[])) # No tools

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            results = await email_filter.filter_emails()
        
        self.assertEqual(results, [{"error": "Tool gmail_fetch_emails not found"}])
        mock_mcp_session.call_tool.assert_not_called()

    @patch.dict(os.environ, MOCKED_ENV_VARS_HTTP, clear=True)
    @patch('gmail_agent.email_filter.http_client') # HTTP client fails
    async def test_mcp_client_error_filter(self, mock_http_client):
        mock_http_client.return_value.__aenter__.side_effect = Exception("HTTP client broke")

        results = await email_filter.filter_emails()
        self.assertEqual(results, [{"error": "MCP client session failed for filtering"}])

    @patch.dict(os.environ, MOCKED_ENV_VARS_STDIO, clear=True)
    @patch('gmail_agent.email_filter.stdio_client')
    async def test_mcp_tool_call_error_filter(self, mock_stdio_client):
        mock_stdio_read, mock_stdio_write = AsyncMock(), AsyncMock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_stdio_read, mock_stdio_write)
        mock_mcp_session = AsyncMock(spec=ClientSession)
        mock_mcp_session.initialize = AsyncMock()
        mock_tool_list = MagicMock(tools=[MagicMock(name="gmail_fetch_emails")])
        mock_mcp_session.list_tools = AsyncMock(return_value=mock_tool_list)
        mock_mcp_session.call_tool = AsyncMock(side_effect=Exception("Tool call kaboom"))

        with patch('gmail_agent.email_filter.ClientSession', return_value=mock_mcp_session):
            results = await email_filter.filter_emails()

        self.assertEqual(results, [{"error": "Failed to call gmail_fetch_emails"}])

if __name__ == '__main__':
    unittest.main()
