from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    """Add CSS classes to a form field widget from template: {{ field|add_class:'foo' }}"""
    try:
        existing = field.field.widget.attrs.get('class', '')
        final = (existing + ' ' + css).strip()
        return field.as_widget(attrs={'class': final})
    except Exception:
        return field
