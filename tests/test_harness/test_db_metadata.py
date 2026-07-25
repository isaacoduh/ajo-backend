from app.db.base import Base, camel_to_snake, metadata_table_names
from app.db.model_registry import import_all_models
from sqlalchemy import MetaData


def test_base_metadata_has_naming_convention() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert Base.metadata.naming_convention["fk"] == (
        "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )


def test_camel_to_snake_table_names() -> None:
    assert camel_to_snake("JournalEntry") == "journal_entry"
    assert camel_to_snake("Posting") == "posting"


def test_metadata_table_names_defaults_to_base_metadata() -> None:
    assert metadata_table_names() == set(Base.metadata.tables)


def test_metadata_table_names_accepts_explicit_metadata() -> None:
    assert metadata_table_names(MetaData()) == set()


def test_model_registry_is_callable() -> None:
    import_all_models()
