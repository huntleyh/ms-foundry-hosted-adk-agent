import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

load_dotenv()

_api_key = os.environ.get("AZURE_API_KEY")

if _api_key:
    # API key auth — no token provider needed
    _model_kwargs = {"api_key": _api_key}
else:
    # Fallback: DefaultAzureCredential (managed identity when hosted, az login locally)
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    _token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    _model_kwargs = {"azure_ad_token_provider": _token_provider}

root_agent = Agent(
    name="greeting_agent",
    model=LiteLlm(
        model=f"azure/{os.environ['AZURE_DEPLOYMENT_NAME']}",
        **_model_kwargs,
    ),
    instruction="You are a helpful assistant. Greet the user warmly and answer their questions.",
)
