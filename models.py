import enum
from typing import Optional, Annotated

from pydantic import BaseModel, Field, create_model


class Artifact(BaseModel):
	title: Optional[str] = None
	author: Optional[str] = None
	url: Optional[str] = None
	img_url: Optional[str] = None
	availability_status: Optional[str] = None
	availability_count: Optional[str] = None
	media_format: Optional[str] = None
	publication_date: Optional[str] = None


class ExtractionMode(str, enum.Enum):
	TEXT = "text"
	ATTRIBUTE = "attribute"


class FieldConvertor(BaseModel):
	mode: Annotated[
		ExtractionMode,
		Field(description="Specifies if the targeted field should be extracted from a tag's attribute or text content")
	] = ExtractionMode.TEXT

	selector: Annotated[
		str,
		Field(description="CSS selector relative to artifact root. MUST NOT be None")
	]

	attribute: Annotated[
		Optional[str],
		Field(description="Optional HTML attribute to extract")
	] = None

	regex: Annotated[
		Optional[str],
		Field(description="Optional regex to clean extracted text. Must produce exactly 1 match group")
	] = None


def build_field_extractor(source_model: type[BaseModel]):
	fields = {}
	for field_name, field_info in source_model.model_fields.items():
		description = (
			f"Extractor object used to extract the '{field_name}' field "
			f"from an artifact element. Will be used after the root selector has been applied"
		)

		fields[field_name] = (
			Annotated[
				Optional[FieldConvertor],
				Field(description=description),
			],
			None,
		)

	return create_model("FieldExtractor", **fields)


class SearchPlan(BaseModel):
	is_valid: Annotated[bool, Field(description="Whether the query is valid")]
	lib_url: Annotated[str, Field(description="The library's home URL")]
	catalog_url: Annotated[str, Field(description="The catalog URL")]
	query: Annotated[str, Field(description="The request template string. Only template for the query string. Preserve all other parameters. For example, https://google.com/?q={}")]


class ExtractionPlan(BaseModel):
	is_parsable: Annotated[
		bool,
		Field(description="Whether a valid ArtifactExtractor model can be used to extract the artifacts from the response.")
	]

	artifact_root: Annotated[
		Optional[str],
		Field(
			description="The root selector for a singular library item."
		),
	] = None

	field_extractor: Annotated[
		build_field_extractor(Artifact),
		Field(description="A dictionary that maps target fields with their respective field extractors")
	]
