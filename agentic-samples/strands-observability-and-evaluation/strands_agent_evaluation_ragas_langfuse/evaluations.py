#!/usr/bin/env python3
"""
Solar Panel Support Agent - Ragas Evaluation System

A comprehensive evaluation pipeline that fetches traces from Langfuse,
runs Ragas evaluations, and pushes scores back to Langfuse with proper
API rate limiting for the free tier.

Usage:
    python evaluations.py                           # Default: 1 trace, 1 hour lookback
    python evaluations.py --batch-size 10 --lookback-hours 24
    python evaluations.py --help
"""

import os
import sys
import time
import argparse
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import logging
from dataclasses import dataclass

# Third-party imports
from langfuse import Langfuse
from ragas.metrics import (
    ContextRelevance,
    ResponseGroundedness, 
    AspectCritic,
    RubricsScore
)
from ragas.dataset_schema import (
    SingleTurnSample,
    MultiTurnSample,
    EvaluationDataset
)
from ragas import evaluate
from langchain_aws import ChatBedrock
from ragas.llms import LangchainLLMWrapper
import boto3

# Local imports
from config import AgentConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class EvaluationConfig:
    """Configuration for evaluation parameters"""
    batch_size: int = 1
    lookback_hours: int = 1
    tags: Optional[List[str]] = None
    save_csv: bool = True
    output_dir: str = "evaluation_results"
    api_delay: float = 2.0  # Delay between API calls in seconds
    max_retries: int = 3
    retry_delay: float = 5.0

