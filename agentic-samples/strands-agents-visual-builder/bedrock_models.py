import boto3
from typing import List, Dict, Any, Tuple, Optional

def get_model_display_name(model_id: str) -> str:
    """
    Convert a Bedrock model ID to a clean display name.
    
    Args:
        model_id: The model ID (e.g., "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        
    Returns:
        A clean display name (e.g., "Claude 3.7 Sonnet")
    """
    # Handle common model patterns
    if "anthropic.claude" in model_id:
        # Extract the model name from the ID
        if "claude-3" in model_id:
            # For Claude 3 models, extract the version (e.g., 3.5, 3.7)
            if "claude-3-5" in model_id:
                return "Claude 3.5"
            elif "claude-3-7" in model_id:
                if "sonnet" in model_id.lower():
                    return "Claude 3.7 Sonnet"
                elif "haiku" in model_id.lower():
                    return "Claude 3.7 Haiku"
                elif "opus" in model_id.lower():
                    return "Claude 3.7 Opus"
                else:
                    return "Claude 3.7"
            elif "claude-3-sonnet" in model_id.lower():
                return "Claude 3 Sonnet"
            elif "claude-3-haiku" in model_id.lower():
                return "Claude 3 Haiku"
            elif "claude-3-opus" in model_id.lower():
                return "Claude 3 Opus"
            else:
                return "Claude 3"
        elif "claude-2" in model_id:
            return "Claude 2"
        elif "claude-instant" in model_id:
            return "Claude Instant"
        else:
            return "Claude"
    elif "amazon.titan" in model_id:
        if "text" in model_id.lower():
            if "express" in model_id.lower():
                return "Titan Text Express"
            elif "lite" in model_id.lower():
                return "Titan Text Lite"
            else:
                return "Titan Text"
        else:
            return "Titan"
    elif "meta.llama" in model_id:
        if "llama-3" in model_id:
            if "70b" in model_id:
                return "Llama 3 70B"
            elif "8b" in model_id:
                return "Llama 3 8B"
            else:
                return "Llama 3"
        elif "llama-2" in model_id:
            if "70b" in model_id:
                return "Llama 2 70B"
            elif "13b" in model_id:
                return "Llama 2 13B"
            else:
                return "Llama 2"
        else:
            return "Llama"
    elif "mistral" in model_id:
        if "mixtral" in model_id.lower():
            return "Mixtral"
        else:
            return "Mistral"
    elif "cohere" in model_id:
        if "command" in model_id.lower():
            if "light" in model_id.lower():
                return "Cohere Command Light"
            else:
                return "Cohere Command"
        else:
            return "Cohere"
    
    # If no specific pattern matches, return the model ID
    return model_id

def list_bedrock_models(filter_text_modality=True, filter_on_demand=True, filter_cross_region=True) -> List[Dict[str, Any]]:
    """
    List available Bedrock foundation models with optional filtering.
    
    Args:
        filter_text_modality: If True, only return models with text output modality
        filter_on_demand: If True, only return models with on-demand inference
        filter_cross_region: If True, only return models that have a cross-region inference profile
        
    Returns:
        List of model information dictionaries
    """
    try:
        # Create a Bedrock client
        bedrock_client = boto3.client('bedrock')
        
        # List foundation models
        response = bedrock_client.list_foundation_models()
        models = response.get('modelSummaries', [])
        
        # Get cross-region profiles if needed
        cross_region_profiles = {}
        if filter_cross_region:
            cross_region_profiles = get_cross_region_inference_profiles()
        
        # Apply filters if requested
        filtered_models = []
        for model in models:
            # Check if model has text output modality
            has_text_modality = False
            if not filter_text_modality:
                has_text_modality = True
            else:
                output_modalities = model.get('outputModalities', [])
                if 'TEXT' in output_modalities:
                    has_text_modality = True
            
            # Check if model has on-demand inference
            has_on_demand = False
            if not filter_on_demand:
                has_on_demand = True
            else:
                inference_types = model.get('inferenceTypesSupported', [])
                if 'ON_DEMAND' in inference_types:
                    has_on_demand = True
            
            # Get the model ID
            model_id = model.get('modelId', '')
            
            # Check if model has a cross-region profile
            has_cross_region = False
            if not filter_cross_region:
                has_cross_region = True
            else:
                if model_id in cross_region_profiles:
                    has_cross_region = True
            
            
            # Add model to filtered list if it meets all criteria
            if has_text_modality and has_on_demand and has_cross_region:
                filtered_models.append({
                    'modelId': model_id,
                    'modelName': model.get('modelName'),
                    'provider': model.get('providerName'),
                    'outputModalities': model.get('outputModalities', []),
                    'inferenceTypes': model.get('inferenceTypesSupported', []),
                    'crossRegionProfile': cross_region_profiles.get(model_id, '')
                })
        
        return filtered_models
    
    except Exception as e:
        print(f"Error listing Bedrock models: {str(e)}")
        return []

def get_cross_region_inference_profiles() -> Dict[str, str]:
    """
    Get a mapping of model IDs to their cross-region inference profiles.
    
    Returns:
        Dictionary mapping base model IDs to their cross-region profile IDs
    """
    try:
        # Create a Bedrock client
        bedrock_client = boto3.client('bedrock')
        
        # Call the list_inference_profiles API
        response = bedrock_client.list_inference_profiles()
        
        profiles = response.get('inferenceProfileSummaries', [])
        
        # Create a mapping of base model IDs to cross-region profile IDs
        model_to_profile_map = {}
        
        for profile in profiles:
            # Get the inference profile ID
            profile_id = profile.get('inferenceProfileId', '')
            
            # Extract model IDs from the associated models
            associated_models = profile.get('models', [])
            
            for model in associated_models:
                # Extract the model ID from the ARN
                model_arn = model.get('modelArn', '')
                
                if model_arn and 'foundation-model/' in model_arn:
                    # Extract the model ID from the ARN (part after 'foundation-model/')
                    base_model_id = model_arn.split('foundation-model/')[1]
                    
                    # Add to the mapping
                    if base_model_id and profile_id:
                        model_to_profile_map[base_model_id] = profile_id
                
        return model_to_profile_map
    
    except Exception as e:
        print(f"Error listing inference profiles: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}

def get_model_with_cross_region_profile(model_id: str) -> str:
    """
    Get the appropriate model ID to use, considering cross-region profiles.
    
    Args:
        model_id: The base model ID
        
    Returns:
        Either the cross-region profile ID if available, or the original model ID
    """
    # Get the mapping of model IDs to cross-region profiles
    profile_map = get_cross_region_inference_profiles()
    
    # Return the cross-region profile if available, otherwise return the original model ID
    return profile_map.get(model_id, model_id)

def get_default_model_id() -> str:
    """
    Get the default Bedrock model ID.
    
    Returns:
        String containing the default model ID
    """
    # Use the same default as in the Bedrock model implementation
    from strands.models.bedrock import DEFAULT_BEDROCK_MODEL_ID
    return DEFAULT_BEDROCK_MODEL_ID

def get_default_model_info() -> Dict[str, str]:
    """
    Get the default Bedrock model ID and its display name.
    
    Returns:
        Dictionary containing the default model ID and display name
    """
    model_id = get_default_model_id()
    display_name = get_model_display_name(model_id)
    return {
        "id": model_id,
        "name": display_name
    }
