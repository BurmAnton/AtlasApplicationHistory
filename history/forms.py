from django import forms

class ImportForm(forms.Form):
    snapshot_dt = forms.DateTimeField(
        label="Дата и время среза",
        input_formats=['%d.%m.%Y, %H:%M'],
        widget=forms.DateTimeInput(format='%d.%m.%Y, %H:%M', attrs={'placeholder': '13.11.2025, 21:00', 'class': 'form-control'}),
        help_text="Формат: ДД.ММ.ГГГГ, ЧЧ:ММ"
    )
    file = forms.FileField(
        label="Файл выгрузки (Excel)",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )

