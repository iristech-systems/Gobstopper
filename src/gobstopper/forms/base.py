"""
Base form infrastructure with auto-rendering capabilities.
Supports both Tera templates (via to_dict) and direct Python rendering (via __html__).
"""

from typing import Any, Dict, List, Optional, Union, Callable
from abc import ABC, abstractmethod
import msgspec
from ..html import form, div, label, input, span, button, textarea, select, option
from ..html.datastar import bind, on_input, show, text as ds_text

class ValidationError(msgspec.Struct):
    """Represents a validation error for a field"""
    field: str
    message: str

class BaseField(ABC):
    """Base class for all form fields"""

    def __init__(
        self,
        name: str,
        label: str = "",
        required: bool = False,
        disabled: bool = False,
        help_text: str = "",
        placeholder: str = "",
        extra_classes: str = "",
        id: str = "",
        default: Any = None,
        validators: Optional[List[Callable]] = None,
        attrs: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.label = label or name.replace("_", " ").title()
        self.required = required
        self.disabled = disabled
        self.help_text = help_text
        self.placeholder = placeholder
        self.extra_classes = extra_classes
        self.id = id or name
        self.default = default
        self.validators = validators or []
        self.attrs = attrs or {}
        self.value = None
        self.errors: List[str] = []
        self._form = None  # Reference to parent form

    def validate(self, value: Any) -> bool:
        """Validate the field value"""
        self.errors = []

        # Check required
        if self.required and (value is None or value == ""):
            self.errors.append(f"{self.label} is required")
            return False

        # Run custom validators
        for validator in self.validators:
            try:
                validator(value)
            except ValueError as e:
                self.errors.append(str(e))

        return len(self.errors) == 0

    def get_value(self) -> Any:
        """Get the current field value or default"""
        return self.value if self.value is not None else self.default

    @abstractmethod
    def _render_input(self) -> Any:
        """Render the input element using htpy"""
        pass

    def __html__(self) -> str:
        """Auto-render as htpy element"""
        attrs = {"class": f"field {self.extra_classes}"}
        
        # Error handling for Datastar
        error_signal = f"errors.{self.name}" if self._form else f"errors"
        
        return str(div(**attrs)[
            label(for_=self.id)[self.label],
            self._render_input(),
            # Reactive error message
            span(class_="error", **show(f"${error_signal}"))[
                ds_text(f"${error_signal}")
            ] if self._form else None,
            # Static error message (fallback)
            *[span(class_="error")[err] for err in self.errors]
        ])

    def to_dict(self) -> Dict[str, Any]:
        """Convert field to dictionary for template rendering"""
        return {
            "name": self.name,
            "label": self.label,
            "required": self.required,
            "disabled": self.disabled,
            "help_text": self.help_text,
            "placeholder": self.placeholder,
            "extra_classes": self.extra_classes,
            "id": self.id,
            "value": self.get_value() or "",
            "errors": self.errors
        }

class TextField(BaseField):
    """Text input field"""

    def __init__(self, *args, input_type: str = "text", **kwargs):
        super().__init__(*args, **kwargs)
        self.input_type = input_type

    def _render_input(self) -> Any:
        attrs = {
            "type": self.input_type,
            "name": self.name,
            "id": self.id,
            "value": self.get_value() or "",
            "placeholder": self.placeholder,
            "disabled": self.disabled,
            "required": self.required,
            **bind(self.name),  # Auto-bind for Datastar
            **self.attrs,       # Merge extra attributes (e.g. event handlers)
        }
        return input(**attrs)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({"type": "input", "input_type": self.input_type})
        return d

class BaseForm:
    """Base form class that works with Tera templates and htpy auto-rendering"""

    def __init__(
        self,
        request: Optional[Any] = None,  # Can pass request explicitly
        data: Optional[Dict[str, Any]] = None,
        initial: Optional[Dict[str, Any]] = None,
        csrf_token: Optional[str] = None
    ):
        self.request = request
        self.data = data or {}
        self.initial = initial or {}
        self.fields: Dict[str, BaseField] = {}
        self.errors: List[ValidationError] = []
        self._is_valid = None
        
        # Auto-get CSRF from request if available
        if csrf_token:
            self.csrf_token = csrf_token
        elif request and hasattr(request, 'csrf_token'):
            self.csrf_token = request.csrf_token
        else:
            self.csrf_token = None

        # Initialize fields
        self._init_fields()
        
        # Set parent form reference on fields
        for field in self.fields.values():
            field._form = self

        # Set initial values
        self._set_initial_values()

    def _init_fields(self):
        """Initialize form fields - to be overridden by subclasses"""
        pass

    def _set_initial_values(self):
        """Set initial values from data or initial dict"""
        for field_name, field in self.fields.items():
            if field_name in self.data:
                field.value = self.data[field_name]
            elif field_name in self.initial:
                field.value = self.initial[field_name]

    def add_field(self, field: BaseField):
        """Add a field to the form"""
        self.fields[field.name] = field
        field._form = self

    def is_valid(self) -> bool:
        """Validate all form fields"""
        if self._is_valid is not None:
            return self._is_valid

        self.errors = []
        all_valid = True

        for field_name, field in self.fields.items():
            value = self.data.get(field_name)
            if not field.validate(value):
                all_valid = False
                for error in field.errors:
                    self.errors.append(ValidationError(field=field_name, message=error))

        self._is_valid = all_valid
        return all_valid

    def get_cleaned_data(self) -> Dict[str, Any]:
        """Get cleaned and validated form data"""
        if not self.is_valid():
            raise ValueError("Form is not valid. Call is_valid() first.")

        cleaned = {}
        for field_name, field in self.fields.items():
            cleaned[field_name] = field.get_value()
        return cleaned

    def __html__(self) -> str:
        """Auto-render form as htpy element"""
        form_content = []
        
        # Add CSRF token
        if self.csrf_token:
            form_content.append(input(type="hidden", name="csrf_token", value=self.csrf_token))
            
        # Add fields
        form_content.extend([field for field in self.fields.values()])
        
        # Add submit button
        form_content.append(div(class_="actions")[
            button(type="submit")["Submit"]
        ])
        
        return str(form(method="post")[form_content])

    def to_dict(self) -> Dict[str, Any]:
        """Convert form to dictionary for template rendering"""
        return {
            "fields": [field.to_dict() for field in self.fields.values()],
            "errors": [{"field": err.field, "message": err.message} for err in self.errors],
            "is_valid": self._is_valid,
            "csrf_token": self.csrf_token
        }
