"""
Data Visualization Service using LIDA (Language Interface for Data Analysis)
Provides automatic visualization generation and data insights
"""

import logging
import json
import base64
import io
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime
import traceback

if not hasattr(np, "unicode_"):
    np.unicode_ = np.str_

# Visualization libraries
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder

# LIDA for automatic visualization
try:
    from lida import Manager, TextGenerationConfig, llm
    LIDA_AVAILABLE = True
except ImportError:
    LIDA_AVAILABLE = False
    logging.warning("LIDA not available. Install with: pip install lida")

logger = logging.getLogger(__name__)


def sanitize_visualization_payload(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): sanitize_visualization_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_visualization_payload(item) for item in obj]
    if isinstance(obj, tuple):
        return [sanitize_visualization_payload(item) for item in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return sanitize_visualization_payload(obj.tolist())
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    try:
        if bool(pd.isna(obj)):
            return None
    except (TypeError, ValueError):
        pass
    return obj


class DataVisualizationService:
    """Service for generating data visualizations and insights"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.lida_manager = None
        
        if LIDA_AVAILABLE and api_key:
            try:
                # Initialize LIDA with Gemini
                self.text_gen_config = TextGenerationConfig(
                    n=1,
                    temperature=0.5,
                    model="gemini/gemini-pro",
                    use_cache=True
                )
                
                # Create LIDA manager
                self.lida_manager = Manager(text_gen=llm(provider="google", api_key=api_key))
                logger.info("LIDA Manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize LIDA: {e}")
                self.lida_manager = None
    
    def analyze_dataset(self, data: pd.DataFrame, dataset_name: str = "Dataset") -> Dict[str, Any]:
        """Analyze dataset and generate insights"""
        try:
            analysis = {
                "dataset_name": dataset_name,
                "basic_stats": {},
                "data_quality": {},
                "column_analysis": {},
                "correlations": {},
                "recommendations": []
            }
            
            # Basic statistics
            analysis["basic_stats"] = {
                "rows": len(data),
                "columns": len(data.columns),
                "memory_usage": f"{data.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB",
                "column_types": data.dtypes.value_counts().to_dict()
            }
            
            # Data quality analysis
            analysis["data_quality"] = {
                "missing_values": data.isnull().sum().to_dict(),
                "missing_percentage": (data.isnull().sum() / len(data) * 100).round(2).to_dict(),
                "duplicated_rows": int(data.duplicated().sum()),
                "unique_values": {col: data[col].nunique() for col in data.columns}
            }
            
            # Column-wise analysis
            for col in data.columns:
                col_analysis = {"type": str(data[col].dtype)}
                
                if pd.api.types.is_numeric_dtype(data[col]):
                    col_analysis.update({
                        "mean": float(data[col].mean()) if not data[col].isna().all() else None,
                        "median": float(data[col].median()) if not data[col].isna().all() else None,
                        "std": float(data[col].std()) if not data[col].isna().all() else None,
                        "min": float(data[col].min()) if not data[col].isna().all() else None,
                        "max": float(data[col].max()) if not data[col].isna().all() else None,
                        "q25": float(data[col].quantile(0.25)) if not data[col].isna().all() else None,
                        "q75": float(data[col].quantile(0.75)) if not data[col].isna().all() else None
                    })
                elif pd.api.types.is_datetime64_any_dtype(data[col]):
                    col_analysis.update({
                        "min_date": str(data[col].min()),
                        "max_date": str(data[col].max()),
                        "date_range": str(data[col].max() - data[col].min())
                    })
                else:
                    # Categorical data
                    value_counts = data[col].value_counts()
                    col_analysis.update({
                        "unique_values": int(data[col].nunique()),
                        "top_values": value_counts.head(5).to_dict() if len(value_counts) > 0 else {},
                        "mode": str(data[col].mode()[0]) if not data[col].mode().empty else None
                    })
                
                analysis["column_analysis"][col] = col_analysis
            
            # Correlation analysis for numeric columns
            numeric_cols = data.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 1:
                corr_matrix = data[numeric_cols].corr()
                
                # Find strong correlations
                strong_correlations = []
                for i in range(len(corr_matrix.columns)):
                    for j in range(i+1, len(corr_matrix.columns)):
                        corr_value = corr_matrix.iloc[i, j]
                        if abs(corr_value) > 0.7:  # Strong correlation threshold
                            strong_correlations.append({
                                "column1": corr_matrix.columns[i],
                                "column2": corr_matrix.columns[j],
                                "correlation": round(corr_value, 3)
                            })
                
                analysis["correlations"] = {
                    "matrix": corr_matrix.round(3).to_dict(),
                    "strong_correlations": strong_correlations
                }
            
            # Generate recommendations
            recommendations = []
            
            # Check for missing data
            missing_cols = [col for col, pct in analysis["data_quality"]["missing_percentage"].items() if pct > 10]
            if missing_cols:
                recommendations.append(f"Consider handling missing values in columns: {', '.join(missing_cols)}")
            
            # Check for duplicates
            if analysis["data_quality"]["duplicated_rows"] > 0:
                recommendations.append(f"Dataset contains {analysis['data_quality']['duplicated_rows']} duplicate rows")
            
            # Check for high cardinality
            high_cardinality = [col for col, unique in analysis["data_quality"]["unique_values"].items() 
                              if unique > len(data) * 0.9 and unique > 100]
            if high_cardinality:
                recommendations.append(f"High cardinality columns detected: {', '.join(high_cardinality)}")
            
            # Check for strong correlations
            if analysis["correlations"].get("strong_correlations"):
                recommendations.append(f"Found {len(analysis['correlations']['strong_correlations'])} strong correlations between columns")
            
            analysis["recommendations"] = recommendations
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing dataset: {e}")
            return {
                "error": str(e),
                "dataset_name": dataset_name,
                "basic_stats": {"rows": len(data), "columns": len(data.columns)}
            }
    
    def generate_visualizations_with_lida(
        self, 
        data: pd.DataFrame, 
        query: str = "Generate useful visualizations for this dataset",
        max_visualizations: int = 4
    ) -> List[Dict[str, Any]]:
        """Generate visualizations using LIDA"""
        if not LIDA_AVAILABLE or not self.lida_manager:
            logger.warning("LIDA not available, falling back to standard visualizations")
            return self.generate_standard_visualizations(data)
        
        try:
            visualizations = []
            
            # Summarize the data with LIDA
            summary = self.lida_manager.summarize(
                data,
                summary_method="default",
                textgen_config=self.text_gen_config
            )
            
            # Generate visualization goals based on the query
            goals = self.lida_manager.goals(
                summary,
                n=max_visualizations,
                textgen_config=self.text_gen_config
            )
            
            # Generate visualizations for each goal
            for i, goal in enumerate(goals):
                try:
                    # Generate visualization code
                    charts = self.lida_manager.visualize(
                        summary=summary,
                        goal=goal,
                        textgen_config=self.text_gen_config,
                        library="plotly"  # Use plotly for interactive charts
                    )
                    
                    if charts and len(charts) > 0:
                        chart = charts[0]
                        
                        # Execute the generated code to create the visualization
                        viz_result = self._execute_visualization_code(
                            chart.code,
                            data,
                            goal.question
                        )
                        
                        if viz_result:
                            visualizations.append(viz_result)
                            
                except Exception as e:
                    logger.error(f"Error generating visualization {i+1}: {e}")
                    continue
            
            # If LIDA fails or produces no results, fall back to standard visualizations
            if not visualizations:
                logger.info("LIDA produced no visualizations, using standard ones")
                return self.generate_standard_visualizations(data)
            
            return visualizations
            
        except Exception as e:
            logger.error(f"LIDA visualization generation failed: {e}")
            return self.generate_standard_visualizations(data)
    
    def generate_chat_visualizations(
        self,
        data: pd.DataFrame,
        query: str = "",
        max_visualizations: int = 3
    ) -> List[Dict[str, Any]]:
        visualizations = self.generate_standard_visualizations(data)
        if not visualizations:
            return []

        query_lower = query.lower()
        priority_map = []
        if any(word in query_lower for word in ["trend", "time", "over time", "line"]):
            priority_map.extend(["time_series", "line"])
        if any(word in query_lower for word in ["distribution", "histogram", "spread"]):
            priority_map.extend(["distribution", "box_plot"])
        if any(word in query_lower for word in ["correlation", "relationship", "heatmap"]):
            priority_map.extend(["heatmap", "scatter"])
        if any(word in query_lower for word in ["compare", "category", "bar", "top"]):
            priority_map.extend(["bar_chart", "grouped_bar"])
        if "pie" in query_lower or "share" in query_lower:
            priority_map.append("pie_chart")

        if priority_map:
            def score(viz: Dict[str, Any]) -> int:
                viz_type = str(viz.get("type", "")).lower()
                title = str(viz.get("title", "")).lower()
                for index, keyword in enumerate(priority_map):
                    if keyword in viz_type or keyword in title:
                        return index
                return len(priority_map)

            visualizations = sorted(visualizations, key=score)

        return visualizations[:max(1, max_visualizations)]

    def generate_standard_visualizations(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate enhanced standard visualizations with more chart types"""
        visualizations = []

        try:
            numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
            categorical_cols = data.select_dtypes(include=['object', 'category']).columns.tolist()
            datetime_cols = data.select_dtypes(include=['datetime64']).columns.tolist()

            # 1. Distribution plot for first numeric column with box plot
            if numeric_cols:
                viz = self._create_distribution_plot(data, numeric_cols[0])
                if viz:
                    visualizations.append(viz)

                # Add box plot for outlier detection
                viz = self._create_box_plot(data, numeric_cols[0])
                if viz:
                    visualizations.append(viz)

            # 2. Bar chart for first categorical column
            if categorical_cols:
                viz = self._create_bar_chart(data, categorical_cols[0])
                if viz:
                    visualizations.append(viz)

                # Add pie chart if not too many categories
                if data[categorical_cols[0]].nunique() <= 10:
                    viz = self._create_pie_chart(data, categorical_cols[0])
                    if viz:
                        visualizations.append(viz)

            # 3. Correlation heatmap if multiple numeric columns
            if len(numeric_cols) > 1:
                viz = self._create_correlation_heatmap(data, numeric_cols)
                if viz:
                    visualizations.append(viz)

            # 4. Time series plot if datetime column exists
            if datetime_cols and numeric_cols:
                viz = self._create_time_series_plot(data, datetime_cols[0], numeric_cols[0])
                if viz:
                    visualizations.append(viz)

            # 5. Scatter plot for first two numeric columns
            if len(numeric_cols) >= 2:
                viz = self._create_scatter_plot(data, numeric_cols[0], numeric_cols[1])
                if viz:
                    visualizations.append(viz)

            # 6. Multi-variable analysis if we have numeric and categorical
            if numeric_cols and categorical_cols and len(data) < 1000:
                viz = self._create_grouped_bar_chart(data, categorical_cols[0], numeric_cols[0])
                if viz:
                    visualizations.append(viz)

            # 7. Data summary stats visualization
            if numeric_cols:
                viz = self._create_stats_summary(data, numeric_cols[:5])
                if viz:
                    visualizations.append(viz)

            return visualizations

        except Exception as e:
            logger.error(f"Error generating standard visualizations: {e}")
            return []
    
    def _create_distribution_plot(self, data: pd.DataFrame, column: str) -> Optional[Dict[str, Any]]:
        """Create a distribution plot for a numeric column"""
        try:
            fig = px.histogram(
                data, 
                x=column, 
                nbins=30,
                title=f"Distribution of {column}",
                labels={column: column, 'count': 'Frequency'}
            )
            
            fig.update_layout(
                showlegend=False,
                height=400,
                template='plotly_white'
            )
            
            return {
                "type": "distribution",
                "title": f"Distribution of {column}",
                "description": f"Histogram showing the distribution of values in {column}",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Mean: {data[column].mean():.2f}",
                    f"Median: {data[column].median():.2f}",
                    f"Std Dev: {data[column].std():.2f}"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating distribution plot: {e}")
            return None
    
    def _create_bar_chart(self, data: pd.DataFrame, column: str) -> Optional[Dict[str, Any]]:
        """Create a bar chart for a categorical column"""
        try:
            value_counts = data[column].value_counts().head(10)
            
            fig = px.bar(
                x=value_counts.index,
                y=value_counts.values,
                title=f"Top 10 {column} Values",
                labels={'x': column, 'y': 'Count'}
            )
            
            fig.update_layout(
                height=400,
                template='plotly_white'
            )
            
            return {
                "type": "bar_chart",
                "title": f"Top 10 {column} Values",
                "description": f"Bar chart showing the most frequent values in {column}",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Most common value: {value_counts.index[0]} ({value_counts.values[0]} occurrences)",
                    f"Total unique values: {data[column].nunique()}"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating bar chart: {e}")
            return None
    
    def _create_correlation_heatmap(self, data: pd.DataFrame, numeric_cols: List[str]) -> Optional[Dict[str, Any]]:
        """Create a correlation heatmap"""
        try:
            # Limit to 10 columns for readability
            cols_to_use = numeric_cols[:10]
            corr_matrix = data[cols_to_use].corr()
            
            fig = px.imshow(
                corr_matrix,
                labels=dict(x="Features", y="Features", color="Correlation"),
                x=cols_to_use,
                y=cols_to_use,
                title="Feature Correlation Heatmap",
                color_continuous_scale="RdBu",
                zmin=-1,
                zmax=1
            )
            
            fig.update_layout(
                height=500,
                template='plotly_white'
            )
            
            # Find strong correlations
            strong_corr = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    corr_value = corr_matrix.iloc[i, j]
                    if abs(corr_value) > 0.7:
                        strong_corr.append(f"{corr_matrix.columns[i]} & {corr_matrix.columns[j]}: {corr_value:.2f}")
            
            insights = ["Strong correlations found:"] + strong_corr if strong_corr else ["No strong correlations found"]
            
            return {
                "type": "heatmap",
                "title": "Feature Correlation Heatmap",
                "description": "Correlation matrix showing relationships between numeric features",
                "chart": json.loads(fig.to_json()),
                "insights": insights
            }
        except Exception as e:
            logger.error(f"Error creating correlation heatmap: {e}")
            return None
    
    def _create_time_series_plot(self, data: pd.DataFrame, date_col: str, value_col: str) -> Optional[Dict[str, Any]]:
        """Create a time series plot"""
        try:
            fig = px.line(
                data.sort_values(date_col),
                x=date_col,
                y=value_col,
                title=f"{value_col} Over Time",
                labels={date_col: "Date", value_col: value_col}
            )
            
            fig.update_layout(
                height=400,
                template='plotly_white',
                hovermode='x unified'
            )
            
            return {
                "type": "time_series",
                "title": f"{value_col} Over Time",
                "description": f"Time series plot showing {value_col} trends over {date_col}",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Date range: {data[date_col].min()} to {data[date_col].max()}",
                    f"Average {value_col}: {data[value_col].mean():.2f}"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating time series plot: {e}")
            return None
    
    def _create_scatter_plot(self, data: pd.DataFrame, x_col: str, y_col: str) -> Optional[Dict[str, Any]]:
        """Create a scatter plot"""
        try:
            fig = px.scatter(
                data,
                x=x_col,
                y=y_col,
                title=f"{y_col} vs {x_col}",
                labels={x_col: x_col, y_col: y_col},
                trendline="ols" if len(data) > 10 else None
            )
            
            fig.update_layout(
                height=400,
                template='plotly_white'
            )
            
            # Calculate correlation
            correlation = data[[x_col, y_col]].corr().iloc[0, 1]
            
            return {
                "type": "scatter",
                "title": f"{y_col} vs {x_col}",
                "description": f"Scatter plot showing relationship between {x_col} and {y_col}",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Correlation coefficient: {correlation:.3f}",
                    f"Data points: {len(data)}"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating scatter plot: {e}")
            return None

    def _create_box_plot(self, data: pd.DataFrame, column: str) -> Optional[Dict[str, Any]]:
        """Create a box plot for outlier detection"""
        try:
            fig = px.box(
                data,
                y=column,
                title=f"Box Plot: {column} (Outlier Detection)",
                labels={column: column}
            )

            fig.update_layout(
                height=400,
                template='plotly_white',
                showlegend=False
            )

            q1 = data[column].quantile(0.25)
            q3 = data[column].quantile(0.75)
            iqr = q3 - q1
            outliers = data[(data[column] < q1 - 1.5*iqr) | (data[column] > q3 + 1.5*iqr)]

            return {
                "type": "box_plot",
                "title": f"Box Plot: {column}",
                "description": f"Box plot showing distribution and outliers for {column}",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Q1 (25%): {q1:.2f}",
                    f"Median: {data[column].median():.2f}",
                    f"Q3 (75%): {q3:.2f}",
                    f"IQR: {iqr:.2f}",
                    f"Potential outliers: {len(outliers)} ({len(outliers)/len(data)*100:.1f}%)"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating box plot: {e}")
            return None

    def _create_pie_chart(self, data: pd.DataFrame, column: str) -> Optional[Dict[str, Any]]:
        """Create a pie chart for categorical data"""
        try:
            value_counts = data[column].value_counts().head(10)

            fig = px.pie(
                values=value_counts.values,
                names=value_counts.index,
                title=f"Distribution of {column}",
                hole=0.3  # Donut chart style
            )

            fig.update_layout(
                height=400,
                template='plotly_white'
            )

            return {
                "type": "pie_chart",
                "title": f"Distribution of {column}",
                "description": f"Pie chart showing proportion of {column} categories",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Total categories: {data[column].nunique()}",
                    f"Largest category: {value_counts.index[0]} ({value_counts.values[0]/len(data)*100:.1f}%)",
                    f"Showing top {len(value_counts)} categories"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating pie chart: {e}")
            return None

    def _create_grouped_bar_chart(self, data: pd.DataFrame, cat_col: str, num_col: str) -> Optional[Dict[str, Any]]:
        """Create a grouped bar chart showing numeric values by category"""
        try:
            # Aggregate by category
            grouped = data.groupby(cat_col)[num_col].agg(['mean', 'median', 'std']).reset_index()
            grouped = grouped.head(10)  # Top 10 categories

            fig = go.Figure()

            fig.add_trace(go.Bar(
                name='Mean',
                x=grouped[cat_col],
                y=grouped['mean'],
                marker_color='#3b82f6'
            ))

            fig.add_trace(go.Bar(
                name='Median',
                x=grouped[cat_col],
                y=grouped['median'],
                marker_color='#10b981'
            ))

            fig.update_layout(
                title=f"{num_col} by {cat_col}",
                xaxis_title=cat_col,
                yaxis_title=num_col,
                barmode='group',
                height=400,
                template='plotly_white'
            )

            return {
                "type": "grouped_bar",
                "title": f"{num_col} by {cat_col}",
                "description": f"Comparison of {num_col} across different {cat_col} categories",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Highest mean: {grouped['mean'].max():.2f} in {grouped.loc[grouped['mean'].idxmax(), cat_col]}",
                    f"Lowest mean: {grouped['mean'].min():.2f} in {grouped.loc[grouped['mean'].idxmin(), cat_col]}",
                    f"Average std dev: {grouped['std'].mean():.2f}"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating grouped bar chart: {e}")
            return None

    def _create_stats_summary(self, data: pd.DataFrame, numeric_cols: List[str]) -> Optional[Dict[str, Any]]:
        """Create a visual summary of statistical metrics"""
        try:
            # Prepare summary statistics
            stats = data[numeric_cols].describe().T

            fig = go.Figure()

            # Add mean as bars
            fig.add_trace(go.Bar(
                name='Mean',
                x=stats.index,
                y=stats['mean'],
                marker_color='#3b82f6',
                error_y=dict(
                    type='data',
                    array=stats['std'],
                    visible=True
                )
            ))

            fig.update_layout(
                title="Statistical Summary of Numeric Features",
                xaxis_title="Features",
                yaxis_title="Mean Value (±1 SD)",
                height=400,
                template='plotly_white',
                showlegend=True
            )

            return {
                "type": "stats_summary",
                "title": "Statistical Summary",
                "description": "Overview of mean values with standard deviation for numeric features",
                "chart": json.loads(fig.to_json()),
                "insights": [
                    f"Features analyzed: {len(numeric_cols)}",
                    f"Highest mean: {stats['mean'].max():.2f} ({stats['mean'].idxmax()})",
                    f"Highest variability: {stats['std'].max():.2f} ({stats['std'].idxmax()})"
                ]
            }
        except Exception as e:
            logger.error(f"Error creating stats summary: {e}")
            return None

    def _execute_visualization_code(self, code: str, data: pd.DataFrame, title: str) -> Optional[Dict[str, Any]]:
        """Execute LIDA-generated visualization code safely"""
        try:
            # Create a safe execution environment
            exec_globals = {
                'pd': pd,
                'np': np,
                'px': px,
                'go': go,
                'data': data,
                'plt': plt,
                'sns': sns
            }
            
            exec_locals = {}
            
            # Execute the code
            exec(code, exec_globals, exec_locals)
            
            # Extract the figure (LIDA usually creates a 'fig' variable)
            if 'fig' in exec_locals:
                fig = exec_locals['fig']
                
                # Convert to JSON for frontend
                if hasattr(fig, 'to_json'):
                    chart_json = json.loads(fig.to_json())
                else:
                    # For matplotlib figures, convert to base64 image
                    buffer = io.BytesIO()
                    fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
                    buffer.seek(0)
                    image_base64 = base64.b64encode(buffer.read()).decode()
                    plt.close(fig)
                    
                    chart_json = {
                        "type": "image",
                        "data": f"data:image/png;base64,{image_base64}"
                    }
                
                return {
                    "type": "lida_generated",
                    "title": title,
                    "description": f"Automatically generated visualization: {title}",
                    "chart": chart_json,
                    "code": code,
                    "insights": []
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing visualization code: {e}")
            return None
    
    def generate_insights_prompt(self, analysis: Dict[str, Any], visualizations: List[Dict[str, Any]]) -> str:
        """Generate a comprehensive prompt for AI to provide insights"""
        prompt = f"""
        Based on the following data analysis and visualizations, provide comprehensive insights:
        
        Dataset Overview:
        - Rows: {analysis['basic_stats']['rows']}
        - Columns: {analysis['basic_stats']['columns']}
        - Column Types: {analysis['basic_stats'].get('column_types', {})}
        
        Data Quality:
        - Missing Values: {analysis['data_quality'].get('missing_percentage', {})}
        - Duplicate Rows: {analysis['data_quality'].get('duplicated_rows', 0)}
        
        Key Statistics:
        {json.dumps(analysis.get('column_analysis', {}), indent=2)}
        
        Correlations:
        {json.dumps(analysis.get('correlations', {}).get('strong_correlations', []), indent=2)}
        
        Visualizations Generated:
        {[v['title'] for v in visualizations]}
        
        Please provide:
        1. Key patterns and trends in the data
        2. Data quality recommendations
        3. Suggested analyses or visualizations
        4. Actionable insights for decision-making
        """
        
        return prompt


# Singleton instance
_visualization_service = None

def get_visualization_service(api_key: Optional[str] = None) -> DataVisualizationService:
    """Get or create visualization service instance"""
    global _visualization_service
    
    if _visualization_service is None:
        _visualization_service = DataVisualizationService(api_key)
    
    return _visualization_service