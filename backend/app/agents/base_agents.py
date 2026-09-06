"""
Base DSPy agents for dataset analysis and interaction.
Inspired by Auto-Analyst's agentic approach.
"""

import dspy
from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class DatasetInfo(dspy.Signature):
    """Extract and summarize key information about a dataset."""
    dataset_description = dspy.InputField(desc="Description of the dataset contents and structure")
    goal = dspy.InputField(desc="User's goal or question about the dataset")

    summary = dspy.OutputField(desc="Clear summary of dataset characteristics and relevant insights")
    suggested_actions = dspy.OutputField(desc="List of suggested analysis actions based on the data")

class DataPreprocessingAgent(dspy.Signature):
    """Agent specialized in data cleaning and preprocessing using pandas and numpy."""

    goal = dspy.InputField(desc="User-defined goal which includes information about data and task they want to perform")
    dataset = dspy.InputField(desc="Provides information about the data in the data frame. Only use column names and dataframe_name as in this context")
    plan_instructions = dspy.InputField(desc="Agent-level instructions about what to create and receive", default="")

    code = dspy.OutputField(desc="Generated Python code for data preprocessing and cleaning")
    summary = dspy.OutputField(desc="A concise bullet-point summary of preprocessing steps performed and key results")

class StatisticalAnalyticsAgent(dspy.Signature):
    """Agent specialized in statistical analysis using statsmodels and scipy."""

    goal = dspy.InputField(desc="User-defined goal which includes information about data and task they want to perform")
    dataset = dspy.InputField(desc="Provides information about the data in the data frame. Only use column names and dataframe_name as in this context")
    plan_instructions = dspy.InputField(desc="Agent-level instructions about what to create and receive", default="")

    code = dspy.OutputField(desc="Generated Python code for statistical analysis")
    summary = dspy.OutputField(desc="A concise bullet-point summary of statistical analysis performed and key findings")

class MachineLearningAgent(dspy.Signature):
    """Agent specialized in machine learning using scikit-learn."""

    goal = dspy.InputField(desc="User-defined goal which includes information about data and task they want to perform")
    dataset = dspy.InputField(desc="Provides information about the data in the data frame. Only use column names and dataframe_name as in this context")
    plan_instructions = dspy.InputField(desc="Agent-level instructions about what to create and receive", default="")

    code = dspy.OutputField(desc="Generated Python code for machine learning analysis")
    summary = dspy.OutputField(desc="A concise bullet-point summary of ML analysis performed and key results")

class DataVisualizationAgent(dspy.Signature):
    """
    You are a data visualization agent that generates plotly visualizations for dataset analysis.
    Your primary responsibility is to create interactive charts and graphs using plotly.

    You are provided with:
    * **goal**: A user-defined goal outlining the type of visualization (e.g., "create bar chart of sales by category").
    * **dataset**: The dataset information including dataframe name (typically 'df') and column details.
    * **styling_index**: Specific styling instructions for consistent visualization formatting.
    * **plan_instructions**: Optional instructions about variables to create and use.

    ### Key Requirements:
    1. **Use Plotly Only**: Generate visualizations using plotly.express or plotly.graph_objects.
    2. **Use fig.show()**: Always end visualizations with fig.show() to display them.
    3. **Dataset Sampling**: If dataset has >50,000 rows, sample to 5,000 rows for performance:
       ```python
       if len(df) > 50000:
           df = df.sample(5000, random_state=42)
       ```
    4. **Styling**: Follow styling_index instructions for consistent formatting.
    5. **No Data Creation**: Only use the provided dataset, never create fake data.

    ### Visualization Guidelines:
    - Use plotly_white template
    - Set appropriate figure size (width=800, height=600)
    - Include clear titles and axis labels
    - Use distinct colors for categories
    - Apply proper number formatting (K for thousands, M for millions)
    - Add hover information where appropriate

    ### Output Format:
    - Generate clean, executable Python code
    - Always end with fig.show()
    - Include proper imports (plotly.express as px, plotly.graph_objects as go)

    Respond with code in English and summary in user's language.
    """

    goal = dspy.InputField(desc="User-defined goal for visualization (e.g., 'create scatter plot of price vs sales')")
    dataset = dspy.InputField(desc="Dataset information including dataframe name and column details")
    plan_instructions = dspy.InputField(desc="Agent-level instructions about what to create and receive", default="")
    styling_index = dspy.InputField(desc='Styling instructions for consistent plot formatting and layout')

    code = dspy.OutputField(desc="Plotly Python code that ends with fig.show() to display the visualization")
    summary = dspy.OutputField(desc="A concise bullet-point summary of the visualization created and key insights")

class PlannerAgent(dspy.Signature):
    """Agent that routes queries to appropriate specialized agents and coordinates workflows."""

    goal = dspy.InputField(desc="User's goal or question about the dataset")
    dataset = dspy.InputField(desc="Information about the dataset structure and contents")
    available_agents = dspy.InputField(desc="List of available specialized agents")

    selected_agent = dspy.OutputField(desc="The most appropriate agent for handling this task")
    plan_instructions = dspy.OutputField(desc="Specific instructions for the selected agent")
    reasoning = dspy.OutputField(desc="Explanation of why this agent was selected")

