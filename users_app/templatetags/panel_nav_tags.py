from django import template
from django.urls import reverse

register = template.Library()

# Single source of truth. To add a page: one dict in the right group's pages list.
# badge_key references a key in the all_badges() dict; omit for no badge.
_NAV_GROUPS = [
    {
        'key': 'home',
        'label': 'Genel bakış',
        'url_name': 'panel_home',
        'pages': [],
    },
    {
        'key': 'koclar',
        'label': 'Koçlar',
        'badge_key': 'koclar',
        'pages': [
            {'key': 'koclar',        'label': 'Koç listesi & WP', 'url_name': 'panel_wp_koclar',        'badge_key': 'no_wp',    'badge_filter': '?filtre=wp-unmatched'},
            {'key': 'koc_ekle',      'label': 'Koç ekle',         'url_name': 'panel_koc_ekle'},
            {'key': 'koc_belgeleri', 'label': 'Belgeler',          'url_name': 'staff_coach_documents',  'badge_key': 'belgeler', 'badge_filter': '?filtre=documents-pending'},
            {'key': 'capacity',      'label': 'Kontenjan',         'url_name': 'capacity_panel:overview'},
        ],
    },
    {
        'key': 'ogrenciler',
        'label': 'Öğrenciler',
        'badge_key': 'ogrenciler_group',
        'pages': [
            {'key': 'students', 'label': 'Öğrenciler', 'url_name': 'panel_ogrenciler', 'badge_key': 'overdue', 'badge_filter': '?filtre=vagus-ended'},
            {'key': 'invites',  'label': 'Davetler',   'url_name': 'panel_davetler'},
        ],
    },
    {
        'key': 'satis',
        'label': 'Satış',
        'badge_key': 'satis',
        'pages': [
            {'key': 'orders', 'label': 'Siparişler', 'url_name': 'purchase_panel:orders', 'badge_key': 'transfers', 'badge_filter': '?filter=claimed'},
            {'key': 'plans',  'label': 'Planlar',    'url_name': 'purchase_panel:plans'},
        ],
    },
    {
        'key': 'odemeler',
        'label': 'Ödemeler',
        'badge_key': 'odemeler_group',
        'pages': [
            {'key': 'earnings', 'label': 'Kazançlar', 'url_name': 'earnings_panel:list', 'badge_key': 'earnings', 'badge_filter': '?filtre=earnings-ready'},
        ],
    },
]

# Auto-built: every page key → its group key.
_SECTION_TO_GROUP = {
    page['key']: group['key']
    for group in _NAV_GROUPS
    for page in group['pages']
}
_SECTION_TO_GROUP['home'] = 'home'


@register.inclusion_tag('panel/includes/panel_nav.html', takes_context=True)
def panel_nav(context, active_section=''):
    request = context.get('request')
    badges = {}
    if request and getattr(request.user, 'is_staff', False):
        from users_app.panel_badges import all_badges
        badges = all_badges()

    active_group_key = _SECTION_TO_GROUP.get(active_section)

    groups = []
    second_row = None

    for group in _NAV_GROUPS:
        gkey = group['key']
        pages = group['pages']
        g_active = (gkey == active_group_key)

        url = reverse(group['url_name']) if not pages else reverse(pages[0]['url_name'])
        badge_val = badges.get(group.get('badge_key', ''), 0)

        groups.append({
            'label':  group['label'],
            'url':    url,
            'active': g_active,
            'badge':  badge_val if badge_val else 0,
        })

        if g_active and len(pages) > 1:
            second_row = []
            for p in pages:
                bval = badges.get(p.get('badge_key', ''), 0) or 0
                purl = reverse(p['url_name'])
                if bval and p.get('badge_filter'):
                    purl += p['badge_filter']
                second_row.append({
                    'label':  p['label'],
                    'url':    purl,
                    'active': p['key'] == active_section,
                    'badge':  bval,
                })

    return {
        'groups':    groups,
        'second_row': second_row,
        'admin_url': reverse('admin:index'),
    }
