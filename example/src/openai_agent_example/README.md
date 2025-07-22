# UTCP OpenAI-Agents Example

This example demonstrates how to integrate the `utcp-client` with the `openai-agents` library to create a tool-using AI agent.

## How it Works

1.  **`server.py`**: A FastAPI application that serves a few mock "workout" tools. The `@utcp_tool` decorator automatically makes them discoverable.
2.  **`providers.json`**: A UTCP configuration file that points to the server's manual, allowing the client to discover the available tools.
3.  **`client.py`**:
    *   Initializes the `UtcpClient` to fetch all available tools from the server.
    *   Dynamically creates wrapper functions for the `openai-agents` library.
    *   Initializes an `Agent`, providing it with the wrapped tools.
    *   Starts a command-line loop where you can chat with the agent.

## How Tools are Defined and Discovered

The server uses the `@utcp_tool` decorator to define tools from standard FastAPI endpoints. For example, the `log_exercise` tool in `server.py` is defined like this:

```python
# From server.py

@utcp_tool(...)
@app.post("/workout/log", ...)
def log_exercise(exercise_name: str, sets: int, reps: int, weight_kg: float):
    # ... implementation ...
```

When the `UtcpClient` in `client.py` starts, it connects to the server and fetches the schema for all available tools. The `log_exercise` tool's properties are parsed into a `Tool` object that looks like this, which is then passed to the LLM:

```json
{
  "name": "gymbro_api.log_exercise",
  "description": "Logs the details of a completed exercise session to the user's history.",
  "parameters": {
    "type": "object",
    "properties": {
      "exercise_name": {
        "title": "Exercise Name",
        "type": "string"
      },
      "sets": {
        "title": "Sets",
        "type": "integer"
      },
      "reps": {
        "title": "Reps",
        "type": "integer"
      },
      "weight_kg": {
        "title": "Weight Kg",
        "type": "number"
      }
    },
    "required": [ "exercise_name", "sets", "reps", "weight_kg" ]
  }
}
```

## Example Agent Interaction

When you run the client and server, you can interact with the agent. The agent will decide when to call a tool based on your prompt.

**User Prompt:**
```
> Please log that I did 3 sets of 10 reps of Cable Flyes with 10kg
```

**Agent Execution Log:**
Here is what the `client.py` will print to the console. You can see the agent identifying the correct tool (`gymbro_api.log_exercise`), calling it with the correct arguments, receiving the result from the server, and then generating a friendly final response.

```
🤖 Agent is calling tool: gymbro_api.log_exercise with args: {'exercise_name': 'Cable Flyes', 'sets': 3, 'reps': 10, 'weight_kg': 10.0}
✅ Tool gymbro_api.log_exercise executed successfully. Result: {'status': 'success', 'message': 'Successfully logged 3x10 of Cable Flyes at 10.0kg.'}

Great job! You've successfully logged 3 sets of 10 reps of Cable Flyes at 10 kg. Keep up the fantastic work! If you need anything else or your next workout plan, just let me know! 💪
```

## Setup

1.  **Navigate to the example directory**:
    ```sh
    cd example/src/openai_agent_example
    ```
2.  **Install requirements**:
    ```sh
    pip install -r requirements.txt
    ```

## Running the Example

1.  **Start the server**:
    Open a terminal and run the FastAPI server on port 8081.
    ```sh
    uvicorn server:app --host 0.0.0.0 --port 8081 --reload
    ```

2.  **Run the agent client**:
    Open a second terminal (with the virtual environment activated) and run the client.
    ```sh
    python client.py
    ```

You can now chat with the agent. Try prompts like:
*   "What's the workout for today?"
*   "Can you log that I did 3 sets of 10 reps of bicep curls with 10kg?" 