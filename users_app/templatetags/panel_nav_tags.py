from django import template
from django.urls import reverse

register = template.Library()

# Single source of truth. To add a page: one dict in the right group's pages list.
# Groups with no pages link directly (url_name on the group itself).
# Groups with one page link to it directly and show no second row.
# Groups with multiple pages show a second row when their group is active.
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
        'pages': [
            {'key': 'koclar',        'label': 'Koç listesi & WP', 'url_name': 'panel_wp_koclar'},
            {'key': 'koc_ekle',      'label': 'Koç ekle',         'url_name': 'panel_koc_ekle'},
            {'key': 'koc_belgeleri', 'label': 'Belgeler',          'url_name': 'staff_coach_documents'},
            {'key': 'capacity',      'label': 'Kontenjan',         'url_name': 'capacity_panel:overview'},
        ],
    },
    {
        'key': 'ogrenciler',
        'label': 'Öğrenciler',
        'pages': [
            {'key': 'students', 'label': 'Öğrenciler', 'url_name': 'panel_ogrenciler'},
            {'key': 'invites',  'label': 'Davetler',   'url_name': 'panel_davetler'},
        ],
    },
    {
        'key': 'satis',
        'label': 'Satış',
        'pages': [
            {'key': 'orders', 'label': 'Siparişler', 'url_name': 'purchase_panel:orders'},
            {'key': 'plans',  'label': 'Planlar',    'url_name': 'purchase_panel:plans'},
        ],
    },
    {
        'key': 'odemeler',
        'label': 'Ödemeler',
        'pages': [
            {'key': 'earnings', 'label': 'Kazançlar', 'url_name': 'earnings_panel:list'},
        ],
    },
]

# Auto-built: every page key → its group key.
# Keys not in this map (e.g. legacy 'classification', 'payments') return None from .get()
# which means no group is highlighted — correct for pages that are no longer in the menu.
_SECTION_TO_GROUP = {
    page['key']: group['key']
    for group in _NAV_GROUPS
    for page in group['pages']
}
_SECTION_TO_GROUP['home'] = 'home'


@register.inclusion_tag('panel/includes/panel_nav.html')
def panel_nav(active_section=''):
    active_group_key = _SECTION_TO_GROUP.get(active_section)

    groups = []
    second_row = None

    for group in _NAV_GROUPS:
        gkey = group['key']
        pages = group['pages']
        g_active = (gkey == active_group_key)

        url = reverse(group['url_name']) if not pages else reverse(pages[0]['url_name'])

        groups.append({'label': group['label'], 'url': url, 'active': g_active})

        if g_active and len(pages) > 1:
            second_row = [
                {
                    'label':  p['label'],
                    'url':    reverse(p['url_name']),
                    'active': p['key'] == active_section,
                }
                for p in pages
            ]

    return {
        'groups': groups,
        'second_row': second_row,
        'admin_url': reverse('admin:index'),
    }
