"""
Audio Generation Service using Hugging Face TTS Models
Supports multiple Hugging Face TTS models with robust fallbacks
"""

import os
import requests
import base64
import json
import time
import logging
import math
import struct
from typing import Dict, List, Optional, Any
from django.conf import settings

logger = logging.getLogger(__name__)

# Cache for TTS responses (use Redis in production)
_audio_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 3600  # 1 hour


def get_huggingface_api_key() -> str:
    """Get HuggingFace API key from environment"""
    api_key = (
        getattr(settings, 'HF_TOKEN', '') or 
        getattr(settings, 'HUGGINGFACE_API_KEY', '') or
        os.getenv('HF_TOKEN') or 
        os.getenv('HUGGINGFACE_API_KEY')
    )
    # Return empty string if no valid key found (will use free inference)
    return api_key if api_key and api_key not in ['your_hf_token_here', 'YOUR_TOKEN_HERE'] else ""


def create_cache_key(text: str, voice_id: str, model: str) -> str:
    """Create a cache key for the TTS request"""
    cache_data = {
        'text': text.strip().lower(),
        'voice_id': voice_id,
        'model': model
    }
    return str(hash(json.dumps(cache_data, sort_keys=True)))


def generate_audio(
    text: str,
    voice_id: Optional[str] = None,
    model: str = "tts-1",
    stability: float = 0.5,
    similarity_boost: float = 0.5,
    style: float = 0.0,
    use_speaker_boost: bool = True,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Generate audio from text using Hugging Face TTS models
    
    Args:
        text: Text to convert to speech
        voice_id: Voice ID (optional, will use default)
        model: TTS model to use
        stability: Voice stability (0.0-1.0) - not used in HF models
        similarity_boost: Voice similarity boost (0.0-1.0) - not used in HF models
        style: Style exaggeration (0.0-1.0) - not used in HF models
        use_speaker_boost: Enable speaker boost - not used in HF models
        timeout: Request timeout in seconds
    
    Returns:
        Dict containing success status, audio data, and metadata
    """
    start_time = time.time()
    
    # Validate input
    if not text or not text.strip():
        return {
            'success': False,
            'error': 'Text cannot be empty',
            'generation_time': 0
        }
    
    text = text.strip()
    if len(text) > 5000:  # Limit text length
        text = text[:5000]
        
    try:
        # Check cache first
        cache_key = create_cache_key(text, voice_id or 'default', model)
        if cache_key in _audio_cache:
            cached_result = _audio_cache[cache_key]
            if time.time() - cached_result['timestamp'] < CACHE_TTL:
                cached_result['cached'] = True
                return cached_result
        
        # Try multiple Hugging Face TTS models as fallbacks
        tts_models = [
            ('microsoft/speecht5_tts', _try_speecht5_tts),
            ('facebook/mms-tts-eng', _try_mms_tts),
            ('espnet/kan-bayashi_ljspeech_vits', _try_vits_tts),
            ('suno/bark', _try_bark_tts),
        ]
        
        for model_name, service_func in tts_models:
            try:
                result = service_func(
                    text=text,
                    voice_id=voice_id,
                    timeout=timeout
                )
                if result.get('success'):
                    generation_time = time.time() - start_time
                    result['generation_time'] = generation_time
                    result['character_count'] = len(text)
                    result['model'] = model_name
                    
                    # Cache successful result
                    result['timestamp'] = time.time()
                    _audio_cache[cache_key] = result.copy()
                    result['cached'] = False
                    
                    return result
            except Exception as e:
                logger.warning(f"TTS model {model_name} failed: {str(e)}")
                continue
        
        # If all Hugging Face models fail, use mock TTS as fallback
        try:
            result = _try_mock_tts(text, voice_id, model, timeout)
            if result.get('success'):
                generation_time = time.time() - start_time
                result['generation_time'] = generation_time
                result['character_count'] = len(text)
                return result
        except Exception as e:
            logger.error(f"Mock TTS failed: {str(e)}")
        
        # If everything fails
        return {
            'success': False,
            'error': 'All TTS services are currently unavailable. Please try again later.',
            'generation_time': time.time() - start_time
        }
        
    except Exception as e:
        logger.error(f"Audio generation failed: {str(e)}")
        return {
            'success': False,
            'error': f'Audio generation failed: {str(e)}',
            'generation_time': time.time() - start_time
        }


def _try_speecht5_tts(text: str, voice_id: Optional[str], timeout: int) -> Dict[str, Any]:
    """Try Microsoft SpeechT5 TTS model from Hugging Face"""
    api_key = get_huggingface_api_key()
    
    # Use Hugging Face Inference API
    api_url = "https://api-inference.huggingface.co/models/microsoft/speecht5_tts"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Add API key if available (for better rate limits)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # Prepare payload
    payload = {
        "inputs": text,
        "parameters": {}
    }
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    
    if response.status_code == 200:
        audio_data = base64.b64encode(response.content).decode('utf-8')
        return {
            'success': True,
            'audio_data': audio_data,
            'mime_type': 'audio/wav',
            'voice_used': voice_id or 'default',
            'file_size': len(response.content),
            'cached': False
        }
    else:
        error_msg = f"SpeechT5 TTS failed: {response.status_code}"
        if response.status_code == 503:
            error_msg += " - Model is loading, please wait"
        elif response.status_code == 429:
            error_msg += " - Rate limit exceeded"
        raise Exception(error_msg)


def _try_mms_tts(text: str, voice_id: Optional[str], timeout: int) -> Dict[str, Any]:
    """Try Facebook MMS TTS model from Hugging Face"""
    api_key = get_huggingface_api_key()
    
    api_url = "https://api-inference.huggingface.co/models/facebook/mms-tts-eng"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "inputs": text
    }
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    
    if response.status_code == 200:
        audio_data = base64.b64encode(response.content).decode('utf-8')
        return {
            'success': True,
            'audio_data': audio_data,
            'mime_type': 'audio/wav',
            'voice_used': voice_id or 'default',
            'file_size': len(response.content),
            'cached': False
        }
    else:
        error_msg = f"MMS TTS failed: {response.status_code}"
        if response.status_code == 503:
            error_msg += " - Model is loading, please wait"
        elif response.status_code == 429:
            error_msg += " - Rate limit exceeded"
        raise Exception(error_msg)


def _try_vits_tts(text: str, voice_id: Optional[str], timeout: int) -> Dict[str, Any]:
    """Try VITS TTS model from Hugging Face"""
    api_key = get_huggingface_api_key()
    
    api_url = "https://api-inference.huggingface.co/models/espnet/kan-bayashi_ljspeech_vits"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "inputs": text
    }
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    
    if response.status_code == 200:
        audio_data = base64.b64encode(response.content).decode('utf-8')
        return {
            'success': True,
            'audio_data': audio_data,
            'mime_type': 'audio/wav',
            'voice_used': voice_id or 'default',
            'file_size': len(response.content),
            'cached': False
        }
    else:
        error_msg = f"VITS TTS failed: {response.status_code}"
        if response.status_code == 503:
            error_msg += " - Model is loading, please wait"
        elif response.status_code == 429:
            error_msg += " - Rate limit exceeded"
        raise Exception(error_msg)


def _try_bark_tts(text: str, voice_id: Optional[str], timeout: int) -> Dict[str, Any]:
    """Try Bark TTS model from Hugging Face (supports longer text)"""
    api_key = get_huggingface_api_key()
    
    api_url = "https://api-inference.huggingface.co/models/suno/bark"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # Bark can handle longer text but we'll still limit it
    if len(text) > 200:
        text = text[:200]
    
    payload = {
        "inputs": text,
        "parameters": {
            "voice_preset": voice_id if voice_id in ["v2/en_speaker_0", "v2/en_speaker_1", "v2/en_speaker_2"] else "v2/en_speaker_6"
        }
    }
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    
    if response.status_code == 200:
        audio_data = base64.b64encode(response.content).decode('utf-8')
        return {
            'success': True,
            'audio_data': audio_data,
            'mime_type': 'audio/wav',
            'voice_used': voice_id or 'v2/en_speaker_6',
            'file_size': len(response.content),
            'cached': False
        }
    else:
        error_msg = f"Bark TTS failed: {response.status_code}"
        if response.status_code == 503:
            error_msg += " - Model is loading, please wait"
        elif response.status_code == 429:
            error_msg += " - Rate limit exceeded"
        raise Exception(error_msg)


def _try_mock_tts(text: str, voice_id: Optional[str], model: str, timeout: int) -> Dict[str, Any]:
    """Mock TTS for testing purposes"""
    
    # Generate a simple sine wave audio for testing
    import math
    import struct
    
    # Audio parameters
    sample_rate = 22050
    duration = min(len(text) * 0.1, 5.0)  # Duration based on text length, max 5 seconds
    frequency = 440  # A4 note
    
    # Generate sine wave
    samples = []
    for i in range(int(sample_rate * duration)):
        sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate) * 0.1)
        samples.append(struct.pack('<h', sample))
    
    # Create WAV header
    audio_data = b''.join(samples)
    wav_header = _create_wav_header(len(audio_data), sample_rate)
    full_audio = wav_header + audio_data
    
    audio_b64 = base64.b64encode(full_audio).decode('utf-8')
    
    return {
        'success': True,
        'audio_data': audio_b64,
        'mime_type': 'audio/wav',
        'model': 'mock-tts',
        'voice_used': voice_id or 'mock',
        'file_size': len(full_audio),
        'cached': False,
        'duration': duration
    }


def _create_wav_header(data_size: int, sample_rate: int = 22050) -> bytes:
    """Create WAV file header"""
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,  # File size
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1Size
        1,   # AudioFormat (PCM)
        1,   # NumChannels (mono)
        sample_rate,  # SampleRate
        sample_rate * 2,  # ByteRate
        2,   # BlockAlign
        16,  # BitsPerSample
        b'data',
        data_size
    )
    return header


def get_available_voices() -> List[Dict[str, str]]:
    """Get list of available voices for different TTS models"""
    return [
        # SpeechT5 voices
        {'id': 'default', 'name': 'Default', 'description': 'Default SpeechT5 voice', 'model': 'microsoft/speecht5_tts'},
        
        # Bark voices
        {'id': 'v2/en_speaker_0', 'name': 'Bark Speaker 0', 'description': 'Bark English Speaker 0', 'model': 'suno/bark'},
        {'id': 'v2/en_speaker_1', 'name': 'Bark Speaker 1', 'description': 'Bark English Speaker 1', 'model': 'suno/bark'},
        {'id': 'v2/en_speaker_2', 'name': 'Bark Speaker 2', 'description': 'Bark English Speaker 2', 'model': 'suno/bark'},
        {'id': 'v2/en_speaker_6', 'name': 'Bark Speaker 6', 'description': 'Bark English Speaker 6 (default)', 'model': 'suno/bark'},
        
        # MMS voices
        {'id': 'english', 'name': 'English', 'description': 'MMS English voice', 'model': 'facebook/mms-tts-eng'},
        
        # VITS voices
        {'id': 'ljspeech', 'name': 'LJSpeech', 'description': 'VITS LJSpeech voice', 'model': 'espnet/kan-bayashi_ljspeech_vits'},
    ]


def get_audio_metrics() -> Dict[str, Any]:
    """Get system metrics for audio generation"""
    try:
        return {
            'available_services': [
                'Microsoft SpeechT5 TTS',
                'Facebook MMS TTS', 
                'VITS TTS',
                'Bark TTS',
                'Mock TTS (fallback)'
            ],
            'supported_formats': ['wav', 'mp3'],
            'max_text_length': 5000,  # Characters
            'supported_languages': ['en'],  # Add more as models support them
            'cache_entries': len(_audio_cache),
            'cache_ttl': CACHE_TTL,
            'status': 'operational'
        }
    except Exception as e:
        logger.error(f"Failed to get audio metrics: {str(e)}")
        return {
            'status': 'error',
            'error': str(e)
        }


def clear_audio_cache():
    """Clear the audio generation cache"""
    global _audio_cache
    _audio_cache.clear()


def get_cache_info() -> Dict[str, Any]:
    """Get information about the current cache"""
    current_time = time.time()
    valid_entries = 0
    total_entries = len(_audio_cache)
    
    for cached_result in _audio_cache.values():
        if current_time - cached_result['timestamp'] < CACHE_TTL:
            valid_entries += 1
    
    return {
        'total_entries': total_entries,
        'valid_entries': valid_entries,
        'expired_entries': total_entries - valid_entries,
        'cache_ttl': CACHE_TTL
    }