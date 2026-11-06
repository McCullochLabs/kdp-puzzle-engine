"""Versioned, bounded Sudoku text sizes; separate from bonus-page presets.

This renderer contract does not certify Large Print or change saved book plans.
Vector shape grids retain their established geometry.
"""
from dataclasses import asdict, dataclass
import math

@dataclass(frozen=True)
class SudokuTypography:
    schema_version: int = 1
    puzzle_font_pt: float = 28.0
    solution_font_pt: float = 17.0

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('Unsupported Sudoku typography version.')
        for name, minimum, maximum in (('puzzle_font_pt',28,34),('solution_font_pt',17,22)):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not minimum<=value<=maximum:
                raise ValueError(f'{name} must be a finite number from {minimum} to {maximum} points.')
            object.__setattr__(self,name,float(value))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value,dict) or set(value)!={'schema_version','puzzle_font_pt','solution_font_pt'}:
            raise ValueError('Sudoku typography requires its exact versioned fields.')
        return cls(**value)


def resolve_typography(value=None):
    if value is None:return SudokuTypography()
    if type(value) is not SudokuTypography:
        raise ValueError('Choose a validated SudokuTypography configuration.')
    return value


def package_typography(kind, value):
    if value is None:return None
    if kind != 'Sudoku':raise ValueError('Package typography currently supports Sudoku only.')
    config=resolve_typography(value)
    return None if config==SudokuTypography() else config


def typography_facts(facts, config):
    if config is None:return facts
    import hashlib,json
    result=dict(facts);result['sudoku_typography']=config.to_dict()
    result['fingerprint']=hashlib.sha256(json.dumps({'base':facts['fingerprint'],'sudoku_typography':config.to_dict()},sort_keys=True).encode()).hexdigest()
    return result


def bind_typography(pdf, config):
    import hashlib,json
    from pathlib import Path
    pdf=Path(pdf);manifest=pdf.with_suffix('.puzzles.json')
    value={'schema_version':1,'sudoku_typography':config.to_dict(),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzle_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}
    pdf.with_suffix('.typography.json').write_text(json.dumps(value,sort_keys=True,indent=2),encoding='utf-8')


def verify_typography_binding(pdf, config):
    import hashlib,json
    from pathlib import Path
    pdf=Path(pdf)
    try:
        value=json.loads(pdf.with_suffix('.typography.json').read_text(encoding='utf-8'))
        expected={'schema_version':1,'sudoku_typography':config.to_dict(),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'puzzle_manifest_sha256':hashlib.sha256(pdf.with_suffix('.puzzles.json').read_bytes()).hexdigest()}
        if value!=expected:raise ValueError('binding mismatch')
    except (OSError,ValueError,TypeError) as exc:
        raise ValueError('Sudoku typography/PDF binding changed or is missing; preserving the package for review.') from exc


def configured_package_typography(folder):
    """Validate opt-in source evidence; legacy unconfigured packages return None."""
    import json
    from pathlib import Path
    from .package_layout import package_file
    folder=Path(folder).resolve();pdf=package_file(folder,'interior.pdf')
    source=package_file(folder,'PACKAGE_SOURCE_RECORD.json');binding=pdf.with_suffix('.typography.json')
    for path in (pdf,source,binding,pdf.with_suffix('.puzzles.json')):
        if not path.resolve().is_relative_to(folder):raise ValueError('Typography evidence is outside the selected package.')
    raw=source.read_bytes() if source.is_file() else b''
    try:payload=json.loads(raw.decode('utf-8-sig')) if raw else {}
    except ValueError as exc:
        if binding.is_file() or (b'"sudoku_typography"' in raw or b'"cryptogram_typography"' in raw):
            raise ValueError('Configured Sudoku typography source is invalid.') from exc
        return None
    declared=isinstance(payload,dict) and ('sudoku_typography' in payload or 'cryptogram_typography' in payload)
    if not declared and not binding.is_file():return None
    if isinstance(payload,dict) and 'cryptogram_typography' in payload:
        if 'sudoku_typography' in payload or payload.get('puzzle_type')!='Cryptogram':
            raise ValueError('Configured typography source family is inconsistent.')
        from .cryptogram_typography import CryptogramTypography, verify_typography_binding as verify_crypto
        config=CryptogramTypography.from_dict(payload['cryptogram_typography'])
        verify_crypto(pdf,config)
        return config
    if not isinstance(payload,dict) or payload.get('puzzle_type')!='Sudoku':
        raise ValueError('Configured typography requires its Sudoku source record.')
    config=SudokuTypography.from_dict(payload.get('sudoku_typography'))
    verify_typography_binding(pdf,config)
    return config
