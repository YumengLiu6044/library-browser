from browser_use import BrowserProfile, Agent
from browser_use.llm import UserMessage, SystemMessage
from browser_use.llm.deepseek.chat import ChatDeepSeek
from bs4 import BeautifulSoup
import re
from pydantic import ValidationError
from browser_manager import BrowserManager
from constants import DEEPSEEK_API_KEY, MODEL_BASE_URL, DEEPSEEK_MODEL
from models import *
from utils import clean_page, resolve_href


class LibraryExplorer:
	def __init__(self, browser_manager: BrowserManager):
		self.llm = ChatDeepSeek(
			base_url=MODEL_BASE_URL,
			model=DEEPSEEK_MODEL,
			api_key=DEEPSEEK_API_KEY
		)

		self.browser_profile = BrowserProfile(
			minimum_wait_page_load_time=1,
			wait_between_actions=0.2,
			headless=True,
		)

		self.common_agent_params = {
			"browser_profile": self.browser_profile,
			"llm": self.llm,
			"use_vision": False,
			"use_judge": False,
		}

		self.browser_manager = browser_manager

	def _launch_agent(self, **kwargs) -> Agent:
		return Agent(
			**self.common_agent_params,
			**kwargs
		)

	async def generate_search_plan(self, lib_url: str, max_steps=10) -> SearchPlan:
		initial_actions = [{"navigate": {"url": lib_url, "new_tab": True}}]
		task = """
			You are an LLM used to reverse engineer library catalog search systems.

			Workflow:
			1. Find if the page has a href to the library catalog page. If so, navigate to it.
			2. Find the input box used to search the catalogue
			3. Use input to fill the input box with "good"
			4. Analyze the results and return a SearchPlan object. 
				If you are unable to find a search query, or if the query doesn't return an HTML object, set is_valid to False.
		"""

		_agent = self._launch_agent(
			task=task,
			output_model_schema=SearchPlan,
			initial_actions=initial_actions
		)

		response = await _agent.run(max_steps=max_steps)
		plan = response.structured_output
		plan.lib_url = lib_url
		return plan

	async def execute_valid_search(self, search_plan: SearchPlan, query, max_chars = 100000) -> str:
		formatted_query = search_plan.query.format(query)
		corpus = await self.browser_manager.fetch_hydrated_html(formatted_query)
		cleaned_corpus = clean_page(corpus)
		return cleaned_corpus[:max_chars]

	async def execute_llm_search(self, search_plan: SearchPlan, max_chars = 100000) -> str:
		task = f"""
			You are an LLM used to explore library catalog search systems.

			Workflow:
			1. Find if the page has a href to the library catalog page. If so, navigate to it.
			2. Find the input box used to search the catalogue
			3. Use input to fill the input box with "good"
			4. Return the HTML content of the search result page as is.
		"""
		initial_steps = [{"navigate": {"url": search_plan.lib_url, "new_tab": True}}]

		class SearchResult(BaseModel):
			corpus: str

		_agent = self._launch_agent(
			task=task,
			output_model_schema=SearchResult,
			initial_actions=initial_steps
		)

		response = await _agent.run(max_steps=10)
		corpus = response.structured_output.corpus
		corpus = clean_page(corpus)
		return corpus[:max_chars]

	async def execute_search(self, search_plan: SearchPlan, query, max_chars = 100000) -> str:
		if search_plan.is_valid and search_plan.query:
			return await self.execute_valid_search(search_plan, query, max_chars)
		else:
			# Fallback to Browser Use agent
			return await self.execute_llm_search(search_plan, max_chars)

	async def generate_extraction_plan(self, _cleaned_corpus: str) -> ExtractionPlan:
		prompt = f"""
		You are an expert HTML extraction engineer.

		Your task is to analyze HTML from a library search results page
		and generate a robust ArtifactExtractor.

		If you are unable to extract any useful information, return a response with is_parsable set to False.

		IMPORTANT RULES:
		- NEVER hallucinate selectors
		- ONLY use selectors that exist in the HTML
		- prefer semantic classes over positional selectors
		- avoid nth-child unless absolutely necessary
		- avoid brittle selectors

		"""

		messages = [
			SystemMessage(content=prompt, role="system"),
			UserMessage(content=_cleaned_corpus, role="user"),
		]

		response = await self.llm.ainvoke(
			messages=messages,
			output_format=ExtractionPlan,
		)
		return response.completion

	@staticmethod
	def extract_parsable_artifact(corpus: str, extraction_plan: ExtractionPlan, catalog_url: str) -> list[Artifact]:
		soup = BeautifulSoup(corpus, "html.parser")
		artifact_list = []
		for result_node in soup.select(extraction_plan.artifact_root):
			artifact = Artifact()
			for field_name, field_extractor in extraction_plan.field_extractor:
				extracted = None

				if field_extractor.mode == ExtractionMode.ATTRIBUTE:
					if selected_child := result_node.select_one(field_extractor.selector):
						extracted = selected_child.get(field_extractor.attribute)
						if field_extractor.attribute in {"href", "src"}:
							extracted = resolve_href(catalog_url, extracted)

				elif field_extractor.mode == ExtractionMode.TEXT:
					if selected_child := result_node.select_one(field_extractor.selector):
						extracted = selected_child.text
						if field_extractor.regex and (matches := re.match(field_extractor.regex, extracted)):
							extracted = matches.group(0)

				extracted = (extracted or "").strip()
				setattr(artifact, field_name, extracted)

			artifact_list.append(artifact)

		return artifact_list

	async def extract_with_llm(self, corpus, catalog_url: str, max_retry=3) -> list[Artifact]:
		class OutputSchema(BaseModel):
			artifacts: list[Artifact]

		prompt = f"""
		You are an expert HTML extraction engineer.

		Your task is to analyze HTML from a library search results page
		and generate a robust list of Artifact objects.

		If you are unable to extract any useful information, return an empty list.

		IMPORTANT RULES:
		- NEVER hallucinate values
		- ONLY output real and correct information
		- MUST output in the correct schema

		JSON output schema:
		{OutputSchema.model_json_schema()}
		"""

		messages = [
			SystemMessage(content=prompt, role="system"),
			UserMessage(content=corpus, role="user"),
		]
		for _ in range(max_retry):
			response = await self.llm.ainvoke(
				messages=messages,
				output_format=OutputSchema,
			)
			try:
				artifacts = response.completion.artifacts
			except ValidationError:
				continue

			for index, artifact in enumerate(artifacts):
				for key, val in artifact:
					val = val.strip() if isinstance(val, str) else val
					setattr(
						artifacts[index],
						key,
						resolve_href(catalog_url, val) if key in {"url", "img_url"} else val
					)

			return artifacts

		return []

	async def execute_extraction(self, corpus: str, plan: ExtractionPlan, catalog_url: str) -> list[Artifact]:
		if plan.is_parsable:
			artifact_list = self.extract_parsable_artifact(corpus, plan, catalog_url)

		else:
			# Use LLM fallback
			artifact_list = await self.extract_with_llm(corpus, catalog_url)

		return artifact_list
