"""
deploy.py  —  Deploy greeting-agent as a Foundry Hosted Agent via Python SDK.

IMPORTANT: Do NOT delete the agent between deployments. The agent's instance_identity
is stable as long as the agent exists — deleting it creates a new identity that
requires re-assigning Cognitive Services roles. Instead, create new versions:
  - Roles are assigned ONCE to the stable instance_identity (see grant-roles below)
  - Each 'python deploy.py' creates a new immutable version with the latest image

Workflow:
  # 1. Build and push a new image (use a version tag, not :latest, so Foundry
  #    detects the change and creates a real new version)
  az acr build --registry acragentfzu5sn \\
    --image greeting-agent:$(Get-Date -Format 'yyyyMMdd-HHmm') \\
    --file Dockerfile .

  # 2. Deploy the new version (update ACR_IMAGE below or pass --image)
  python deploy.py [--image greeting-agent:<tag>]

  # 3. Invoke for testing
  python deploy.py --invoke "hello"

  # One-time role setup (only needed after the FIRST ever deployment, or if
  # you accidentally deleted the agent):
  python deploy.py --grant-roles
"""

import argparse
import time
import sys

PROJECT_ENDPOINT  = "https://aifoundry9263.services.ai.azure.com/api/projects/agent-project"
ACR_REGISTRY      = "acragentfzu5sn.azurecr.io"
ACR_IMAGE         = f"{ACR_REGISTRY}/greeting-agent:latest"   # override with --image
AGENT_NAME        = "greeting-agent"
FOUNDRY_ACCOUNT_ID = (
    "/subscriptions/3ce66af2-55dc-48a9-8498-d973bda26aa5"
    "/resourceGroups/rg-aifoundry9263"
    "/providers/Microsoft.CognitiveServices/accounts/aifoundry9263"
)


def get_client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    return AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def deploy(image: str = ACR_IMAGE):
    from azure.ai.projects.models import (
        HostedAgentDefinition,
        ProtocolVersionRecord,
        AgentEndpointProtocol,
        ContainerConfiguration,
    )

    project = get_client()
    print(f"Deploying {AGENT_NAME} from {image} ...")

    # create_version either creates a new version (if image/config changed)
    # or returns the existing version (if nothing changed) — either way the
    # agent identity stays the same so roles don't need to be re-assigned.
    agent = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=HostedAgentDefinition(
            protocol_versions=[
                ProtocolVersionRecord(protocol=AgentEndpointProtocol.RESPONSES, version="1.0.0")
            ],
            cpu="0.5",
            memory="1Gi",
            container_configuration=ContainerConfiguration(image=image),
            environment_variables={
                "AZURE_API_BASE":        "https://aifoundry9263.openai.azure.com/",
                "AZURE_API_VERSION":     "2024-12-01-preview",
                "AZURE_DEPLOYMENT_NAME": "gpt-4.1",
            },
        ),
    )
    print(f"Version: {agent.version}  (polling for active status...)")

    while True:
        info = project.agents.get_version(agent_name=AGENT_NAME, agent_version=agent.version)
        status = info.get("status", "unknown")
        print(f"  status: {status}")
        if status == "active":
            iid = info.get("instance_identity", {}).get("principal_id", "?")
            print(f"\nAgent is ready.")
            print(f"Instance identity (stable): {iid}")
            print(f"Endpoint: {PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint/protocols/openai/responses")
            return iid
        if status == "failed":
            print(f"Provisioning failed: {info.get('error')}")
            sys.exit(1)
        time.sleep(5)


def grant_roles(principal_id: str = None):
    """Assign Cognitive Services roles to the agent's instance identity.

    Only needs to run ONCE per agent lifetime (not per version).
    """
    import subprocess

    if not principal_id:
        project = get_client()
        v = project.agents.get_version(agent_name=AGENT_NAME, agent_version="1")
        principal_id = v["instance_identity"]["principal_id"]

    print(f"Granting roles to {principal_id} on {FOUNDRY_ACCOUNT_ID} ...")
    for role in ["Cognitive Services OpenAI User", "Cognitive Services User"]:
        result = subprocess.run([
            "az.cmd", "role", "assignment", "create",
            "--assignee-object-id", principal_id,
            "--assignee-principal-type", "ServicePrincipal",
            "--role", role,
            "--scope", FOUNDRY_ACCOUNT_ID,
            "--query", "roleDefinitionName", "-o", "tsv",
        ], capture_output=True, text=True)
        name = result.stdout.strip() or result.stderr.strip()[:80]
        print(f"  {role}: {name or 'already exists'}")


def invoke(message: str):
    project = get_client()
    openai_client = project.get_openai_client(agent_name=AGENT_NAME)
    response = openai_client.responses.create(input=message)
    print(response.output_text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoke",      metavar="MESSAGE", help="Invoke the deployed agent")
    parser.add_argument("--grant-roles", action="store_true", help="Assign Cognitive Services roles (one-time setup)")
    parser.add_argument("--image",       metavar="TAG",     help="Override ACR image tag (e.g. greeting-agent:20260714-1200)")
    args = parser.parse_args()

    if args.invoke:
        invoke(args.invoke)
    elif args.grant_roles:
        grant_roles()
    else:
        image = f"{ACR_REGISTRY}/{args.image}" if args.image else ACR_IMAGE
        instance_id = deploy(image=image)
        # Remind the user about one-time role setup if this is the first deployment
        print(f"\nIf this is a new agent (first deployment), run:")
        print(f"  python deploy.py --grant-roles")