class AgentOrchestrator:
    """Orchestrates multiple agents for complex data analysis workflows."""

    def __init__(self, llm_config: Dict[str, Any]):
        """Initialize the orchestrator with LLM configuration."""
        self.llm_config = llm_config
        self.available_agents = {
            "preprocessing_agent": DataPreprocessingAgent,
            "statistical_analytics_agent": StatisticalAnalyticsAgent,
            "ml_agent": MachineLearningAgent,
            "data_viz_agent": DataVisualizationAgent
        }

        # Configure DSPy with the provided LLM
        self._configure_dspy()

        # Initialize agent modules
        self.planner = dspy.ChainOfThought(PlannerAgent)
        self.preprocessing_module = dspy.ChainOfThought(DataPreprocessingAgent)
        self.statistics_module = dspy.ChainOfThought(StatisticalAnalyticsAgent)
        self.ml_module = dspy.ChainOfThought(MachineLearningAgent)
        self.visualization_module = dspy.ChainOfThought(DataVisualizationAgent)

    def _configure_dspy(self):
        """Configure DSPy with appropriate LLM."""
        try:
            import os

            # Try to use OpenAI if available
            if self.llm_config.get("api_key") or os.getenv("OPENAI_API_KEY"):
                import dspy

                # Configure with OpenAI
                turbo = dspy.OpenAI(
                    model=self.llm_config.get("model", "gpt-3.5-turbo"),
                    api_key=self.llm_config.get("api_key") or os.getenv("OPENAI_API_KEY"),
                    temperature=self.llm_config.get("temperature", 0.1),
                    max_tokens=self.llm_config.get("max_tokens", 2000)
                )
                dspy.settings.configure(lm=turbo)
                logger.info("DSPy configured with OpenAI")

            # Try Google Gemini if available
            elif os.getenv("GOOGLE_API_KEY"):
                import dspy
                from dspy import GoogleGenerativeAI

                gemini = GoogleGenerativeAI(
                    model="gemini-pro",
                    api_key=os.getenv("GOOGLE_API_KEY"),
                    temperature=self.llm_config.get("temperature", 0.1)
                )
                dspy.settings.configure(lm=gemini)
                logger.info("DSPy configured with Google Gemini")

            else:
                logger.warning("No LLM API key found. DSPy agents may not work properly.")

        except Exception as e:
            logger.error(f"Failed to configure DSPy LLM: {str(e)}")
            # Continue without LLM configuration - will fail at runtime

    def route_query(self, goal: str, dataset_info: str, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Route a query to the appropriate agent, either specified or auto-selected.

        Args:
            goal: User's goal or question
            dataset_info: Information about the dataset
            agent_name: Optional specific agent name (e.g., '@preprocessing_agent')

        Returns:
            Dictionary containing agent response with code and summary
        """
        try:
            if agent_name and agent_name.startswith('@'):
                # Remove @ prefix and route to specific agent
                agent_name = agent_name[1:]
                return self._execute_specific_agent(agent_name, goal, dataset_info)
            else:
                # Use planner to auto-select agent
                return self._auto_route_query(goal, dataset_info)

        except Exception as e:
            logger.error(f"Error in query routing: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to process query with agents"
            }

    def _auto_route_query(self, goal: str, dataset_info: str) -> Dict[str, Any]:
        """Use planner agent to automatically route query."""
        try:
            # Get available agents list
            agents_list = list(self.available_agents.keys())

            # Use planner to select appropriate agent
            plan_result = self.planner(
                goal=goal,
                dataset=dataset_info,
                available_agents=", ".join(agents_list)
            )

            selected_agent = plan_result.selected_agent
            plan_instructions = plan_result.plan_instructions
            reasoning = plan_result.reasoning

            # Execute the selected agent
            result = self._execute_specific_agent(
                selected_agent,
                goal,
                dataset_info,
                plan_instructions
            )

            # Add planner information to result
            result["planner"] = {
                "selected_agent": selected_agent,
                "reasoning": reasoning,
                "plan_instructions": plan_instructions
            }

            return result

        except Exception as e:
            logger.error(f"Error in auto-routing: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to auto-route query"
            }

    def _execute_specific_agent(self, agent_name: str, goal: str, dataset_info: str, plan_instructions: str = "") -> Dict[str, Any]:
        """Execute a specific agent."""
        try:
            # For visualization agent, use direct Gemini API if DSPy fails
            if agent_name == "data_viz_agent":
                return self._execute_visualization_agent_direct(goal, dataset_info, plan_instructions)

            # Try DSPy-based execution for other agents
            if agent_name == "preprocessing_agent":
                result = self.preprocessing_module(
                    goal=goal,
                    dataset=dataset_info,
                    plan_instructions=plan_instructions
                )
            elif agent_name == "statistical_analytics_agent":
                result = self.statistics_module(
                    goal=goal,
                    dataset=dataset_info,
                    plan_instructions=plan_instructions
                )
            elif agent_name == "ml_agent":
                result = self.ml_module(
                    goal=goal,
                    dataset=dataset_info,
                    plan_instructions=plan_instructions
                )
            else:
                raise ValueError(f"Unknown agent: {agent_name}")

            return {
                "success": True,
                "agent": agent_name,
                "code": result.code,
                "summary": result.summary,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error executing agent {agent_name}: {str(e)}")

            # Fallback for visualization agent
            if agent_name == "data_viz_agent":
                logger.info("Falling back to direct Gemini API for visualization")
                return self._execute_visualization_agent_direct(goal, dataset_info, plan_instructions)

            return {
                "success": False,
                "agent": agent_name,
                "error": str(e),
                "message": f"Failed to execute {agent_name}"
            }

    def _execute_visualization_agent_direct(self, goal: str, dataset_info: str, plan_instructions: str = "") -> Dict[str, Any]:
        """Execute visualization agent using direct Gemini API."""
        try:
            import os
            import google.generativeai as genai

            # Configure Gemini
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not found")

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')

            # Create prompt
            prompt = f'''You are a data visualization expert. Generate Python code using plotly to create visualizations.

Dataset Information:
{dataset_info}

User Goal: {goal}

Instructions: {plan_instructions if plan_instructions else "Create appropriate visualizations based on the data"}

CRITICAL: The dataframe 'df' is already loaded with the columns exactly as described above. Use the EXACT column names provided (case-sensitive).

Generate clean, executable Python code that:
1. Uses plotly.express (import as px) or plotly.graph_objects (import as go)
2. Assumes the dataframe 'df' is already loaded
3. Uses EXACT column names as provided in the dataset info (typically lowercase)
4. Creates informative and visually appealing charts
5. Uses appropriate chart types based on the data
6. Includes proper titles, labels, and formatting
7. MUST end with fig.show() to display the visualization
8. If the dataset has many rows (>5000), sample it: df = df.sample(min(5000, len(df)), random_state=42)

Example: If columns are 'age', 'salary', 'department' - use exactly these names, NOT 'Age', 'Salary', 'Department'

Response format (use exactly this format):
CODE:
```python
# Your Python code here
```
SUMMARY:
- Brief bullet points about what was visualized
- Key insights or patterns shown
'''

            # Generate response
            response = model.generate_content(prompt)
            text = response.text

            # Extract code and summary
            code = ""
            summary = ""

            if "CODE:" in text and "```python" in text:
                code_start = text.find("```python") + 9
                code_end = text.find("```", code_start)
                if code_end > code_start:
                    code = text[code_start:code_end].strip()

            if "SUMMARY:" in text:
                summary_start = text.find("SUMMARY:") + 8
                summary = text[summary_start:].strip()

            # If no code was extracted, try a simpler extraction
            if not code and "```" in text:
                parts = text.split("```")
                for part in parts:
                    if part.strip().startswith("python"):
                        code = part[6:].strip()
                        break

            # Ensure we have some code
            if not code:
                # Generate a default visualization
                code = f'''import plotly.express as px
import pandas as pd

# Create a simple bar chart as fallback
# Assuming df is already loaded
if 'df' in locals():
    # Try to identify numeric and categorical columns
    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()

    if len(categorical_cols) > 0 and len(numeric_cols) > 0:
        # Create bar chart of first numeric column by first categorical column
        fig = px.bar(df, x=categorical_cols[0], y=numeric_cols[0],
                     title=f"{{numeric_cols[0]}} by {{categorical_cols[0]}}")
    else:
        # Create histogram of first column
        first_col = df.columns[0]
        fig = px.histogram(df, x=first_col, title=f"Distribution of {{first_col}}")

    fig.show()
else:
    print("No dataframe found")
'''
                summary = "Generated default visualization based on available data"

            return {
                "success": True,
                "agent": "data_viz_agent",
                "code": code,
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in direct visualization agent: {str(e)}")
            return {
                "success": False,
                "agent": "data_viz_agent",
                "error": str(e),
                "message": f"Failed to generate visualization: {str(e)}"
            }

    def _get_visualization_styling(self) -> str:
        """Get styling instructions for visualizations."""
        return """
        For visualization styling:
        - Use plotly_white template for all charts
        - Set axes line width to 0.2 and grid width to 1
        - Always include titles and bold axis labels using HTML tags
        - Display large numbers in K (thousands) or M (millions) format
        - Show percentages with 2 decimal places and % sign
        - Default chart size: height=600, width=800
        - Use multiple colors for multi-line charts
        - Annotate min/max values on line charts
        - Annotate values on bar charts
        - Use bin_size=50 for histograms
        """

def create_agent_orchestrator(llm_config: Dict[str, Any]) -> AgentOrchestrator:
    """Factory function to create and configure agent orchestrator."""
    return AgentOrchestrator(llm_config)