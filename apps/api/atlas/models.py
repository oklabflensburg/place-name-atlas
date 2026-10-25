"""Persistence only; HTTP schemas live in schemas.py."""
from datetime import datetime, timezone
from typing import Any
from geoalchemy2 import Geometry
from sqlalchemy import Column, BigInteger, Integer, Computed, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class SourceVersion(SQLModel, table=True):
    __tablename__ = "source_version"
    id: str = Field(primary_key=True)
    product: str
    version: str
    data_date: str
    retrieved_at: str
    url: str
    sha256: str
    license: str
    attribution: str
    original_crs: str
    status: str = "staged"
    importer_version: str = "0.1.0"


class Dataset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    label: str
    status: str = "staging"
    synthetic: bool = False
    scope: str = "Deutschland"
    geometry_date: str
    population_date: str
    gn_source: str = Field(foreign_key="source_version.id")
    vg_source: str = Field(foreign_key="source_version.id")
    ew_source: str = Field(foreign_key="source_version.id")
    fingerprint: str
    report: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Publication(SQLModel, table=True):
    __tablename__ = "publication"
    id: int = Field(default=1, primary_key=True)
    dataset_id: str = Field(foreign_key="dataset.id")


class PlaceIdentity(SQLModel, table=True):
    __tablename__ = "place_identity"
    id: str = Field(primary_key=True)
    source_id: str = Field(unique=True)
    feature_id: int = Field(sa_column=Column(BigInteger, unique=True, nullable=False))


class AdminIdentity(SQLModel, table=True):
    __tablename__ = "admin_identity"
    id: str = Field(primary_key=True)
    level: str
    code: str = Field(index=True)


class AdminArea(SQLModel, table=True):
    __tablename__ = "admin_area"
    __table_args__ = (UniqueConstraint("dataset_id", "identity_id"),)
    id: str = Field(primary_key=True)
    dataset_id: str = Field(foreign_key="dataset.id", index=True)
    identity_id: str = Field(foreign_key="admin_identity.id")
    source_id: str
    code: str = Field(index=True)
    ars: str
    level: str = Field(index=True)
    parent_code: str | None = None
    name: str
    normalized_name: str
    ibz: str
    geom: Any = Field(sa_column=Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False))
    display_geom: Any = Field(default=None, sa_column=Column(
        Geometry("MULTIPOLYGON", srid=3035, spatial_index=False),
        Computed("ST_SimplifyPreserveTopology(ST_Transform(geom,3035),150)", persisted=True), nullable=False))


class Population(SQLModel, table=True):
    __tablename__ = "population"
    __table_args__ = (UniqueConstraint("dataset_id", "area_id"),)
    id: str = Field(primary_key=True)
    dataset_id: str = Field(foreign_key="dataset.id", index=True)
    area_id: str = Field(foreign_key="admin_area.id")
    source_id: str = Field(foreign_key="source_version.id")
    reference_date: str
    value: int | None = Field(default=None, sa_column=Column(BigInteger))
    quality: str


class PlaceRecord(SQLModel, table=True):
    __tablename__ = "place_record"
    __table_args__ = (UniqueConstraint("dataset_id", "place_id"),)
    id: str = Field(primary_key=True)
    dataset_id: str = Field(foreign_key="dataset.id", index=True)
    place_id: str = Field(foreign_key="place_identity.id", index=True)
    source_id: str
    name: str
    kind: str
    geom: Any = Field(sa_column=Column(Geometry("POINT", srid=4326), nullable=False))
    municipality_id: str | None = Field(default=None, foreign_key="admin_area.id")
    assignment: str
    candidates: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    grid_x: int | None = Field(default=None, sa_column=Column(Integer,
        Computed('floor(ST_X(ST_Transform(geom,3035))/20000)::integer', persisted=True)))
    grid_y: int | None = Field(default=None, sa_column=Column(Integer,
        Computed('floor(ST_Y(ST_Transform(geom,3035))/20000)::integer', persisted=True)))


class PlaceName(SQLModel, table=True):
    __tablename__ = "place_name"
    id: str = Field(primary_key=True)
    record_id: str = Field(foreign_key="place_record.id", index=True)
    original: str
    normalized: str = Field(index=True)
    reversed: str = Field(index=True)
    primary_name: bool
