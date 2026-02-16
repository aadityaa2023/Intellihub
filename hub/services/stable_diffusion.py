import os
import json
import time
import requests
from typing import Dict, Any, Optional, List
import base64

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Stable Diffusion API configurations
STABLE_DIFFUSION_API_URL = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
STABLE_DIFFUSION_UPSCALE_URL = "https://api.stability.ai/v1/generation/esrgan-v1-x2plus/image-to-image/upscale"

# Simple in-memory cache for responses (use Redis in production)
_image_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 3600  # 1 hour for images

# Metrics tracking
_image_metrics = {
    'attempts': 0,
    'successful_generations': 0,
    'errors_total': 0,
    'images_generated': 0,
    'last_generation_time': 0,
}

def get_stable_diffusion_api_key() -> str:
    """Get Stable Diffusion API key from environment"""
    api_key = os.getenv('STABLE_DIFFUSION_API_KEY')
    if not api_key:
        raise ValueError("STABLE_DIFFUSION_API_KEY not found in environment variables")
    return api_key

def create_cache_key(prompt: str, **kwargs) -> str:
    """Create a cache key for the image generation request"""
    cache_data = {
        'prompt': prompt.strip().lower(),
        **kwargs
    }
    return str(hash(json.dumps(cache_data, sort_keys=True)))

