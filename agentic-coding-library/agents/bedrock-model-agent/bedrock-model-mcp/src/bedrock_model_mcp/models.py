"""Bedrock model listing functions."""
from concurrent.futures import ThreadPoolExecutor
import boto3
from functools import lru_cache
from typing import List, Dict, Optional, Union


@lru_cache(maxsize=1)
def _get_bedrock_regions() -> List[str]:
    """Get regions where Bedrock is available for the current account."""
    ec2 = boto3.client('ec2')
    all_regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
    
    def check_bedrock(region):
        try:
            client = boto3.client('bedrock', region_name=region)
            client.list_foundation_models()
            return region
        except:
            return None
    
    with ThreadPoolExecutor(max_workers=min(len(all_regions), 10)) as executor:
        results = list(executor.map(check_bedrock, all_regions))
    bedrock_regions = [r for r in results if r]
    return bedrock_regions


def _resolve_regions(regions: Union[str, List[str]]) -> List[str]:
    """Resolve region input to list of regions. 'any' expands to all Bedrock regions."""
    if isinstance(regions, str):
        regions = [regions]
    if 'any' in [r.lower() for r in regions]:
        return _get_bedrock_regions()
    return regions


def _run_parallel(func, regions: List[str], **kwargs) -> List[Dict]:
    """Run a function across multiple regions in parallel, returning results with region info."""
    if not regions:
        return []
    
    def run_in_region(region):
        try:
            results = func(region=region, **kwargs)
            return [{'region': region, **r} if isinstance(r, dict) else {'region': region, 'value': r} for r in results]
        except Exception as e:
            return [{'region': region, 'error': str(e)}]
    
    with ThreadPoolExecutor(max_workers=min(len(regions), 10)) as executor:
        all_results = list(executor.map(run_in_region, regions))
    return [item for sublist in all_results for item in sublist]


def _get_providers_single(region: str) -> List[str]:
    client = boto3.client('bedrock', region_name=region)
    models = client.list_foundation_models()['modelSummaries']
    return sorted(set(model['providerName'] for model in models))


def get_model_providers(regions: Union[str, List[str]] = 'us-east-1') -> List[Dict]:
    """Get unique list of model providers. Use 'any' to query all Bedrock regions."""
    regions = _resolve_regions(regions)
    if len(regions) == 1:
        return [{'region': regions[0], 'value': p} for p in _get_providers_single(regions[0])]
    return _run_parallel(lambda region: _get_providers_single(region), regions)


def _list_profiles_single(
    region: str,
    type_filter: Optional[str] = None,
    model_id_contains: Optional[str] = None,
) -> List[Dict]:
    client = boto3.client('bedrock', region_name=region)
    kwargs = {}
    if type_filter:
        kwargs['typeEquals'] = type_filter
    paginator = client.get_paginator('list_inference_profiles')
    profiles = []
    for page in paginator.paginate(**kwargs):
        profiles.extend(page['inferenceProfileSummaries'])
    if model_id_contains:
        profiles = [p for p in profiles if model_id_contains.lower() in p.get('inferenceProfileId', '').lower()]
    return profiles


def list_inference_profiles(
    regions: Union[str, List[str]] = 'us-east-1',
    type_filter: Optional[str] = None,
    model_id_contains: Optional[str] = None,
) -> List[Dict]:
    """
    List inference profiles. Use 'any' to query all Bedrock regions in parallel.
    
    Args:
        regions: AWS region(s) or 'any' for all regions (default: us-east-1)
        type_filter: Filter by profile type ('SYSTEM_DEFINED', 'APPLICATION') [API filter]
        model_id_contains: Filter profiles whose ID contains this substring [client-side]
    
    Returns:
        List of inference profile summaries with region info
    """
    regions = _resolve_regions(regions)
    if len(regions) == 1:
        return [{'region': regions[0], **p} for p in _list_profiles_single(regions[0], type_filter, model_id_contains)]
    return _run_parallel(
        lambda region: _list_profiles_single(region, type_filter, model_id_contains),
        regions
    )


