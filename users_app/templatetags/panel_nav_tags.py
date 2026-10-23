from django import template
from django.urls import reverse

register = template.Library()


def _build_nav_groups(per_student):
    capacity_label = 'Davet Hakkı' if per_student else 'Kontenjan'
    koclar_pages = [
        {'key': 'koclar',        'label': 'Koç listesi & WP', 'url_name': 'panel_wp_koclar',       'badge_key': 'no_wp'},
        {'key': 'koc_ekle',      'label': 'Koç ekle',         'url_name': 'panel_koc_ekle'},
        {'key': 'koc_belgeleri', 'label': 'Belgeler',          'url_name': 'staff_coach_documents', 'badge_key': 'belgeler'},
        {'key': 'capacity',      'label': capacity_label,      'url_name': 'capacity_panel:overview'},
    ]
    if per_student:
        koclar_pages.append({
            'key':       'renewals',
            'label':     'Yenileme',
            'url_name':  'capacity_panel:renewal_list',
            'badge_key': 'renewals_claimed',
        })
    return [
        {
            'key':      'home',
            'label':    'Genel bakış',
            'url_name': 'panel_home',
            'pages':    [],
        },
        {
            'key':       'koclar',
            'label':     'Koçlar',
            'badge_key': 'koclar',
            'pages':     koclar_pages,
        },
        {
            'key':       'ogrenciler',
            'label':     'Öğrenciler',
            'badge_key': 'ogrenciler_group',
            'pages': [
                {'key': 'students', 'label': 'Öğrenciler', 'url_name': 'panel_ogrenciler', 'badge_key': 'overdue'},
                {'key': 'invites',  'label': 'Davetler',   'url_name': 'panel_davetler'},
            ],
        },
        {
            'key':       'satis',
            'label':     'Satış',
            'badge_key': 'satis',
            'pages': [
                {'key': 'orders', 'label': 'Siparişler', 'url_name': 'purchase_panel:orders', 'badge_key': 'transfers'},
                {'key': 'plans',  'label': 'Planlar',    'url_name': 'purchase_panel:plans'},
            ],
        },
        {
            'key':       'odemeler',
            'label':     'Ödemeler',
            'badge_key': 'odemeler_group',
            'pages': [
                {'key': 'earnings', 'label': 'Kazançlar', 'url_name': 'earnings_panel:list', 'badge_key': 'earnings'},
            ],
        },
    ]


@register.inclusion_tag('panel/includes/panel_nav.html', takes_context=True)
def panel_nav(context, active_section=''):
    from django.conf import settings
    per_student = getattr(settings, 'COACH_PER_STUDENT_PERIODS', False)

    request = context.get('request')
    badges = {}
    if request and getattr(request.user, 'is_staff', False):
        from users_app.panel_badges import all_badges
        badges = all_badges()

    nav_groups = _build_nav_groups(per_student)
    section_to_group = {
        page['key']: group['key']
        for group in nav_groups
        for page in group['pages']
    }
    section_to_group['home'] = 'home'
    active_group_key = section_to_group.get(active_section)

    groups = []
    second_row = None

    for group in nav_groups:
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
                second_row.append({
                    'label':  p['label'],
                    'url':    purl,
                    'active': p['key'] == active_section,
                    'badge':  bval,
                })

    return {
        'groups':     groups,
        'second_row': second_row,
        'admin_url':  reverse('admin:index'),
    }
