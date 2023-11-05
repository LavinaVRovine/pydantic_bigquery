import json
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, List, Optional, get_args
from uuid import UUID, uuid4

from pydantic.fields import ComputedFieldInfo
from google.cloud import bigquery
from pydantic import BaseModel, Extra, Field

from pydantic.fields import FieldInfo
from .constants import BigQueryMode
from types import UnionType, NoneType


class BigQueryModelBase(BaseModel):
    __TABLE_NAME__: str
    __PARTITION_FIELD__: Optional[str] = None
    __CLUSTERING_FIELDS__: List[str] = []

    class Config:
        extra = Extra.forbid
        validate_all = True
        validate_assignment = True

    def get_bigquery_schema(self) -> List[bigquery.SchemaField]:
        return [self._get_schema_field(field, name=k) for k, field in self.model_fields.items() if not field.exclude] + [self._get_schema_field(field, name=k) for k, field in self.model_computed_fields.items()]

    @classmethod
    def _get_schema_field(cls, field: FieldInfo | ComputedFieldInfo, name: str) -> bigquery.SchemaField:
        schema_type = cls._get_schema_field_type(field)
        schema_mode = cls._get_schema_field_mode(field)
        inner_fields = cls._get_schema_inner_fields(field)
        return bigquery.SchemaField(
            name=name,
            field_type=str(schema_type.value),
            mode=str(schema_mode.value),
            fields=inner_fields,
        )

    @classmethod
    def get_field_type(cls, field: FieldInfo | ComputedFieldInfo):
        type__ = cls._get_fields_type(field)
        if type(type__) == UnionType:
            args_non_none = [t for t in get_args(type__) if t != NoneType]
            if len(args_non_none) > 1:
                raise NotImplementedError
            return args_non_none[0]
        return type__

    @classmethod
    def _get_fields_type(cls, field: FieldInfo | ComputedFieldInfo):
        try:
            return field.annotation
        except AttributeError:
            return field.return_type

    @classmethod
    def _get_schema_field_type(
        cls, field: FieldInfo | ComputedFieldInfo,
    ) -> bigquery.enums.SqlTypeNames:

        if cls.get_field_type(field) in (str, UUID) or issubclass(cls.get_field_type(field), Enum):
            return bigquery.enums.SqlTypeNames.STRING
        if cls.get_field_type(field) == int:
            return bigquery.enums.SqlTypeNames.INTEGER
        if cls.get_field_type(field) == float:
            return bigquery.enums.SqlTypeNames.FLOAT
        if cls.get_field_type(field) == bool:
            return bigquery.enums.SqlTypeNames.BOOLEAN
        if cls.get_field_type(field) == date:
            return bigquery.enums.SqlTypeNames.DATE
        if cls.get_field_type(field) == datetime:
            return bigquery.enums.SqlTypeNames.TIMESTAMP
        try:
            if issubclass(cls.get_field_type(field), BaseModel):
                return bigquery.enums.SqlTypeNames.RECORD
        except TypeError:
            print()

        raise NotImplementedError(f"Unknown type: {field}")

    @classmethod
    def _get_schema_inner_fields(cls, field: FieldInfo | ComputedFieldInfo) -> List[bigquery.SchemaField]:
        if issubclass(cls.get_field_type(field), BaseModel):
            # FIXME:
            return cls.get_bigquery_schema(field)
        return []

    @classmethod
    def _get_schema_field_mode(cls, field: FieldInfo | ComputedFieldInfo) -> BigQueryMode:
        try:
            if not field.is_required():
                return BigQueryMode.NULLABLE
            return BigQueryMode.REQUIRED
        except AttributeError:
            if type(field.return_type) == UnionType:
                if any([t for t in get_args(field.return_type) if t == NoneType]):
                    return BigQueryMode.NULLABLE
            return BigQueryMode.REQUIRED

        if field.shape == SHAPE_SINGLETON:
            if field.allow_none:
                return BigQueryMode.NULLABLE
            return BigQueryMode.REQUIRED

        if field.shape in (
            SHAPE_LIST,
            SHAPE_SET,
            SHAPE_TUPLE,
        ):
            if not field.allow_none:
                return BigQueryMode.REPEATED

        raise NotImplementedError(f"Unknown combination: shape={field.shape}, required={field.required}")

    def bq_dict(self) -> Any:
        # Conversion hack = Use pydantic encoders (datetime, enum -> str)
        return json.loads(self.json())


class BigQueryModel(BigQueryModelBase):
    insert_id: UUID = Field(default_factory=uuid4)
    inserted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
