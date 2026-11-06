"""Bounded versioned Cryptogram text settings; renderer only, not a print certification."""
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class CryptogramTypography:
    schema_version: int = 1
    puzzle_font_pt: float = 17.0
    solution_font_pt: float = 11.0

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported Cryptogram typography version.")
        for name, minimum, maximum in (("puzzle_font_pt", 17, 22), ("solution_font_pt", 11, 14)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be a finite number from {minimum} to {maximum} points.")
            object.__setattr__(self, name, float(value))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"schema_version", "puzzle_font_pt", "solution_font_pt"}:
            raise ValueError("Cryptogram typography requires its exact versioned fields.")
        return cls(**value)


def resolve_typography(value=None):
    if value is None:
        return CryptogramTypography()
    if type(value) is not CryptogramTypography:
        raise ValueError("Choose a validated CryptogramTypography configuration.")
    return value


def package_typography(kind, value):
    if value is None:return None
    if kind != 'Cryptogram':raise ValueError('Package typography currently supports Cryptogram only.')
    config=resolve_typography(value)
    return None if config==CryptogramTypography() else config


def typography_facts(facts, config):
    if config is None:return facts
    import hashlib,json
    result=dict(facts);result['cryptogram_typography']=config.to_dict()
    result['fingerprint']=hashlib.sha256(json.dumps({'base':facts['fingerprint'],'cryptogram_typography':config.to_dict()},sort_keys=True).encode()).hexdigest()
    return result


def bind_typography(pdf, config):
    import hashlib,json
    from pathlib import Path
    pdf=Path(pdf);manifest=pdf.with_suffix('.puzzles.json')
    value={'schema_version':1,'cryptogram_typography':config.to_dict(),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzle_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}
    pdf.with_suffix('.typography.json').write_text(json.dumps(value,sort_keys=True,indent=2),encoding='utf-8')


def verify_typography_binding(pdf, config):
    import hashlib,json
    from pathlib import Path
    pdf=Path(pdf)
    try:
        value=json.loads(pdf.with_suffix('.typography.json').read_text(encoding='utf-8'))
        expected={'schema_version':1,'cryptogram_typography':config.to_dict(),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzle_manifest_sha256':hashlib.sha256(pdf.with_suffix('.puzzles.json').read_bytes()).hexdigest()}
        if value!=expected:raise ValueError('binding mismatch')
    except (OSError,ValueError,TypeError) as exc:
        raise ValueError('Cryptogram typography/PDF binding changed or is missing; preserving the package for review.') from exc

