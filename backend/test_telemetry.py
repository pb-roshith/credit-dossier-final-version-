"""
test_telemetry.py
-----------------
Standalone script to verify Mistral telemetry is working end-to-end.

Uploads a trace of an agent executing multiple tools to Mistral's
telemetry backend, with redaction=True and custom credit_dossier.* attributes.

Usage:
    cd backend
    python test_telemetry.py
"""
import os
import sys

# CRITICAL: Override system-level OTEL_SDK_DISABLED before any OTel imports
os.environ["OTEL_SDK_DISABLED"] = "false"

import time
import json
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Load .env from the backend directory
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
API_KEY = os.getenv("MISTRAL_API_KEY", "")

if not API_KEY or API_KEY == "your_mistral_api_key_here":
    print("❌ MISTRAL_API_KEY not set in .env file")
    sys.exit(1)

# 1. Initialize client & telemetry (v2.7+ API)
from mistralai.client import Mistral
from mistralai.extra.observability import configure_telemetry, get_telemetry_tracer

client = Mistral(api_key=API_KEY)
configure_telemetry(client, provider="dedicated", redaction=True)
tracer = get_telemetry_tracer(client, "credit-dossier-test")

print("✓ Mistral client created with telemetry (provider=dedicated, redaction=True)")


# 2. Set up MLflow logging (optional — skips gracefully if not installed)
try:
    import mlflow
    mlflow.set_experiment("credit-dossier-telemetry-test")
    mlflow.opentelemetry.autolog()
    print("✓ MLflow trace logging enabled")
except ImportError:
    print("ℹ MLflow not installed — traces go to Mistral's dashboard only")
    print("  Install later with: pip install mlflow>=2.14.0")
except Exception as e:
    print(f"⚠ MLflow setup failed: {e}")


# 3. Define local tools (mock functions for testing)
def get_current_weather(location: str) -> str:
    return f"The current weather in {location} is 22°C and sunny."

def calculate_conversion(amount: float, from_curr: str, to_curr: str) -> str:
    return f"{amount} {from_curr} = {amount * 1.08:.2f} {to_curr}"

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_conversion",
            "description": "Convert currency amount",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "from_curr": {"type": "string"},
                    "to_curr": {"type": "string"}
                },
                "required": ["amount", "from_curr", "to_curr"]
            }
        }
    }
]

# 4. Run the agent with telemetry tracing
print()
print("=" * 60)
print("  Sending Agent with Multiple Tools Trace...")
print("  (with credit_dossier.* custom attributes)")
print("=" * 60)

with tracer.start_as_current_span("agent_tools_execution") as agent_span:
    # Custom attributes for Mistral dashboard filtering
    agent_span.set_attribute("gen_ai.agent.name", "weather_and_finance_agent")
    agent_span.set_attribute("gen_ai.system", "mistral")
    agent_span.set_attribute("credit_dossier.operation", "test_telemetry")
    agent_span.set_attribute("credit_dossier.app_version", "2.0.0")
    agent_span.set_attribute("credit_dossier.environment", "development")
    
    messages = [{"role": "user", "content": "What is the weather in Paris, and convert 100 EUR to USD?"}]
    
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    msg = response.choices[0].message
    if msg.tool_calls:
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            
            with tracer.start_as_current_span(f"execute_tool {func_name}") as tool_span:
                tool_span.set_attribute("gen_ai.tool.name", func_name)
                tool_span.set_attribute("gen_ai.tool.call.arguments", str(args))
                # Custom attributes for dashboard filtering
                tool_span.set_attribute("credit_dossier.operation", f"tool_{func_name}")
                tool_span.set_attribute("credit_dossier.tool_name", func_name)
                
                if func_name == "get_current_weather":
                    result = get_current_weather(args.get("location", ""))
                elif func_name == "calculate_conversion":
                    result = calculate_conversion(args.get("amount", 0), args.get("from_curr", ""), args.get("to_curr", ""))
                else:
                    result = "Unknown tool"
                
                tool_span.set_attribute("gen_ai.tool.result", str(result))
                tool_span.set_attribute("credit_dossier.tool_result", str(result))
                print(f"  ✓ Executed Tool [{func_name}]: {result}")
    else:
        print("  ⚠ No tool calls in response — model responded directly:")
        print(f"    {msg.content[:200] if msg.content else '(empty)'}")

print()
print("Flushing telemetry (waiting 5s)...")
time.sleep(5)
print()
print("=" * 60)
print("  ✓ Done! Telemetry trace sent.")
print()
print("  Custom attributes sent:")
print("    credit_dossier.operation")
print("    credit_dossier.app_version")
print("    credit_dossier.environment")
print("    credit_dossier.tool_name")
print("    credit_dossier.tool_result")
print()
print("  View traces:")
print("    • Mistral Dashboard: https://console.mistral.ai/")
print("    • MLflow (local):    mlflow ui --port 5000")
print("=" * 60)
