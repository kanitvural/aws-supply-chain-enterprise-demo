"""Guardrails Stack — Bedrock Guardrails for content & PII filtering.

Creates a guardrail with:
  - Word filter: "Project Meridian" blocked
  - Profanity filter: enabled
  - Content filters: HATE, INSULTS, MISCONDUCT, VIOLENCE at HIGH strength
  - PII: USERNAME anonymized, PASSWORD blocked
  - Regex: discount codes (DISC-[A-Z]{3}-\\d{4}) anonymized
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_bedrock as bedrock,
)
from constructs import Construct


class GuardrailsStack(Stack):
    """Security layer: Bedrock Guardrail for input/output filtering."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Guardrail
        # ------------------------------------------------------------------
        self.guardrail = bedrock.CfnGuardrail(
            self,
            "SupplyChainGuardrail",
            name="SupplyChainGuardrail",
            blocked_input_messaging=(
                "This question cannot be answered due to our security policies."
            ),
            blocked_outputs_messaging=(
                "This response was blocked by our content policy."
            ),
            description="Content and PII guardrail for Supply Chain AI Assistant",
            # ---- Word policy ----
            word_policy_config=bedrock.CfnGuardrail.WordPolicyConfigProperty(
                words_config=[
                    bedrock.CfnGuardrail.WordConfigProperty(text="Project Meridian"),
                ],
                managed_word_lists_config=[
                    bedrock.CfnGuardrail.ManagedWordsConfigProperty(type="PROFANITY"),
                ],
            ),
            # ---- Content filter policy ----
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="INSULTS",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="MISCONDUCT",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="VIOLENCE",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                ],
            ),
            # ---- Sensitive information (PII + regex) ----
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        type="USERNAME",
                        action="ANONYMIZE",
                    ),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        type="PASSWORD",
                        action="BLOCK",
                    ),
                ],
                regexes_config=[
                    bedrock.CfnGuardrail.RegexConfigProperty(
                        name="DiscountCode",
                        description="Anonymize internal discount codes",
                        pattern=r"DISC-[A-Z]{3}-\d{4}",
                        action="ANONYMIZE",
                    ),
                ],
            ),
        )

        # ------------------------------------------------------------------
        # Expose for AgentCore stack
        # ------------------------------------------------------------------
        self.guardrail_id = self.guardrail.attr_guardrail_id

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        CfnOutput(self, "GuardrailId", value=self.guardrail.attr_guardrail_id)
        CfnOutput(self, "GuardrailArn", value=self.guardrail.attr_guardrail_arn)