def generate_image(
    prompt: str,
    negative_prompt: Optional[str] = None,
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    cfg_scale: float = 7.0,
    samples: int = 1,
    style_preset: Optional[str] = None,
    seed: Optional[int] = None,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Generate an image using Stable Diffusion API
    
    Args:
        prompt: Text description of the image to generate
        negative_prompt: What to avoid in the image
        width: Image width (default: 1024)
        height: Image height (default: 1024)
        steps: Number of diffusion steps (10-50, default: 30)
        cfg_scale: How closely to follow prompt (1-35, default: 7.0)
        samples: Number of images to generate (1-10, default: 1)
        style_preset: Style preset to apply (optional)
        seed: Random seed for reproducible results (optional)
        use_cache: Whether to use cached results
        
    Returns:
        Dict containing image data and metadata
    """
    global _image_metrics
    _image_metrics['attempts'] += 1
    
    try:
        # Check cache first
        if use_cache:
            cache_key = create_cache_key(
                prompt, negative_prompt=negative_prompt, width=width, height=height,
                steps=steps, cfg_scale=cfg_scale, style_preset=style_preset, seed=seed
            )
            
            if cache_key in _image_cache:
                cached_result = _image_cache[cache_key]
                if time.time() - cached_result['timestamp'] < CACHE_TTL:
                    return {
                        **cached_result['result'],
                        'cached': True,
                        'generation_time': cached_result['result']['generation_time']
                    }
        
        api_key = get_stable_diffusion_api_key()
        
        # Prepare request payload
        payload = {
            "text_prompts": [
                {
                    "text": prompt,
                    "weight": 1.0
                }
            ],
            "cfg_scale": cfg_scale,
            "height": height,
            "width": width,
            "samples": samples,
            "steps": steps,
        }
        
        # Add optional parameters
        if negative_prompt:
            payload["text_prompts"].append({
                "text": negative_prompt,
                "weight": -1.0
            })
        
        if style_preset:
            payload["style_preset"] = style_preset
            
        if seed is not None:
            payload["seed"] = seed
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        start_time = time.time()
        
        # Make API request
        response = requests.post(
            STABLE_DIFFUSION_API_URL,
            headers=headers,
            json=payload,
            timeout=120  # 2 minutes timeout for image generation
        )
        
        generation_time = time.time() - start_time
        _image_metrics['last_generation_time'] = generation_time
        
        if response.status_code != 200:
            error_msg = f"Stable Diffusion API error: {response.status_code}"
            try:
                error_data = response.json()
                if 'message' in error_data:
                    error_msg += f" - {error_data['message']}"
            except:
                error_msg += f" - {response.text}"
            
            _image_metrics['errors_total'] += 1
            raise Exception(error_msg)
        
        # Parse response
        result_data = response.json()
        
        # Process generated images
        images = []
        for artifact in result_data.get('artifacts', []):
            if artifact.get('finishReason') == 'SUCCESS':
                images.append({
                    'base64': artifact['base64'],
                    'seed': artifact.get('seed'),
                    'finish_reason': artifact.get('finishReason')
                })
        
        if not images:
            _image_metrics['errors_total'] += 1
            raise Exception("No successful images generated")
        
        result = {
            'images': images,
            'prompt': prompt,
            'negative_prompt': negative_prompt,
            'parameters': {
                'width': width,
                'height': height,
                'steps': steps,
                'cfg_scale': cfg_scale,
                'samples': samples,
                'style_preset': style_preset,
                'seed': seed
            },
            'generation_time': generation_time,
            'cached': False,
            'model': 'stable-diffusion-xl-1024-v1-0'
        }
        
        # Cache the result
        if use_cache:
            _image_cache[cache_key] = {
                'result': result,
                'timestamp': time.time()
            }
        
        _image_metrics['successful_generations'] += 1
        _image_metrics['images_generated'] += len(images)
        
        return result
        
    except Exception as e:
        _image_metrics['errors_total'] += 1
        raise Exception(f"Image generation failed: {str(e)}")

def upscale_image(
    image_base64: str,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> Dict[str, Any]:
    """
    Upscale an image using Stable Diffusion's ESRGAN upscaler
    
    Args:
        image_base64: Base64 encoded image data
        width: Target width (optional, will be auto-calculated)
        height: Target height (optional, will be auto-calculated)
        
    Returns:
        Dict containing upscaled image data
    """
    try:
        api_key = get_stable_diffusion_api_key()
        
        # Prepare form data
        files = {
            'image': ('image.png', base64.b64decode(image_base64), 'image/png')
        }
        
        data = {}
        if width:
            data['width'] = width
        if height:
            data['height'] = height
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        
        start_time = time.time()
        
        response = requests.post(
            STABLE_DIFFUSION_UPSCALE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120
        )
        
        generation_time = time.time() - start_time
        
        if response.status_code != 200:
            error_msg = f"Upscale API error: {response.status_code}"
            try:
                error_data = response.json()
                if 'message' in error_data:
                    error_msg += f" - {error_data['message']}"
            except:
                error_msg += f" - {response.text}"
            raise Exception(error_msg)
        
        result_data = response.json()
        
        # Process upscaled image
        upscaled_images = []
        for artifact in result_data.get('artifacts', []):
            if artifact.get('finishReason') == 'SUCCESS':
                upscaled_images.append({
                    'base64': artifact['base64'],
                    'finish_reason': artifact.get('finishReason')
                })
        
        if not upscaled_images:
            raise Exception("No successful upscaled images generated")
        
        return {
            'images': upscaled_images,
            'generation_time': generation_time,
            'model': 'esrgan-v1-x2plus'
        }
        
    except Exception as e:
        raise Exception(f"Image upscaling failed: {str(e)}")

def get_available_style_presets() -> List[str]:
    """Get list of available style presets for Stable Diffusion"""
    return [
        "enhance",
        "anime",
        "photographic", 
        "digital-art",
        "comic-book",
        "fantasy-art",
        "line-art",
        "analog-film",
        "neon-punk",
        "isometric",
        "low-poly",
        "origami",
        "modeling-compound",
        "cinematic",
        "3d-model",
        "pixel-art",
        "tile-texture"
    ]

def get_image_metrics() -> Dict[str, Any]:
    """Get current image generation metrics"""
    return _image_metrics.copy()

def clear_image_cache() -> None:
    """Clear the image generation cache"""
    global _image_cache
    _image_cache.clear()

def save_image_to_file(base64_data: str, file_path: str) -> None:
    """Save base64 image data to a file"""
    try:
        image_data = base64.b64decode(base64_data)
        with open(file_path, 'wb') as f:
            f.write(image_data)
    except Exception as e:
        raise Exception(f"Failed to save image: {str(e)}")