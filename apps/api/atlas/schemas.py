import math
import re
import unicodedata
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NORMALIZATION_VERSION = "nfc-casefold-ucd15.1-v1"


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", value).casefold())


Mode = Literal["suffix", "prefix", "contains", "exact"]
Kind = Literal["settlement", "district"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pattern(StrictModel):
    mode: Mode = "suffix"
    value: str = Field(min_length=1, max_length=80)

    @field_validator("value")
    @classmethod
    def valid_value(cls, value: str) -> str:
        if not value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("Leere Muster und Steuerzeichen sind nicht erlaubt")
        return value


class Group(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,24}$")
    title: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#126b61", pattern=r"^#[0-9a-fA-F]{6}$")
    patterns: list[Pattern] = Field(min_length=1, max_length=8)
    exclusions: list[Pattern] = Field(default_factory=list, max_length=8)


class Filter(StrictModel):
    schema_version: Literal[1] = 1
    dataset: str | None = Field(default=None, min_length=1, max_length=100)
    groups: list[Group] = Field(default_factory=list, max_length=10)
    regions: list[str] = Field(default_factory=list, max_length=12)
    kinds: list[Kind] = Field(default_factory=list, max_length=2)
    bbox: tuple[float, float, float, float] | None = None

    @field_validator("regions")
    @classmethod
    def valid_regions(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"(state|district|municipality):[0-9]{2,12}", v) for v in values):
            raise ValueError("Ungültiger Gebietsschlüssel")
        return sorted(set(values))

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, b):
        if b is not None and (not all(math.isfinite(x) for x in b) or
                not (-180 <= b[0] < b[2] <= 180 and -85.051129 <= b[1] < b[3] <= 85.051129)):
            raise ValueError("Ungültige Bounding Box")
        return b

    @model_validator(mode="after")
    def unique_groups(self):
        if len({g.id for g in self.groups}) != len(self.groups):
            raise ValueError("Gruppenkennungen müssen eindeutig sein")
        return self


class SourceOut(StrictModel):
    product: str
    version: str
    data_date: str
    license: str
    attribution: str
    url: str


class DatasetOut(StrictModel):
    id: str
    label: str
    synthetic: bool
    scope: str
    active: bool
    geometry_date: str
    population_date: str
    sources: list[SourceOut]
    place_count: int


class RegionOut(StrictModel):
    id: str
    name: str
    level: str


class Match(StrictModel):
    group: str
    name: str
    mode: Mode
    pattern: str


class MunicipalityOut(StrictModel):
    name: str
    population: int | None
    population_date: str
    population_quality: str


class PlaceOut(StrictModel):
    id: str
    name: str
    kind: str
    alternatives: list[str]
    longitude: float
    latitude: float
    groups: list[str]
    matches: list[Match]
    municipality: MunicipalityOut | None
    assignment: str
    regions: list[RegionOut]


class PlacePage(StrictModel):
    dataset: str
    total: int
    offset: int
    limit: int
    items: list[PlaceOut]


class GroupStatistic(StrictModel):
    group: str
    count: int
    denominator: int
    share: float | None
    municipality_population: int | None
    matched_municipalities: int
    missing_population: int


class RegionalGroupStatistic(StrictModel):
    group: str
    count: int
    denominator: int
    share: float | None


class RegionalStatistic(StrictModel):
    region: RegionOut
    total: int
    denominator: int
    groups: list[RegionalGroupStatistic]


class StatisticsOut(StrictModel):
    dataset: str
    total: int
    denominator: int
    overlap: int
    groups: list[GroupStatistic]
    regions: list[RegionalStatistic]
    denominator_description: str = "Alle erfassten Orte mit denselben Gebiets-, Ortsart- und Ausschnittfiltern, ohne Namensfilter."
    population_description: str = "Einwohner von Gemeinden, deren eigener Gemeindename passt; keine Einwohnerzahl einzelner Siedlungen. Ortsartfilter gelten nur für Ortszahlen."


class PresetOut(StrictModel):
    id: str
    title: str
    description: str
    comparison: Literal["independent"] = "independent"
    groups: list[Group]


class ErrorOut(StrictModel):
    code: str
    message: str
    request_id: str


class GridCell(StrictModel):
    id: str
    cx: float
    cy: float


class GridGeometry(StrictModel):
    representation: Literal["circle-centers-v1"] = "circle-centers-v1"
    dataset: str
    grid: str
    crs: str = "EPSG:3035"
    cell_size: int = 20000
    origin: tuple[int, int] = (0, 0)
    viewbox: tuple[float, float, float, float]
    bounds: tuple[float, float, float, float]
    outline: str
    cells: list[GridCell]


class GridValue(StrictModel):
    id: str
    denominator: int
    counts: list[int]


class GridValues(StrictModel):
    dataset: str
    grid: str
    groups: list[str]
    totals: list[int]
    denominator: int
    cells: list[GridValue]


class BaseCell(StrictModel):
    id: str
    denominator: int


class GridBase(StrictModel):
    dataset: str
    grid: str
    base_key: str
    missing_cells: Literal['no-places'] = 'no-places'
    denominator: int
    cells: list[BaseCell]


class HitCell(StrictModel):
    id: str
    count: int


class GridHit(StrictModel):
    group: str
    total: int
    cells: list[HitCell]


class GridCounts(StrictModel):
    dataset: str
    grid: str
    base_key: str
    missing_counts: Literal['zero'] = 'zero'
    groups: list[GridHit]


class CellPlace(StrictModel):
    id: str
    name: str
    matching_names: list[str]


class CellPlaces(StrictModel):
    dataset: str
    cell: str
    group: str
    count: int
    denominator: int
    share: float | None
    limit: int
    offset: int
    items: list[CellPlace]