def _search_models_single(
    region: str,
    provider: Optional[str] = None,
    inference_type: Optional[str] = None,
    input_modality: Optional[str] = None,
    output_modality: Optional[str] = None,
    customization_type: Optional[str] = None,
    inference_profile_only: bool = False,
    exclude_inference_profile_only: bool = False,
    status: Optional[str] = None,
    model_id_contains: Optional[str] = None,
) -> List[Dict]:
    client = boto3.client('bedrock', region_name=region)
    kwargs = {}
    if provider:
        kwargs['byProvider'] = provider
    if inference_type:
        kwargs['byInferenceType'] = inference_type
    if output_modality:
        kwargs['byOutputModality'] = output_modality
    if customization_type:
        kwargs['byCustomizationType'] = customization_type
    models = client.list_foundation_models(**kwargs)['modelSummaries']
    if input_modality:
        models = [m for m in models if input_modality in m.get('inputModalities', [])]
    if inference_profile_only:
        models = [m for m in models if m.get('inferenceTypesSupported') == ['INFERENCE_PROFILE']]
    if exclude_inference_profile_only:
        models = [m for m in models if m.get('inferenceTypesSupported') != ['INFERENCE_PROFILE']]
    if status:
        models = [m for m in models if m.get('modelLifecycle', {}).get('status') == status]
    if model_id_contains:
        models = [m for m in models if model_id_contains.lower() in m.get('modelId', '').lower()]
    
    # Auto-fetch inference profiles for models that only support inference profiles
    for model in models:
        if model.get('inferenceTypesSupported') == ['INFERENCE_PROFILE']:
            model_id = model.get('modelId', '')
            profiles = _list_profiles_single(region, model_id_contains=model_id)
            model['inference_profiles'] = profiles
    
    return models


def search_models(
    regions: Union[str, List[str]] = 'us-east-1',
    provider: Optional[str] = None,
    inference_type: Optional[str] = None,
    input_modality: Optional[str] = None,
    output_modality: Optional[str] = None,
    customization_type: Optional[str] = None,
    inference_profile_only: bool = False,
    exclude_inference_profile_only: bool = False,
    status: Optional[str] = None,
    model_id_contains: Optional[str] = None,
) -> List[Dict]:
    """
    Search and filter Bedrock foundation models. Use 'any' to query all Bedrock regions in parallel.
    
    Automatically fetches inference profiles for models that only support INFERENCE_PROFILE.
    
    Args:
        regions: AWS region(s) or 'any' for all regions (default: us-east-1)
        provider: Filter by provider name (e.g., 'Anthropic', 'Amazon', 'Meta') [API filter]
        inference_type: Filter by inference type ('ON_DEMAND', 'PROVISIONED') [API filter]
        input_modality: Filter by input modality ('TEXT', 'IMAGE', 'VIDEO', 'AUDIO') [client-side]
        output_modality: Filter by output modality ('TEXT', 'IMAGE', 'EMBEDDING') [API filter]
        customization_type: Filter by customization ('FINE_TUNING', 'CONTINUED_PRE_TRAINING', 'DISTILLATION') [API filter]
        inference_profile_only: If True, return only models that require inference profiles [client-side]
        exclude_inference_profile_only: If True, exclude models that only support inference profiles [client-side]
        status: Filter by lifecycle status ('ACTIVE', 'LEGACY') [client-side]
        model_id_contains: Filter models whose ID contains this substring [client-side]
    
    Returns:
        List of model summaries with region info. Models with only inference profile support
        include an 'inference_profiles' field with available profiles.
    """
    regions = _resolve_regions(regions)
    if len(regions) == 1:
        return [{'region': regions[0], **m} for m in _search_models_single(
            regions[0], provider, inference_type, input_modality, output_modality,
            customization_type, inference_profile_only, exclude_inference_profile_only, status, model_id_contains
        )]
    return _run_parallel(
        lambda region: _search_models_single(
            region, provider, inference_type, input_modality, output_modality,
            customization_type, inference_profile_only, exclude_inference_profile_only, status, model_id_contains
        ),
        regions
    )
