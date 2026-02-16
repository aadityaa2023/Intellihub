"""
Presentation Generation Service
Handles AI-powered presentation creation using multiple AI providers
"""
import json
import time
import base64
import requests
import logging
from typing import Dict, List, Optional, Tuple
from django.conf import settings
import os

from .gemini import generate_gemini_response
from .openrouter import generate_response as openrouter_generate

# Configure logger
logger = logging.getLogger(__name__)


class PresentationGeneratorService:
    """Service for AI-powered presentation generation"""
    
    def __init__(self):
        # Get both API keys for maximum availability
        self.gemini_new_key = os.getenv('GEMINI_NEW_API_KEY')
        self.gemini_old_key = os.getenv('GEMINI_API_KEY')
        self.openrouter_keys = os.getenv('OPENROUTER_API_KEYS', '').split(',')
        
        # Track which keys are available
        self.has_gemini_new = self.gemini_new_key is not None
        self.has_gemini_old = self.gemini_old_key is not None
        self.gemini_available = self.has_gemini_new or self.has_gemini_old
        self.openrouter_available = len([k for k in self.openrouter_keys if k.strip()]) > 0
        
        # Strategy: Try both keys with lower-tier models for better quota
        self.api_key_rotation = []
        if self.has_gemini_new:
            self.api_key_rotation.append(('new', 'GEMINI_NEW_API_KEY'))
        if self.has_gemini_old:
            self.api_key_rotation.append(('old', 'GEMINI_API_KEY'))
        
        # Log API availability
        logger.info(f"Presentation service initialized: NEW_KEY={self.has_gemini_new}, OLD_KEY={self.has_gemini_old}, OR_KEYS={len(self.openrouter_keys)}")
        
    def _try_gemini_with_fallback(self, prompt: str, temperature: float = 0.7) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Try Gemini API with both keys and lower-tier models for maximum success rate
        Returns: (response, model_info) or (None, None)
        """
        # Use lower-tier models with better quota: 1.5-flash is more stable than 2.x models
        models_to_try = [
            'gemini-1.5-flash',      # Most stable, best quota
            'gemini-1.5-flash-8b',   # Lighter version
            'gemini-1.5-pro',        # Fallback to pro if flash fails
        ]
        
        # Try each API key
        for key_type, key_name in self.api_key_rotation:
            use_new_key = (key_type == 'new')
            
            for model in models_to_try:
                try:
                    logger.info(f"Trying {key_name} with {model}")
                    response = generate_gemini_response(
                        prompt,
                        model=model,
                        use_new_key=use_new_key,
                        temperature=temperature
                    )
                    model_info = f"{model} ({key_name})"
                    logger.info(f"✓ Success with {model_info}")
                    return response, model_info
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.warning(f"✗ Failed {key_name}/{model}: {error_msg[:100]}")
                    
                    # If quota exceeded on one key, try the other key immediately
                    if '429' in error_msg or 'quota' in error_msg.lower():
                        logger.info(f"Quota exceeded on {key_name}, will try other keys...")
                        break  # Move to next key
                    # For other errors, continue trying models with same key
                    continue
        
        return None, None
    
    def generate_presentation_outline(self, topic: str, slide_count: int = 10, 
                                    target_audience: str = None, 
                                    presentation_type: str = 'business',
                                    tone: str = 'professional') -> Dict:
        """
        Generate a structured presentation outline with dual-key fallback strategy
        """
        try:
            prompt = self._build_outline_prompt(
                topic, slide_count, target_audience, presentation_type, tone
            )
            
            start_time = time.time()
            logger.info(f"Generating outline for: {topic}")
            
            # Try Gemini with both API keys and lower-tier models
            response, model_info = self._try_gemini_with_fallback(prompt, temperature=0.7)
            
            if response:
                # Extract text from response
                response_text = response.get('text', '') or response.get('content', '') or response.get('assistant_text', '') or str(response)
                outline = self._parse_outline_response(response_text)
                generation_time = time.time() - start_time
                
                logger.info(f"✓ Outline generated with {model_info} in {generation_time:.2f}s")
                return {
                    'success': True,
                    'outline': outline,
                    'generation_time': generation_time,
                    'model_used': model_info,
                    'raw_response': response
                }
            
            # Fallback to OpenRouter if Gemini exhausted
            if self.openrouter_available:
                logger.info("Trying OpenRouter as final fallback...")
                try:
                    response = openrouter_generate(prompt, model="anthropic/claude-3-haiku")
                    response_text = response.get('assistant_text', '') if isinstance(response, dict) else str(response)
                    outline = self._parse_outline_response(response_text)
                    generation_time = time.time() - start_time
                    
                    logger.info(f"✓ Outline generated with OpenRouter in {generation_time:.2f}s")
                    return {
                        'success': True,
                        'outline': outline,
                        'generation_time': generation_time,
                        'model_used': 'claude-3-haiku (OpenRouter)',
                        'raw_response': response
                    }
                except Exception as e:
                    logger.error(f"OpenRouter failed: {e}")
            
            # All providers failed
            raise Exception("All AI providers failed (Gemini quota exceeded, OpenRouter unavailable)")
            
        except Exception as e:
            logger.error(f"Outline generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'generation_time': 0,
                'model_used': None
            }
    
    def generate_slide_content(self, slide_title: str, slide_type: str,
                             presentation_context: str, tone: str = 'professional') -> Dict:
        """
        Generate detailed content for a specific slide with dual-key fallback
        """
        try:
            prompt = self._build_slide_content_prompt(
                slide_title, slide_type, presentation_context, tone
            )
            
            start_time = time.time()
            logger.info(f"Generating content for slide: {slide_title}")
            
            # Try Gemini with both API keys
            response, model_info = self._try_gemini_with_fallback(prompt, temperature=0.7)
            
            if response:
                content = self._parse_slide_content_response(response)
                generation_time = time.time() - start_time
                
                logger.info(f"✓ Slide content generated with {model_info} in {generation_time:.2f}s")
                return {
                    'success': True,
                    'content': content,
                    'generation_time': generation_time,
                    'model_used': model_info
                }
            
            # Fallback to OpenRouter
            if self.openrouter_available:
                logger.info("Trying OpenRouter for slide content...")
                try:
                    response = openrouter_generate(prompt, model="anthropic/claude-3-haiku")
                    content = self._parse_slide_content_response(response)
                    generation_time = time.time() - start_time
                    
                    return {
                        'success': True,
                        'content': content,
                        'generation_time': generation_time,
                        'model_used': 'claude-3-haiku (OpenRouter)'
                    }
                except Exception as e:
                    logger.error(f"OpenRouter failed for slide content: {e}")
            
            raise Exception("Failed to generate slide content - all providers exhausted")
            
        except Exception as e:
            logger.error(f"Slide content generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'generation_time': 0
            }
    
    def generate_chart_data(self, chart_type: str, topic: str, 
                          context: str = "") -> Dict:
        """
        Generate data for charts and graphs with dual-key fallback
        """
        try:
            prompt = f"""
            Generate realistic data for a {chart_type} chart about "{topic}".
            Context: {context}
            
            Return data in JSON format suitable for Chart.js with:
            - labels: array of labels
            - datasets: array with data, backgroundColor, borderColor
            - title: chart title
            - type: chart type
            
            Make the data realistic and relevant to the topic.
            """
            
            start_time = time.time()
            logger.info(f"Generating chart data: {chart_type} for {topic}")
            
            # Try Gemini with both API keys
            response, model_info = self._try_gemini_with_fallback(prompt, temperature=0.5)
            
            if response:
                chart_data = self._extract_json_from_response(response)
                generation_time = time.time() - start_time
                
                logger.info(f"✓ Chart data generated with {model_info}")
                return {
                    'success': True,
                    'chart_data': chart_data,
                    'generation_time': generation_time
                }
            
            # Fallback to OpenRouter
            if self.openrouter_available:
                logger.info("Trying OpenRouter for chart data...")
                try:
                    response = openrouter_generate(prompt)
                    chart_data = self._extract_json_from_response(response)
                    generation_time = time.time() - start_time
                    
                    return {
                        'success': True,
                        'chart_data': chart_data,
                        'generation_time': generation_time
                    }
                except Exception as e:
                    logger.error(f"OpenRouter failed for chart data: {e}")
            
            raise Exception("Failed to generate chart data - all providers exhausted")
            
        except Exception as e:
            logger.error(f"Chart data generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'chart_data': None
            }
    
    def enhance_slide_content(self, current_content: str, 
                            enhancement_type: str = 'improve') -> Dict:
        """
        Enhance existing slide content with dual-key fallback
        """
        try:
            if enhancement_type == 'improve':
                prompt = f"""
                Improve the following slide content to make it more engaging and professional:
                
                Current content:
                {current_content}
                
                Provide improved version with:
                - Better structure and flow
                - More compelling language
                - Clear bullet points where appropriate
                - Professional tone
                
                Return only the improved content.
                """
            elif enhancement_type == 'simplify':
                prompt = f"""
                Simplify the following slide content to make it more concise and clear:
                
                Current content:
                {current_content}
                
                Provide simplified version with:
                - Shorter sentences
                - Key points only
                - Easy to understand language
                
                Return only the simplified content.
                """
            elif enhancement_type == 'expand':
                prompt = f"""
                Expand the following slide content with more details and examples:
                
                Current content:
                {current_content}
                
                Provide expanded version with:
                - More detailed explanations
                - Relevant examples
                - Supporting information
                
                Return only the expanded content.
                """
            else:
                raise ValueError("Invalid enhancement type")
            
            start_time = time.time()
            logger.info(f"Enhancing content: {enhancement_type}")
            
            # Try Gemini with both API keys
            response, model_info = self._try_gemini_with_fallback(prompt, temperature=0.6)
            
            if response:
                enhanced_text = response.get('text', '') or response.get('content', '') or str(response)
                generation_time = time.time() - start_time
                
                logger.info(f"✓ Content enhanced with {model_info}")
                return {
                    'success': True,
                    'enhanced_content': enhanced_text.strip(),
                    'generation_time': generation_time
                }
            
            # Fallback to OpenRouter
            if self.openrouter_available:
                logger.info("Trying OpenRouter for content enhancement...")
                try:
                    response = openrouter_generate(prompt)
                    enhanced_text = response.get('assistant_text', '') if isinstance(response, dict) else str(response)
                    generation_time = time.time() - start_time
                    
                    return {
                        'success': True,
                        'enhanced_content': enhanced_text.strip(),
                        'generation_time': generation_time
                    }
                except Exception as e:
                    logger.error(f"OpenRouter failed for enhancement: {e}")
            
            raise Exception("Failed to enhance content - all providers exhausted")
            
        except Exception as e:
            logger.error(f"Content enhancement failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'enhanced_content': current_content
            }
    
    def _build_outline_prompt(self, topic: str, slide_count: int,
                            target_audience: str, presentation_type: str,
                            tone: str) -> str:
        """Build prompt for presentation outline generation"""
        
        audience_text = f" for {target_audience}" if target_audience else ""
        
        prompt = f"""
        Create a comprehensive presentation outline for a {presentation_type} presentation about "{topic}"{audience_text}.
        
        Requirements:
        - Exactly {slide_count} slides
        - {tone.title()} tone throughout
        - Logical flow and structure
        - Engaging and informative content
        
        For each slide, provide:
        - Slide number
        - Slide title
        - Slide type (title, content, bullet_points, two_column, image_text, chart, quote, call_to_action, etc.)
        - Brief description of content
        - Key points to cover
        - Suggested layout
        
        Format the response as a structured outline that can be easily parsed.
        Start with slide 1 (title slide) and end with a conclusion or call-to-action slide.
        
        Example format:
        **Slide 1: Title Slide**
        - Type: title
        - Title: [Main Title]
        - Subtitle: [Subtitle or tagline]
        - Layout: centered
        
        **Slide 2: Introduction**
        - Type: content
        - Title: [Slide title]
        - Key Points:
          • Point 1
          • Point 2
        - Layout: default
        
        Continue for all {slide_count} slides...
        """
        
        return prompt
    
    def _build_slide_content_prompt(self, slide_title: str, slide_type: str,
                                  presentation_context: str, tone: str) -> str:
        """Build prompt for individual slide content generation"""
        
        prompt = f"""
        Generate detailed content for a presentation slide with the following specifications:
        
        Slide Title: {slide_title}
        Slide Type: {slide_type}
        Tone: {tone}
        Presentation Context: {presentation_context}
        
        Provide:
        1. Main content (body text)
        2. Bullet points (if applicable)
        3. Speaker notes
        4. Suggested visuals or images
        5. Call-to-action or next steps (if applicable)
        
        Make the content engaging, informative, and appropriate for the slide type.
        Keep text concise but meaningful for presentation slides.
        """
        
        return prompt
    
    def _parse_outline_response(self, response: str) -> List[Dict]:
        """Parse AI response to extract structured outline"""
        slides = []
        current_slide = None
        
        lines = response.split('\n')
        slide_number = 0
        
        for line in lines:
            line = line.strip()
            
            # Detect slide headers
            if line.startswith('**Slide ') or line.startswith('Slide ') or line.startswith('#'):
                if current_slide:
                    slides.append(current_slide)
                
                slide_number += 1
                current_slide = {
                    'slide_number': slide_number,
                    'title': '',
                    'subtitle': '',
                    'slide_type': 'content',
                    'layout': 'default',
                    'key_points': [],
                    'description': '',
                    'suggested_visuals': []
                }
                
                # Extract title from line
                if ':' in line:
                    title_part = line.split(':', 1)[1].strip()
                    current_slide['title'] = title_part.replace('**', '').replace('#', '').strip()
            
            elif current_slide:
                # Parse slide properties
                if line.startswith('- Type:'):
                    current_slide['slide_type'] = line.split(':', 1)[1].strip()
                elif line.startswith('- Title:'):
                    current_slide['title'] = line.split(':', 1)[1].strip()
                elif line.startswith('- Subtitle:'):
                    current_slide['subtitle'] = line.split(':', 1)[1].strip()
                elif line.startswith('- Layout:'):
                    current_slide['layout'] = line.split(':', 1)[1].strip()
                elif line.startswith('- Description:'):
                    current_slide['description'] = line.split(':', 1)[1].strip()
                elif line.startswith('  •') or line.startswith('  -'):
                    current_slide['key_points'].append(line[3:].strip())
                elif line.startswith('- Key Points:'):
                    # Next lines will be key points
                    continue
        
        # Add the last slide
        if current_slide:
            slides.append(current_slide)
        
        return slides
    
    def _parse_slide_content_response(self, response) -> Dict:
        """Parse AI response for slide content - handles both dict and string responses"""
        # Extract text from response if it's a dict
        if isinstance(response, dict):
            response_text = response.get('text', '') or response.get('content', '') or response.get('assistant_text', '') or str(response)
        else:
            response_text = str(response)
        
        content = {
            'main_content': '',
            'bullets': [],
            'speaker_notes': '',
            'suggested_visuals': [],
            'call_to_action': ''
        }
        
        sections = response_text.split('\n\n')
        current_section = 'main_content'
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
            
            if 'bullet points:' in section.lower() or 'key points:' in section.lower():
                current_section = 'bullets'
                continue
            elif 'speaker notes:' in section.lower() or 'notes:' in section.lower():
                current_section = 'speaker_notes'
                continue
            elif 'suggested visuals:' in section.lower() or 'images:' in section.lower():
                current_section = 'suggested_visuals'
                continue
            elif 'call to action:' in section.lower() or 'next steps:' in section.lower():
                current_section = 'call_to_action'
                continue
            
            if current_section == 'bullets':
                lines = section.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                        content['bullets'].append(line[1:].strip())
                    elif line and not any(marker in line.lower() for marker in ['bullet', 'points:', 'notes:']):
                        # Add non-empty lines that aren't section headers
                        content['bullets'].append(line)
            elif current_section == 'suggested_visuals':
                lines = section.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not 'suggested' in line.lower():
                        content['suggested_visuals'].append(line.strip('•-* '))
            else:
                if content[current_section]:
                    content[current_section] += '\n\n' + section
                else:
                    content[current_section] = section
        
        return content
    
    def _extract_json_from_response(self, response) -> Dict:
        """Extract JSON data from AI response - handles both dict and string responses"""
        # Extract text from response if it's a dict
        if isinstance(response, dict):
            response_text = response.get('text', '') or response.get('content', '') or response.get('assistant_text', '') or str(response)
        else:
            response_text = str(response)
        
        try:
            # Try to find JSON in the response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            
            if start != -1 and end > start:
                json_str = response_text[start:end]
                return json.loads(json_str)
            else:
                # Create a default chart structure
                return {
                    "type": "bar",
                    "title": "Sample Chart",
                    "labels": ["Category 1", "Category 2", "Category 3", "Category 4"],
                    "datasets": [{
                        "label": "Data Series",
                        "data": [10, 20, 15, 25],
                        "backgroundColor": ["#3B82F6", "#10B981", "#F59E0B", "#EF4444"],
                        "borderColor": ["#1D4ED8", "#059669", "#D97706", "#DC2626"],
                        "borderWidth": 1
                    }]
                }
        except:
            # Return default structure on any error
            return {
                "type": "bar",
                "title": "Sample Chart",
                "labels": ["A", "B", "C", "D"],
                "datasets": [{
                    "label": "Sample Data",
                    "data": [10, 20, 15, 25],
                    "backgroundColor": "#3B82F6",
                    "borderColor": "#1D4ED8",
                    "borderWidth": 1
                }]
            }


# Service instance
presentation_service = PresentationGeneratorService()


def generate_presentation(topic: str, slide_count: int = 10,
                        target_audience: str = None,
                        presentation_type: str = 'business',
                        tone: str = 'professional',
                        theme: str = 'modern',
                        include_images: bool = True,
                        include_charts: bool = True) -> Dict:
    """
    Main function to generate a complete presentation
    """
    try:
        start_time = time.time()
        
        # Generate outline
        outline_result = presentation_service.generate_presentation_outline(
            topic, slide_count, target_audience, presentation_type, tone
        )
        
        if not outline_result['success']:
            return outline_result
        
        slides = []
        total_generation_time = outline_result['generation_time']
        
        # Generate content for each slide
        for slide_data in outline_result['outline']:
            content_result = presentation_service.generate_slide_content(
                slide_data['title'],
                slide_data['slide_type'],
                f"Presentation about {topic}",
                tone
            )
            
            if content_result['success']:
                slide_data.update(content_result['content'])
                total_generation_time += content_result['generation_time']
            
            slides.append(slide_data)
        
        return {
            'success': True,
            'slides': slides,
            'generation_time': total_generation_time,
            'model_used': outline_result['model_used'],
            'slide_count': len(slides)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'generation_time': 0,
            'slides': []
        }


def get_presentation_metrics() -> Dict:
    """Get metrics about presentation generation service"""
    return {
        'gemini_available': presentation_service.gemini_available,
        'openrouter_available': presentation_service.openrouter_available,
        'service_status': 'active' if (presentation_service.gemini_available or 
                                     presentation_service.openrouter_available) else 'offline'
    }


def get_available_themes() -> List[Dict]:
    """Get list of available presentation themes"""
    return [
        {'id': 'modern', 'name': 'Modern & Clean', 'description': 'Clean design with modern typography'},
        {'id': 'corporate', 'name': 'Corporate Professional', 'description': 'Professional business style'},
        {'id': 'creative', 'name': 'Creative & Colorful', 'description': 'Vibrant and creative design'},
        {'id': 'minimal', 'name': 'Minimal & Simple', 'description': 'Simple and focused design'},
        {'id': 'academic', 'name': 'Academic & Traditional', 'description': 'Traditional academic style'},
        {'id': 'tech', 'name': 'Technology Focused', 'description': 'Modern tech-oriented design'},
        {'id': 'nature', 'name': 'Nature & Organic', 'description': 'Natural colors and organic shapes'},
        {'id': 'dark', 'name': 'Dark & Bold', 'description': 'Dark theme with bold accents'},
    ]


def get_available_templates() -> List[Dict]:
    """Get list of available presentation templates"""
    return [
        {
            'id': 'business_pitch',
            'name': 'Business Pitch',
            'description': 'Perfect for business presentations and pitches',
            'category': 'business',
            'slide_count': 12
        },
        {
            'id': 'educational',
            'name': 'Educational Content',
            'description': 'Great for educational and training materials',
            'category': 'education',
            'slide_count': 15
        },
        {
            'id': 'marketing',
            'name': 'Marketing Presentation',
            'description': 'Ideal for marketing campaigns and product launches',
            'category': 'marketing',
            'slide_count': 10
        },
        {
            'id': 'report',
            'name': 'Report & Analysis',
            'description': 'Professional template for reports and data analysis',
            'category': 'business',
            'slide_count': 8
        }
    ]
