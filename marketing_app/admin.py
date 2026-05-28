from django.contrib import admin

from .models import (
    CoachProfile,
    CoachRequest,
    FAQItem,
    FeatureItem,
    PricingFeature,
    PricingPlan,
    SiteSettings,
    Testimonial,
)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Hero', {
            'fields': (
                'hero_eyebrow', 'hero_title_line1', 'hero_title_line2',
                'hero_subtitle', 'hero_cta_primary_label', 'hero_cta_primary_url',
                'hero_cta_secondary_label', 'hero_cta_secondary_url',
            ),
        }),
        ('Son CTA Bölümü', {
            'fields': ('final_cta_title', 'final_cta_subtitle'),
        }),
        ('Navbar', {
            'fields': ('nav_cta_label', 'nav_cta_url'),
        }),
        ('Altbilgi', {
            'fields': ('footer_tagline', 'footer_copyright', 'footer_location'),
        }),
        ('İletişim', {
            'fields': ('contact_email', 'contact_corporate_email', 'contact_whatsapp'),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FeatureItem)
class FeatureItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'title', 'accent', 'show_on_home', 'is_published')
    list_editable = ('order', 'show_on_home', 'is_published')
    list_display_links = ('title',)
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title', 'subtitle')


class PricingFeatureInline(admin.TabularInline):
    model = PricingFeature
    extra = 1
    fields = ('order', 'text')


@admin.register(PricingPlan)
class PricingPlanAdmin(admin.ModelAdmin):
    list_display = ('order', 'name', 'price_monthly_try', 'is_featured', 'is_published')
    list_editable = ('order', 'is_featured', 'is_published')
    list_display_links = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [PricingFeatureInline]


@admin.register(FAQItem)
class FAQItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'category', 'question', 'is_published')
    list_editable = ('order', 'is_published')
    list_display_links = ('question',)
    list_filter = ('category',)
    search_fields = ('question', 'answer')


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('order', 'student_name', 'accent', 'is_published')
    list_editable = ('order', 'is_published')
    list_display_links = ('student_name',)


@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ('order', '_display_name', 'title', 'is_public')
    list_editable = ('order', 'is_public')
    list_display_links = ('_display_name',)
    list_filter = ('is_public',)
    prepopulated_fields = {'slug': ('display_name',)}
    raw_id_fields = ('user',)
    search_fields = ('display_name', 'user__full_name', 'title')

    @admin.display(description='Koç')
    def _display_name(self, obj):
        return obj.get_display_name()


@admin.register(CoachRequest)
class CoachRequestAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'full_name', 'email', 'phone', '_coach', 'grade_level', 'track', 'status')
    list_filter = ('status', 'coach_profile', 'track', 'grade_level')
    list_editable = ('status',)
    list_display_links = ('full_name',)
    search_fields = ('full_name', 'email', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Öğrenci', {
            'fields': ('full_name', 'email', 'phone', 'grade_level', 'target_exam_year', 'track', 'note'),
        }),
        ('Veli', {
            'fields': ('parent_name', 'parent_phone'),
            'classes': ('collapse',),
        }),
        ('Yönetim', {
            'fields': ('coach_profile', 'status', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Koç')
    def _coach(self, obj):
        return obj.coach_profile.get_display_name() if obj.coach_profile else '—'
