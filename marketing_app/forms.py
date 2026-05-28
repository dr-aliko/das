from django import forms
from django.utils.timezone import now

from .models import CoachRequest


def _year_choices():
    current = now().year
    return [(y, str(y)) for y in range(current, current + 5)]


class CoachRequestForm(forms.ModelForm):
    target_exam_year = forms.TypedChoiceField(
        choices=_year_choices,
        coerce=int,
        label='Hedef Sınav Yılı',
    )

    class Meta:
        model = CoachRequest
        fields = [
            'full_name', 'email', 'phone',
            'grade_level', 'target_exam_year', 'track',
            'note', 'parent_name', 'parent_phone',
        ]
        widgets = {
            'note': forms.Textarea(attrs={'rows': 4}),
        }
