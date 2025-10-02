#!/usr/bin/env python3

import bedrock_models

def test_bedrock_models():
    print("Testing Bedrock Models and Cross-Region Profiles")
    print("=" * 50)
    
    # Get all available models
    print("Retrieving available Bedrock models...")
    models = bedrock_models.list_bedrock_models()
    
    if not models:
        print("No models found. Check your AWS credentials and region settings.")
        return
    
    print(f"Found {len(models)} models.")
    print()
    
    # Get cross-region profiles
    print("Retrieving cross-region inference profiles...")
    try:
        profiles = bedrock_models.get_cross_region_inference_profiles()
        print(f"Found {len(profiles)} cross-region profiles.")
        if profiles:
            print("Profiles found:")
            for base_id, profile_id in profiles.items():
                print(f"  Base: {base_id} -> Profile: {profile_id}")
        else:
            print("No profiles found. This is normal if your AWS region doesn't have cross-region profiles configured.")
    except Exception as e:
        print(f"Error retrieving profiles: {str(e)}")
    print()
    
    # Print model information with cross-region profiles
    print("Model Information with Cross-Region Profiles:")
    print("-" * 50)
    print(f"{'Model ID':<60} | {'Display Name':<25} | {'Cross-Region Profile':<60}")
    print("-" * 150)
    
    for model in models:
        model_id = model['modelId']
        display_name = bedrock_models.get_model_display_name(model_id)
        cross_region_id = bedrock_models.get_model_with_cross_region_profile(model_id)
        
        # Check if a cross-region profile was found
        has_cross_region = cross_region_id != model_id
        cross_region_display = cross_region_id if has_cross_region else "No cross-region profile"
        
        print(f"{model_id:<60} | {display_name:<25} | {cross_region_display:<60}")
    
    print("-" * 150)
    print()
    
    # Test with default model
    print("Testing with default model:")
    default_model = bedrock_models.get_default_model_id()
    default_display = bedrock_models.get_model_display_name(default_model)
    default_cross_region = bedrock_models.get_model_with_cross_region_profile(default_model)
    
    print(f"Default Model ID: {default_model}")
    print(f"Default Display Name: {default_display}")
    print(f"Cross-Region Profile: {default_cross_region}")
    
    # Check if default model has a cross-region profile
    if default_cross_region != default_model:
        print("Default model has a cross-region profile.")
    else:
        print("Default model does not have a cross-region profile.")

if __name__ == "__main__":
    test_bedrock_models()
