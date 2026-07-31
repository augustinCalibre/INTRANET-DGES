from django import forms


class StyledFormMixin:
    date_time_input_format = "%Y-%m-%dT%H:%M"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            existing_classes = widget.attrs.get("class", "")

            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css_class = "form-select"
            elif isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css_class = "form-check-input"
            else:
                css_class = "form-control"

            widget.attrs["class"] = f"{existing_classes} {css_class}".strip()

            if isinstance(widget, forms.DateTimeInput):
                widget.attrs["type"] = "text"
                widget.attrs["data-flatpickr"] = "datetime"
                widget.attrs.setdefault("autocomplete", "off")
                widget.attrs.setdefault("placeholder", "JJ/MM/AAAA HH:MM")
                widget.format = self.date_time_input_format
            elif isinstance(widget, forms.DateInput):
                widget.attrs["type"] = "text"
                widget.attrs["data-flatpickr"] = "date"
                widget.attrs.setdefault("autocomplete", "off")
                widget.attrs.setdefault("placeholder", "JJ/MM/AAAA")
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)


class AgentModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        full_name = obj.get_full_name().strip()
        return full_name or obj.username


class AgentMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        full_name = obj.get_full_name().strip()
        return full_name or obj.username
