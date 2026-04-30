import json
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_bedrock as bedrock,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
)
from constructs import Construct

AGENT_NAME = "PrivateAviationAgent"
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an AI assistant for a private aviation company. You help book private jet
reservations for aircraft owners and their families.

When a user requests a trip:
1. Look up the owner's information using their owner ID to find their home airport.
2. Look up the owner's registered passengers (family members).
3. Determine the departure airport (owner's home airport) and arrival airport based on the destination.
4. Compute the flight date/time based on the user's request.
5. Book the reservation with all passengers.

Important:
- Disney World is near Orlando, Florida. The nearest airport is KMCO (Orlando International).
- Always use ICAO airport codes (e.g., KJFK, KMCO, KLAX).
- When the user says "family", include all registered passengers for the owner.
- Format dates in ISO 8601 format."""

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class BedrockAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # MODEL_ID is a cross-region inference profile (e.g. global.anthropic...).
        # Bedrock routes the actual model call to a regional foundation-model
        # endpoint the profile selects, so the role needs invoke permissions
        # on both the profile itself and the underlying foundation models.
        agent_role = iam.Role(
            self, "AgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "BedrockInvoke": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream",
                            ],
                            resources=[
                                f"arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:*:{self.account}:inference-profile/{MODEL_ID}",
                            ],
                        )
                    ]
                )
            },
        )

        lambda_role = iam.Role(
            self, "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        fn_get_owner = _lambda.Function(
            self, "GetOwnerInfoFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset(
                str(PROJECT_ROOT / "lambda_functions" / "get_owner_info")
            ),
            role=lambda_role,
            timeout=Duration.seconds(30),
            function_name=f"{AGENT_NAME}-GetOwnerInfo",
        )

        fn_get_passengers = _lambda.Function(
            self, "GetPassengersFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset(
                str(PROJECT_ROOT / "lambda_functions" / "get_passengers")
            ),
            role=lambda_role,
            timeout=Duration.seconds(30),
            function_name=f"{AGENT_NAME}-GetPassengers",
        )

        fn_book_reservation = _lambda.Function(
            self, "BookReservationFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset(
                str(PROJECT_ROOT / "lambda_functions" / "book_reservation")
            ),
            role=lambda_role,
            timeout=Duration.seconds(30),
            function_name=f"{AGENT_NAME}-BookReservation",
        )

        for fn in [fn_get_owner, fn_get_passengers, fn_book_reservation]:
            fn.add_permission(
                "BedrockInvoke",
                principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
                action="lambda:InvokeFunction",
                source_account=self.account,
            )

        log_group = logs.LogGroup(
            self, "AgentLogGroup",
            log_group_name=f"/aws/bedrock/agents/{AGENT_NAME}",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # Bedrock Agents action groups are 1:1 with Lambda functions — each
        # action group's executor points to exactly one Lambda ARN. The agent
        # uses functionSchema rather than apiSchema because the AgentCore CLI
        # import path (`agentcore create --type import`) only translates
        # functionSchema-based action groups into @tool scaffolding.
        action_groups = [
            bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="OwnerInfo",
                description="Look up owner profile and home airport.",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                    lambda_=fn_get_owner.function_arn,
                ),
                function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                    functions=[
                        bedrock.CfnAgent.FunctionProperty(
                            name="get_owner_info",
                            description="Retrieve the profile of a private jet owner — name and home airport — by owner ID.",
                            parameters={
                                "ownerId": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="Unique identifier of the jet owner (UUID format).",
                                    required=True,
                                ),
                            },
                        ),
                    ],
                ),
            ),
            bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="Passengers",
                description="List registered passengers for an owner.",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                    lambda_=fn_get_passengers.function_arn,
                ),
                function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                    functions=[
                        bedrock.CfnAgent.FunctionProperty(
                            name="get_passengers",
                            description="List the family members and registered passengers associated with an owner.",
                            parameters={
                                "ownerId": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="Unique identifier of the jet owner (UUID format).",
                                    required=True,
                                ),
                            },
                        ),
                    ],
                ),
            ),
            bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="Reservations",
                description="Book a private jet reservation.",
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                    lambda_=fn_book_reservation.function_arn,
                ),
                function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                    functions=[
                        # Bedrock Agents caps functionSchema at 5 parameters per
                        # function. The Lambda derives the primary passenger
                        # from the ownerId and includes the full manifest from
                        # the pre-fetched passengers list.
                        bedrock.CfnAgent.FunctionProperty(
                            name="book_reservation",
                            description="Book a private jet reservation for the owner and their registered passengers.",
                            parameters={
                                "ownerId": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="Unique identifier of the jet owner.",
                                    required=True,
                                ),
                                "date": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="Flight date and time in ISO 8601 format.",
                                    required=True,
                                ),
                                "departureAirport": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="ICAO code of the departure airport (e.g. KJFK).",
                                    required=True,
                                ),
                                "arrivalAirport": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="ICAO code of the arrival airport (e.g. KMCO).",
                                    required=True,
                                ),
                                "passengers": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="JSON-encoded array of passenger objects, e.g. [{\"firstname\":\"Jill\",\"lastname\":\"Doe\",\"age\":39}].",
                                    required=True,
                                ),
                            },
                        ),
                    ],
                ),
            ),
        ]

        cfn_agent = bedrock.CfnAgent(
            self, "Agent",
            agent_name=AGENT_NAME,
            agent_resource_role_arn=agent_role.role_arn,
            foundation_model=MODEL_ID,
            instruction=SYSTEM_PROMPT,
            idle_session_ttl_in_seconds=600,
            auto_prepare=True,
            action_groups=action_groups,
        )

        cfn_alias = bedrock.CfnAgentAlias(
            self, "AgentAlias",
            agent_id=cfn_agent.attr_agent_id,
            agent_alias_name="live",
        )
        cfn_alias.add_dependency(cfn_agent)

        CfnOutput(self, "AgentId", value=cfn_agent.attr_agent_id)
        CfnOutput(self, "AgentAliasId", value=cfn_alias.attr_agent_alias_id)
        CfnOutput(self, "GetOwnerInfoArn", value=fn_get_owner.function_arn)
        CfnOutput(self, "GetPassengersArn", value=fn_get_passengers.function_arn)
        CfnOutput(self, "BookReservationArn", value=fn_book_reservation.function_arn)
