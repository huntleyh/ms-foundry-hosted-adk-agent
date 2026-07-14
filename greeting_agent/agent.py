import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

load_dotenv()

# DefaultAzureCredential: uses managed identity when hosted, az login locally
_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)

root_agent = Agent(
    name="greeting_agent",
    model=LiteLlm(
        model=f"azure/{os.environ['AZURE_DEPLOYMENT_NAME']}",
        azure_ad_token_provider=_token_provider,     
    ),
    instruction="You are a helpful assistant. Greet the user warmly and answer their questions.",
)
