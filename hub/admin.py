from django.contrib import admin
from .models import (
    ImageGenerationRequest, GeneratedImage, ImageUpscaleRequest, UserImagePreferences,
    IDEProject, CodeFile, IDEChatMessage, CodeExecutionResult, 
    ProjectDeployment, ProjectExport, UserIDEPreferences
)

# Configure Material admin site titles and branding
admin.site.site_header = 'IntelliHub Admin'
admin.site.site_title = 'IntelliHub'
admin.site.index_title = 'Management Dashboard'

@admin.register(ImageGenerationRequest)
class ImageGenerationRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'prompt_preview', 'status', 'width', 'height', 'created_at', 'generation_time')
    list_filter = ('status', 'style_preset', 'created_at', 'width', 'height')
    search_fields = ('prompt', 'negative_prompt', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'generation_time', 'cached')
    ordering = ('-created_at',)
    
    def prompt_preview(self, obj):
        return obj.prompt[:50] + "..." if len(obj.prompt) > 50 else obj.prompt
    prompt_preview.short_description = 'Prompt'

@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'seed_used', 'file_size', 'favorited', 'public', 'created_at')
    list_filter = ('favorited', 'public', 'created_at', 'mime_type')
    search_fields = ('request__prompt', 'request__user__username')
    readonly_fields = ('created_at', 'file_size', 'image_data')
    ordering = ('-created_at',)

@admin.register(ImageUpscaleRequest)
class ImageUpscaleRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'original_image', 'status', 'created_at', 'processing_time')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'processing_time')
    ordering = ('-created_at',)

@admin.register(UserImagePreferences)
class UserImagePreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_images_generated', 'total_generation_time', 'favorite_style_preset', 'created_at')
    list_filter = ('favorite_style_preset', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'updated_at', 'total_images_generated', 'total_generation_time')
    ordering = ('-total_images_generated',)


# ============================================================================
# IDE ADMIN
# ============================================================================

@admin.register(IDEProject)
class IDEProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user', 'project_type', 'is_public', 'ai_enabled', 'total_executions', 'created_at', 'updated_at')
    list_filter = ('project_type', 'is_public', 'ai_enabled', 'is_template', 'created_at')
    search_fields = ('name', 'description', 'user__username')
    readonly_fields = ('created_at', 'updated_at', 'last_accessed', 'total_executions', 'total_ai_queries')
    ordering = ('-updated_at',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'name', 'description', 'project_type')
        }),
        ('Settings', {
            'fields': ('is_public', 'is_template', 'ai_enabled', 'ai_model')
        }),
        ('Execution Settings', {
            'fields': ('python_version', 'node_version')
        }),
        ('Statistics', {
            'fields': ('total_executions', 'total_ai_queries')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_accessed')
        }),
    )


@admin.register(CodeFile)
class CodeFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'path', 'project', 'file_type', 'size_bytes', 'line_count', 'updated_at')
    list_filter = ('file_type', 'ai_generated', 'created_at', 'updated_at')
    search_fields = ('name', 'path', 'project__name', 'content')
    readonly_fields = ('created_at', 'updated_at', 'size_bytes', 'line_count', 'version')
    ordering = ('-updated_at',)
    
    fieldsets = (
        ('File Information', {
            'fields': ('project', 'name', 'path', 'file_type', 'language')
        }),
        ('Content', {
            'fields': ('content',)
        }),
        ('Version Control', {
            'fields': ('version', 'previous_version')
        }),
        ('Metadata', {
            'fields': ('size_bytes', 'line_count', 'ai_generated', 'ai_model_used')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(IDEChatMessage)
class IDEChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'role', 'message_preview', 'message_type', 'model_used', 'created_at')
    list_filter = ('role', 'message_type', 'created_at')
    search_fields = ('content', 'project__name')
    readonly_fields = ('created_at', 'response_time', 'tokens_used')
    ordering = ('-created_at',)
    
    def message_preview(self, obj):
        return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content
    message_preview.short_description = 'Message'


@admin.register(CodeExecutionResult)
class CodeExecutionResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'user', 'execution_type', 'status', 'exit_code', 'execution_time', 'created_at')
    list_filter = ('status', 'execution_type', 'created_at')
    search_fields = ('project__name', 'user__username', 'code')
    readonly_fields = ('created_at', 'started_at', 'completed_at', 'execution_time', 'memory_used', 'cpu_time')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Execution Details', {
            'fields': ('project', 'user', 'file', 'execution_type', 'command')
        }),
        ('Code', {
            'fields': ('code',)
        }),
        ('Environment', {
            'fields': ('environment',)
        }),
        ('Results', {
            'fields': ('status', 'exit_code', 'stdout', 'stderr')
        }),
        ('Performance', {
            'fields': ('execution_time', 'memory_used', 'cpu_time')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at')
        }),
    )


@admin.register(ProjectDeployment)
class ProjectDeploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'user', 'platform', 'status', 'deployment_url', 'created_at', 'deployed_at')
    list_filter = ('platform', 'status', 'created_at')
    search_fields = ('project__name', 'user__username', 'deployment_url', 'repository_url')
    readonly_fields = ('created_at', 'deployed_at')
    ordering = ('-created_at',)


@admin.register(ProjectExport)
class ProjectExportAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'user', 'export_format', 'status', 'file_size', 'created_at', 'expires_at')
    list_filter = ('export_format', 'status', 'created_at')
    search_fields = ('project__name', 'user__username')
    readonly_fields = ('created_at', 'file_size')
    ordering = ('-created_at',)


@admin.register(UserIDEPreferences)
class UserIDEPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'theme', 'font_size', 'total_projects', 'total_executions', 'total_ai_queries', 'updated_at')
    list_filter = ('theme', 'ai_autocomplete', 'ai_suggestions', 'auto_save', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'updated_at', 'total_projects', 'total_executions', 'total_ai_queries')
    ordering = ('-updated_at',)
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Editor Settings', {
            'fields': ('theme', 'font_size', 'font_family', 'tab_size', 'use_spaces', 'word_wrap', 'line_numbers', 'minimap_enabled')
        }),
        ('AI Settings', {
            'fields': ('ai_autocomplete', 'ai_suggestions', 'preferred_ai_model')
        }),
        ('Execution Settings', {
            'fields': ('auto_save', 'auto_format')
        }),
        ('Layout', {
            'fields': ('sidebar_position', 'terminal_position')
        }),
        ('Statistics', {
            'fields': ('total_projects', 'total_executions', 'total_ai_queries')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

