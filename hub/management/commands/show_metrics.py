from django.core.management.base import BaseCommand
import json

from hub.services.openrouter import get_metrics


class Command(BaseCommand):
    help = 'Show in-process OpenRouter metrics (reset on process restart)'

    def handle(self, *args, **options):
        metrics = get_metrics()
        self.stdout.write(json.dumps(metrics, indent=2))
