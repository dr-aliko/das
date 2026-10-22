from django import template
from django.urls import reverse

register = template.Library()

# Single source of truth for the panel navigation.
# To add a page: append one dict here; touch nothing else.
_NAV_ITEMS = [
    {'key': 'home',           'label': 'Genel bakış',      'url_name': 'panel_home'},
    {'sep': 'Koçlar'},
    {'key': 'koclar',         'label': 'Koç listesi & WP', 'url_name': 'panel_wp_koclar'},
    {'key': 'koc_ekle',       'label': 'Koç ekle',         'url_name': 'panel_koc_ekle'},
    {'key': 'koc_belgeleri',  'label': 'Belgeler',          'url_name': 'staff_coach_documents'},
    {'key': 'capacity',       'label': 'Kontenjan',         'url_name': 'capacity_panel:overview'},
    {'sep': 'Öğrenciler'},
    {'key': 'students',       'label': 'Öğrenciler',        'url_name': 'panel_ogrenciler'},
    {'key': 'invites',        'label': 'Davetler',          'url_name': 'panel_davetler'},
    {'sep': 'Satış'},
    {'key': 'orders',         'label': 'Siparişler',        'url_name': 'purchase_panel:orders'},
    {'key': 'plans',          'label': 'Planlar',           'url_name': 'purchase_panel:plans'},
    {'sep': 'Ödemeler'},
    {'key': 'earnings',       'label': 'Kazançlar',         'url_name': 'earnings_panel:list'},
    {'sep': 'Eski ödeme takibi'},
    {'key': 'classification', 'label': 'Tarifeler',         'url_name': 'panel_billing'},
    {'key': 'payments',       'label': 'Ödeme özeti',       'url_name': 'panel_odemeler'},
]


@register.inclusion_tag('panel/includes/panel_nav.html')
def panel_nav(active_section=''):
    items = []
    for item in _NAV_ITEMS:
        if 'sep' in item:
            items.append({'sep': item['sep']})
        else:
            items.append({
                'label':  item['label'],
                'url':    reverse(item['url_name']),
                'active': item['key'] == active_section,
            })
    return {'items': items, 'admin_url': reverse('admin:index')}
