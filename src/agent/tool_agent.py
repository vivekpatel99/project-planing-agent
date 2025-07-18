import operator
from typing import Annotated, TypedDict

from langchain_community.document_loaders import WikipediaLoader
from langchain_core.tools import Tool, tool
from langchain_experimental.utilities import PythonREPL
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field


class PlanningState(TypedDict):
    """State of conversation between Agent and User."""

    project_description: Annotated[str, "Description of the project by User"]
    messages: Annotated[
        list[str], add_messages
    ]  # Clarifying questions to refine the project idea by project info colleciton agent
    project_research: Annotated[
        str, "Research information generated by research agent"
    ]  #
    project_plan: Annotated[list[str], operator.add]  # generated by planning Agent/s
    final_report: Annotated[str, "Generated by Report Generation Agent"]


class SearchQuery(BaseModel):
    """Agent will use this to search for information."""

    query: str = Field(..., description="The query to search for")


class ResearchState(BaseModel):
    """The state of the research agent."""

    result: Annotated[str, "collect final results after research from the Agent"]


# ENHANCEMENT: More explicit instructions for tool usage
SEARCH_INSTRUCTIONS = """You are a helpful assistant that searches for information. 
When a user asks a question that requires current information or web search, 
you MUST use the search_web tool to find the answer. Always search for relevant information before responding."""

llm = ChatOpenAI(model="gpt-4o", temperature=0.0)


@tool
def search_web(state: PlanningState) -> PlanningState:
    """Retrieve docs from the web."""
    print("[INFO] search_web tool called")
    structured_llm = llm_with_tools.with_structured_output(SearchQuery)
    search_query: SearchQuery = structured_llm.invoke(
        [SEARCH_INSTRUCTIONS] + state["messages"]
    )
    tavily_search = TavilySearch(max_results=3)
    search_docs = tavily_search.invoke(search_query.query)
    # format
    formatted_search_docs = [
        f"""<Document href='{doc["url"]}'messages/>\n{doc["content"]}\n<Document>"""
        for doc in search_docs
    ]

    return {"messages": state["messages"] + formatted_search_docs}


@tool
def search_wikipedia(state: PlanningState) -> PlanningState:
    """Retrieve docs from Wikipedia."""
    print("[INFO] search_wikipedia tool called")
    structured_llm = llm_with_tools.with_structured_output(SearchQuery)
    search_query: SearchQuery = structured_llm.invoke(
        [SEARCH_INSTRUCTIONS] + state["messages"]
    )
    search_docs = WikipediaLoader(
        query=search_query.search_query, load_max_docs=2
    ).load()
    # format
    formatted_search_docs = [
        f"""<Document href='{doc["url"]}'/>\n{doc["content"]}\n<Document>"""
        for doc in search_docs
    ]

    state.project_plan = [formatted_search_docs]
    return {"messages": state["messages"] + formatted_search_docs}


python_repl = PythonREPL()
# You can create the tool to pass to an agent
repl_tool = Tool(
    name="python_repl",
    description="A Python shell. Use this to execute python commands. Input should be a valid python command. If you want to see the output of a value, you should print it out with `print(...)`.",
    func=python_repl.run,
)
TOOLS = [search_web, search_wikipedia, repl_tool]
llm_with_tools = llm.bind_tools(TOOLS)


def research_agent(state: PlanningState) -> PlanningState:
    """Understand conversation and user web tools or python to peform research."""
    print("[INFO] research_agent called")
    msg_history = state["messages"]

    result = llm_with_tools.invoke(msg_history)
    return {"result": [result]}


research_agent_graph = StateGraph(
    state_schema=PlanningState, output_schema=ResearchState
)

research_agent_graph.add_node("research_agent", research_agent)
research_agent_graph.add_node("tools", ToolNode(TOOLS))

research_agent_graph.add_edge(START, "research_agent")
research_agent_graph.add_conditional_edges("research_agent", tools_condition)
research_agent_graph.add_edge("tools", "research_agent")


research_agent_workflow = research_agent_graph.compile(
    name="Research Agent",
)

result = research_agent_workflow.invoke(
    {"messages": ["what is latest version of python"]}
)
print(result)
