from django import template
import markdown

register = template.Library()

@register.filter(name='markdown')
def markdown_filter(text):
    if not text:
        return ''
    return markdown.markdown(text, extensions=['extra', 'nl2br'])