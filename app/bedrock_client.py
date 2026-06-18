import os
from typing import Any


class BedrockAdvisor:
    def __init__(self) -> None:
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "")
        self.enabled = os.getenv("USE_BEDROCK", "false").lower() == "true" and bool(self.model_id)

    def generate(self, system_prompt: str, user_prompt: str, context: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None

        try:
            import boto3
        except ImportError:
            return None

        try:
            client = boto3.client("bedrock-runtime", region_name=self.region)
            response = client.converse(
                modelId=self.model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": (
                                    "Use only this approved AWS service-pack context. "
                                    "Do not invent services, metrics, IAM actions, or controls.\n\n"
                                    f"Context:\n{context}\n\n"
                                    f"User question:\n{user_prompt}"
                                )
                            }
                        ],
                    }
                ],
                inferenceConfig={"temperature": 0.2, "maxTokens": 1400},
            )
            return response["output"]["message"]["content"][0]["text"]
        except Exception:
            return None