class RateLimitedLangfuse:
    """Wrapper around Langfuse client with rate limiting for free tier"""
    
    def __init__(self, langfuse_client: Langfuse, api_delay: float = 2.0):
        self.client = langfuse_client
        self.api_delay = api_delay
        self.last_call_time = 0
        
    def _wait_for_rate_limit(self):
        """Ensure we don't exceed rate limits"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        
        if time_since_last_call < self.api_delay:
            sleep_time = self.api_delay - time_since_last_call
            logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_call_time = time.time()
    
    def get_traces(self, **kwargs):
        """Rate-limited trace fetching"""
        self._wait_for_rate_limit()
        return self.client.api.trace.list(**kwargs)
    
    def get_observations(self, observation_id: str):
        """Rate-limited observation fetching (single observation)"""
        self._wait_for_rate_limit()
        return self.client.api.observations.get(observation_id)
    
    def get_observations_many(self, trace_id: str):
        """Rate-limited batch observation fetching (all observations for a trace)"""
        self._wait_for_rate_limit()
        return self.client.api.observations.get_many(trace_id=trace_id)
    
    def create_score(self, **kwargs):
        """Rate-limited score creation"""
        self._wait_for_rate_limit()
        return self.client.create_score(**kwargs)

class SolarAgentEvaluator:
    """Main evaluation class for the Solar Panel Support Agent"""
    
    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or EvaluationConfig()
        self.solar_config = AgentConfig.from_env()
        
        # Initialize Langfuse with rate limiting
        self.langfuse_client = Langfuse(
            public_key=self.solar_config.langfuse.public_key,
            secret_key=self.solar_config.langfuse.secret_key,
            host=self.solar_config.langfuse.host
        )
        self.langfuse = RateLimitedLangfuse(self.langfuse_client, self.config.api_delay)
        
        # Initialize evaluator LLM
        self.evaluator_llm = self._setup_evaluator_llm()
        
        # Initialize metrics
        self.rag_metrics = self._setup_rag_metrics()
        self.conversation_metrics = self._setup_conversation_metrics()
        
        logger.info(f"Initialized evaluator with config: batch_size={self.config.batch_size}, "
                   f"lookback_hours={self.config.lookback_hours}, api_delay={self.config.api_delay}")
    
    def _setup_evaluator_llm(self) -> LangchainLLMWrapper:
        """Setup the LLM for evaluation"""
        try:
            session = boto3.session.Session()
            region = session.region_name or self.solar_config.aws.region
            
            bedrock_llm = ChatBedrock(
                model_id=self.solar_config.strands.model,
                region_name=region
            )
            return LangchainLLMWrapper(bedrock_llm)
        except Exception as e:
            logger.warning(f"Failed to setup evaluator LLM: {e}")
            raise
    
    def _setup_rag_metrics(self) -> List:
        """Setup RAG-specific evaluation metrics"""
        return [
            ContextRelevance(llm=self.evaluator_llm),
            ResponseGroundedness(llm=self.evaluator_llm)
        ]
    
    def _setup_conversation_metrics(self) -> List:
        """Setup conversation and agent-specific evaluation metrics"""
        # Solar panel support specific metrics
        request_completeness = AspectCritic(
            name="Request Completeness",
            llm=self.evaluator_llm,
            definition=(
                "Return 1 if the solar panel support agent completely fulfills all the user requests "
                "with no omissions (e.g., creating tickets, providing technical information, "
                "checking ticket status). Otherwise, return 0."
            ),
        )
        
        technical_accuracy = AspectCritic(
            name="Technical Accuracy",
            llm=self.evaluator_llm,
            definition=(
                "Return 1 if the agent provides technically accurate information about solar panels, "
                "maintenance, troubleshooting, or related topics. Return 0 if the information is "
                "incorrect, misleading, or not technically sound."
            ),
        )
        
        customer_service_quality = AspectCritic(
            name="Customer Service Quality",
            llm=self.evaluator_llm,
            definition=(
                "Return 1 if the agent's communication is professional, empathetic, helpful, "
                "and appropriate for customer support interactions. Return 0 if the tone is "
                "inappropriate, unhelpful, or unprofessional."
            ),
        )
        
        tool_usage_effectiveness = AspectCritic(
            name="Tool Usage Effectiveness",
            llm=self.evaluator_llm,
            definition=(
                "Return 1 if the agent appropriately used available tools to fulfill the user's request "
                "(such as using search_solar_knowledge for technical questions, open_ticket for "
                "creating support tickets, get_ticket_status for checking tickets). "
                "Return 0 if the agent failed to use appropriate tools or used unnecessary tools."
            ),
        )
        
        # Solar-specific rubric for problem resolution
        problem_resolution_rubrics = {
            "score-1_description": (
                "The agent failed to address the customer's solar panel issue and provided "
                "no helpful guidance or next steps."
            ),
            "score0_description": (
                "The agent partially addressed the issue but missed key aspects or failed "
                "to provide complete resolution guidance."
            ),
            "score1_description": (
                "The agent fully addressed the customer's solar panel issue with appropriate "
                "technical guidance, ticket creation, or problem resolution steps."
            ),
        }
        
        problem_resolution = RubricsScore(
            rubrics=problem_resolution_rubrics, 
            llm=self.evaluator_llm, 
            name="Problem Resolution"
        )
        
        return [
            request_completeness,
            technical_accuracy,
            customer_service_quality,
            tool_usage_effectiveness,
            problem_resolution
        ]
    
    def fetch_traces(self) -> List[Any]:
        """Fetch traces from Langfuse with rate limiting"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=self.config.lookback_hours)
        
        logger.info(f"Fetching {self.config.batch_size} traces from {start_time} to {end_time}")
        
        try:
            if self.config.tags:
                traces = self.langfuse.get_traces(
                    limit=self.config.batch_size,
                    tags=self.config.tags,
                    from_timestamp=start_time,
                    to_timestamp=end_time
                ).data
            else:
                traces = self.langfuse.get_traces(
                    limit=self.config.batch_size,
                    from_timestamp=start_time,
                    to_timestamp=end_time
                ).data
            
            logger.info(f"Successfully fetched {len(traces)} traces")
            return traces
            
        except Exception as e:
            logger.error(f"Error fetching traces: {e}")
            return []
    
    def extract_span_components(self, trace) -> Dict[str, Any]:
        """Extract user queries, agent responses, retrieved contexts and tool usage from a trace"""
        user_inputs = []
        agent_responses = []
        retrieved_contexts = []
        tool_usages = []
        available_tools = []
        
        # Extract basic trace information
        if hasattr(trace, 'input') and trace.input is not None:
            if isinstance(trace.input, dict) and 'args' in trace.input:
                if trace.input['args'] and len(trace.input['args']) > 0:
                    user_inputs.append(str(trace.input['args'][0]))
            elif isinstance(trace.input, str):
                user_inputs.append(trace.input)
            else:
                user_inputs.append(str(trace.input))
        
        if hasattr(trace, 'output') and trace.output is not None:
            if isinstance(trace.output, str):
                agent_responses.append(trace.output)
            else:
                agent_responses.append(str(trace.output))
        
        # Extract observations using get_many() for efficiency (single API call per trace)
        if hasattr(trace, 'observations') and trace.observations:
            logger.info(f"Processing {len(trace.observations)} observations for trace {trace.id}")
            
            try:
                # Use get_many() to fetch all observations for this trace in one API call
                logger.info(f"Fetching all observations for trace {trace.id} in single API call")
                observations_response = self.langfuse.get_observations_many(trace.id)
                
                # Handle the response structure - it should be a list or have a .data attribute
                if hasattr(observations_response, 'data'):
                    observations = observations_response.data
                elif isinstance(observations_response, list):
                    observations = observations_response
                else:
                    logger.warning(f"Unexpected observations response format: {type(observations_response)}")
                    observations = []
                
                logger.info(f"Successfully fetched {len(observations)} observations for trace {trace.id}")
                
                for obs in observations:
                    try:
                        # Extract tool usage information
                        if hasattr(obs, 'name') and obs.name:
                            tool_name = str(obs.name)
                            tool_input = obs.input if hasattr(obs, 'input') and obs.input else None
                            tool_output = obs.output if hasattr(obs, 'output') and obs.output else None
                            
                            tool_usages.append({
                                "name": tool_name,
                                "input": tool_input,
                                "output": tool_output
                            })
                            
                            # Specifically capture retrieved contexts for RAG evaluation
                            if any(keyword in tool_name.lower() for keyword in ['retrieve', 'search', 'knowledge']):
                                if tool_output:
                                    retrieved_contexts.append(str(tool_output))
                    except Exception as e:
                        logger.warning(f"Error processing observation: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Error fetching observations for trace {trace.id}: {e}")
                # Fallback to individual observation fetching if get_many fails
                logger.info("Falling back to individual observation fetching")
                for i, obs_id in enumerate(trace.observations):
                    try:
                        logger.info(f"Fetching observation {i+1}/{len(trace.observations)}: {obs_id}")
                        observation = self.langfuse.get_observations(obs_id)
                        
                        # Handle single observation response
                        if hasattr(observation, 'name') and observation.name:
                            tool_name = str(observation.name)
                            tool_input = observation.input if hasattr(observation, 'input') and observation.input else None
                            tool_output = observation.output if hasattr(observation, 'output') and observation.output else None
                            
                            tool_usages.append({
                                "name": tool_name,
                                "input": tool_input,
                                "output": tool_output
                            })
                            
                            # Specifically capture retrieved contexts for RAG evaluation
                            if any(keyword in tool_name.lower() for keyword in ['retrieve', 'search', 'knowledge']):
                                if tool_output:
                                    retrieved_contexts.append(str(tool_output))
                                    
                    except Exception as e:
                        logger.warning(f"Error fetching observation {obs_id}: {e}")
                        continue
        
        # Extract available tools from metadata
        if hasattr(trace, 'metadata') and trace.metadata:
            if 'attributes' in trace.metadata:
                attributes = trace.metadata['attributes']
                if 'agent.tools' in attributes:
                    available_tools = attributes['agent.tools']
        
        return {
            "user_inputs": user_inputs,
            "agent_responses": agent_responses,
            "retrieved_contexts": retrieved_contexts,
            "tool_usages": tool_usages,
            "available_tools": available_tools
        }
    
    def process_traces(self, traces: List[Any]) -> Dict[str, Any]:
        """Process traces into samples for RAGAS evaluation"""
        single_turn_samples = []
        multi_turn_samples = []
        trace_sample_mapping = []
        
        logger.info(f"Processing {len(traces)} traces into evaluation samples")
        
        for trace in traces:
            try:
                # Extract components
                components = self.extract_span_components(trace)
                
                # Add tool usage information for evaluation context
                tool_info = ""
                if components["tool_usages"]:
                    tool_names = [t["name"] for t in components["tool_usages"] if "name" in t]
                    tool_info = f"Tools used: {', '.join(tool_names)}"
                
                # Convert to RAGAS samples
                if components["user_inputs"]:
                    # For RAG evaluation (single turn with retrieved contexts)
                    if components["retrieved_contexts"]:
                        single_turn_samples.append(
                            SingleTurnSample(
                                user_input=components["user_inputs"][0],
                                response=components["agent_responses"][0] if components["agent_responses"] else "",
                                retrieved_contexts=components["retrieved_contexts"],
                                metadata={
                                    "tool_usages": components["tool_usages"],
                                    "available_tools": components["available_tools"],
                                    "tool_info": tool_info,
                                    "trace_id": trace.id
                                }
                            )
                        )
                        trace_sample_mapping.append({
                            "trace_id": trace.id,
                            "type": "single_turn",
                            "index": len(single_turn_samples) - 1
                        })
                    
                    # For conversation evaluation (multi-turn or single turn without RAG)
                    else:
                        messages = []
                        max_turns = max(len(components["user_inputs"]), len(components["agent_responses"]))
                        
                        for i in range(max_turns):
                            if i < len(components["user_inputs"]):
                                messages.append({
                                    "role": "user", 
                                    "content": components["user_inputs"][i]
                                })
                            if i < len(components["agent_responses"]):
                                response_content = components["agent_responses"][i]
                                if tool_info:
                                    response_content += f"\n\n{tool_info}"
                                messages.append({
                                    "role": "assistant",
                                    "content": response_content
                                })
                        
                        multi_turn_samples.append(
                            MultiTurnSample(
                                user_input=messages,
                                metadata={
                                    "tool_usages": components["tool_usages"],
                                    "available_tools": components["available_tools"],
                                    "trace_id": trace.id
                                }
                            )
                        )
                        trace_sample_mapping.append({
                            "trace_id": trace.id,
                            "type": "multi_turn",
                            "index": len(multi_turn_samples) - 1
                        })
                        
            except Exception as e:
                logger.error(f"Error processing trace {trace.id}: {e}")
                continue
        
        logger.info(f"Created {len(single_turn_samples)} single-turn and {len(multi_turn_samples)} multi-turn samples")
        
        return {
            "single_turn_samples": single_turn_samples,
            "multi_turn_samples": multi_turn_samples,
            "trace_sample_mapping": trace_sample_mapping
        }
    
    def evaluate_rag_samples(self, single_turn_samples: List[SingleTurnSample], 
                           trace_sample_mapping: List[Dict]) -> Optional[pd.DataFrame]:
        """Evaluate RAG-based samples and push scores to Langfuse"""
        if not single_turn_samples:
            logger.info("No single-turn samples to evaluate")
            return None
        
        logger.info(f"Evaluating {len(single_turn_samples)} single-turn samples with RAG metrics")
        
        try:
            rag_dataset = EvaluationDataset(samples=single_turn_samples)
            rag_results = evaluate(
                dataset=rag_dataset,
                metrics=self.rag_metrics
            )
            rag_df = rag_results.to_pandas()
            
            # Push RAG scores back to Langfuse with rate limiting
            logger.info("Pushing RAG evaluation scores back to Langfuse")
            for mapping in trace_sample_mapping:
                if mapping["type"] == "single_turn":
                    sample_index = mapping["index"]
                    trace_id = mapping["trace_id"]
                    
                    if sample_index < len(rag_df):
                        for metric_name in rag_df.columns:
                            if metric_name not in ['user_input', 'response', 'retrieved_contexts']:
                                try:
                                    metric_value = float(rag_df.iloc[sample_index][metric_name])
                                    if not pd.isna(metric_value):
                                        self.langfuse.create_score(
                                            trace_id=trace_id,
                                            name=f"rag_{metric_name}",
                                            value=metric_value
                                        )
                                        logger.info(f"Added score rag_{metric_name}={metric_value} to trace {trace_id}")
                                except Exception as e:
                                    logger.error(f"Error adding RAG score {metric_name}: {e}")
            
            return rag_df
            
        except Exception as e:
            logger.error(f"Error evaluating RAG samples: {e}")
            return None
    
    def evaluate_conversation_samples(self, multi_turn_samples: List[MultiTurnSample], 
                                    trace_sample_mapping: List[Dict]) -> Optional[pd.DataFrame]:
        """Evaluate conversation-based samples and push scores to Langfuse"""
        if not multi_turn_samples:
            logger.info("No multi-turn samples to evaluate")
            return None
        
        logger.info(f"Evaluating {len(multi_turn_samples)} multi-turn samples with conversation metrics")
        
        try:
            conv_dataset = EvaluationDataset(samples=multi_turn_samples)
            conv_results = evaluate(
                dataset=conv_dataset,
                metrics=self.conversation_metrics
            )
            conv_df = conv_results.to_pandas()
            
            # Push conversation scores back to Langfuse with rate limiting
            logger.info("Pushing conversation evaluation scores back to Langfuse")
            for mapping in trace_sample_mapping:
                if mapping["type"] == "multi_turn":
                    sample_index = mapping["index"]
                    trace_id = mapping["trace_id"]
                    
                    if sample_index < len(conv_df):
                        for metric_name in conv_df.columns:
                            if metric_name not in ['user_input']:
                                try:
                                    metric_value = float(conv_df.iloc[sample_index][metric_name])
                                    if pd.isna(metric_value):
                                        metric_value = 0.0
                                    
                                    self.langfuse.create_score(
                                        trace_id=trace_id,
                                        name=metric_name,
                                        value=metric_value
                                    )
                                    logger.info(f"Added score {metric_name}={metric_value} to trace {trace_id}")
                                except Exception as e:
                                    logger.error(f"Error adding conversation score {metric_name}: {e}")
            
            return conv_df
            
        except Exception as e:
            logger.error(f"Error evaluating conversation samples: {e}")
            return None
    
    def save_results_to_csv(self, rag_df: Optional[pd.DataFrame] = None, 
                          conv_df: Optional[pd.DataFrame] = None) -> Dict[str, str]:
        """Save evaluation results to CSV files"""
        os.makedirs(self.config.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        results = {}
        
        if rag_df is not None and not rag_df.empty:
            rag_file = os.path.join(self.config.output_dir, f"solar_rag_evaluation_{timestamp}.csv")
            rag_df.to_csv(rag_file, index=False)
            logger.info(f"RAG evaluation results saved to {rag_file}")
            results["rag_file"] = rag_file
        
        if conv_df is not None and not conv_df.empty:
            conv_file = os.path.join(self.config.output_dir, f"solar_conversation_evaluation_{timestamp}.csv")
            conv_df.to_csv(conv_file, index=False)
            logger.info(f"Conversation evaluation results saved to {conv_file}")
            results["conv_file"] = conv_file
        
        return results
    
    def run_evaluation(self) -> Dict[str, Any]:
        """Main evaluation pipeline"""
        logger.info("Starting Solar Agent evaluation pipeline")
        
        try:
            # Step 1: Fetch traces from Langfuse
            traces = self.fetch_traces()
            if not traces:
                logger.warning("No traces found. Exiting evaluation.")
                return {"status": "no_traces", "results": None}
            
            # Step 2: Process traces into evaluation samples
            processed_data = self.process_traces(traces)
            
            # Step 3: Run RAG evaluation
            rag_df = self.evaluate_rag_samples(
                processed_data["single_turn_samples"],
                processed_data["trace_sample_mapping"]
            )
            
            # Step 4: Run conversation evaluation
            conv_df = self.evaluate_conversation_samples(
                processed_data["multi_turn_samples"],
                processed_data["trace_sample_mapping"]
            )
            
            # Step 5: Save results if requested
            saved_files = {}
            if self.config.save_csv:
                saved_files = self.save_results_to_csv(rag_df, conv_df)
            
            # Step 6: Generate summary
            summary = self._generate_evaluation_summary(rag_df, conv_df)
            
            logger.info("Evaluation pipeline completed successfully")
            
            return {
                "status": "success",
                "results": {
                    "rag_results": rag_df,
                    "conversation_results": conv_df,
                    "saved_files": saved_files,
                    "summary": summary
                }
            }
            
        except Exception as e:
            logger.error(f"Evaluation pipeline failed: {e}")
            return {"status": "error", "error": str(e), "results": None}
    
    def _generate_evaluation_summary(self, rag_df: Optional[pd.DataFrame], 
                                   conv_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Generate a summary of evaluation results"""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "batch_size": self.config.batch_size,
                "lookback_hours": self.config.lookback_hours,
                "tags": self.config.tags
            }
        }
        
        if rag_df is not None and not rag_df.empty:
            summary["rag_evaluation"] = {
                "samples_evaluated": len(rag_df),
                "metrics": {}
            }
            
            for col in rag_df.columns:
                if col not in ['user_input', 'response', 'retrieved_contexts']:
                    try:
                        values = pd.to_numeric(rag_df[col], errors='coerce')
                        summary["rag_evaluation"]["metrics"][col] = {
                            "mean": float(values.mean()),
                            "std": float(values.std()),
                            "min": float(values.min()),
                            "max": float(values.max())
                        }
                    except:
                        pass
        
        if conv_df is not None and not conv_df.empty:
            summary["conversation_evaluation"] = {
                "samples_evaluated": len(conv_df),
                "metrics": {}
            }
            
            for col in conv_df.columns:
                if col not in ['user_input']:
                    try:
                        values = pd.to_numeric(conv_df[col], errors='coerce')
                        summary["conversation_evaluation"]["metrics"][col] = {
                            "mean": float(values.mean()),
                            "std": float(values.std()),
                            "min": float(values.min()),
                            "max": float(values.max())
                        }
                    except:
                        pass
        
        return summary

def main():
    """Main function with command-line argument support"""
    parser = argparse.ArgumentParser(
        description="Solar Panel Support Agent - Ragas Evaluation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python evaluations.py                           # Default: 1 trace, 1 hour lookback
  python evaluations.py --batch-size 10          # Fetch 10 traces
  python evaluations.py --lookback-hours 24      # Look back 24 hours
  python evaluations.py --batch-size 5 --lookback-hours 12 --tags solar-agent
  python evaluations.py --no-csv                 # Don't save CSV files
  python evaluations.py --api-delay 3.0          # 3 second delay between API calls
        """
    )
    
    parser.add_argument(
        '--batch-size', 
        type=int, 
        default=1,
        help='Number of traces to fetch (default: 1, respects free tier limits)'
    )
    
    parser.add_argument(
        '--lookback-hours', 
        type=int, 
        default=1,
        help='Hours to look back for traces (default: 1)'
    )
    
    parser.add_argument(
        '--tags', 
        nargs='+',
        help='Filter traces by tags (e.g., --tags solar-agent production)'
    )
    
    parser.add_argument(
        '--no-csv', 
        action='store_true',
        help='Skip saving results to CSV files'
    )
    
    parser.add_argument(
        '--output-dir', 
        default='evaluation_results',
        help='Directory to save results (default: evaluation_results)'
    )
    
    parser.add_argument(
        '--api-delay', 
        type=float, 
        default=2.0,
        help='Delay between API calls in seconds (default: 2.0)'
    )
    
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create evaluation configuration
    eval_config = EvaluationConfig(
        batch_size=args.batch_size,
        lookback_hours=args.lookback_hours,
        tags=args.tags,
        save_csv=not args.no_csv,
        output_dir=args.output_dir,
        api_delay=args.api_delay
    )
    
    # Validate configuration for free tier
    if eval_config.batch_size > 20:
        logger.warning(f"Batch size {eval_config.batch_size} may exceed free tier limits. Consider reducing.")
    
    if eval_config.api_delay < 1.0:
        logger.warning(f"API delay {eval_config.api_delay}s may be too aggressive for free tier.")
    
    # Run evaluation
    try:
        evaluator = SolarAgentEvaluator(eval_config)
        results = evaluator.run_evaluation()
        
        if results["status"] == "success":
            print("\n" + "="*60)
            print("SOLAR AGENT EVALUATION COMPLETED SUCCESSFULLY")
            print("="*60)
            
            if results["results"]["summary"]:
                summary = results["results"]["summary"]
                print(f"\nEvaluation Summary:")
                print(f"- Timestamp: {summary['timestamp']}")
                print(f"- Configuration: {summary['config']}")
                
                if "rag_evaluation" in summary:
                    rag_eval = summary["rag_evaluation"]
                    print(f"\nRAG Evaluation:")
                    print(f"- Samples evaluated: {rag_eval['samples_evaluated']}")
                    for metric, stats in rag_eval["metrics"].items():
                        print(f"- {metric}: mean={stats['mean']:.3f}, std={stats['std']:.3f}")
                
                if "conversation_evaluation" in summary:
                    conv_eval = summary["conversation_evaluation"]
                    print(f"\nConversation Evaluation:")
                    print(f"- Samples evaluated: {conv_eval['samples_evaluated']}")
                    for metric, stats in conv_eval["metrics"].items():
                        print(f"- {metric}: mean={stats['mean']:.3f}, std={stats['std']:.3f}")
            
            if results["results"]["saved_files"]:
                print(f"\nSaved Files:")
                for file_type, file_path in results["results"]["saved_files"].items():
                    print(f"- {file_type}: {file_path}")
            
            print(f"\nCheck your Langfuse dashboard to see the evaluation scores!")
            
        elif results["status"] == "no_traces":
            print("\nNo traces found for the specified criteria.")
            print("Try adjusting --lookback-hours or --tags parameters.")
            
        else:
            print(f"\nEvaluation failed: {results.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nEvaluation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
