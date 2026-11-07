"""Universal persona contracts. No behavioral simulation or fitted models."""
from .schema import UniversalPersona
from .resolver import resolve_persona

__all__ = ['UniversalPersona', 'resolve_persona']
