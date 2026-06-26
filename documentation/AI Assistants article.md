# AI Assistants for Public SDoH Data Modeling and Discovery
![map development.png](image\map development.png)

If your project involves public data, you have probably spent more time data wrangling than performing analysis or building models. This is especially true when data is derived from multiple public sources or must be integrated with your own datasets. There is no single standard for public SDoH data, and datasets often differ in definitions, geographic levels, identifiers, and reporting periods. As a result, analysts spend significant time determining whether datasets can be combined before statistical analysis or machine learning can begin.

This article explores how AI assistants can help with the discovery and modeling of public SDoH data. An open-source AI assistant will be highlighted that integrates several of the most widely used public data sources. The assistant can help find relevant variables, understand geographic and temporal coverage, and compare related measures across sources before building statistical, machine learning, or AI pipelines.

### The Challenge of Public SDoH Data
Government agencies and civil organizations collect, consolidate, and publish Social Determinants of Health (SDoH) data. Important U.S. sources include the U.S. Census Bureau, the Centers for Disease Control and Prevention (CDC), and the Centers for Medicare & Medicaid Services (CMS). Important international sources include the World Health Organization (WHO) and the United Nations Statistics Division.

Accessing data from different sources can be time consuming because there is no common API for querying and retrieving SDoH data.  Also, there is no standard approach for organizing datasets. Each source uses its own terminology, metadata conventions and geographic identifiers.

Also, combining sources for analysis can be challenging. Most public health datasets can be understood in terms of three types of data: time, place, and population metrics.

#### Time

Most public SDoH metrics are reported annually, but reporting periods are not always consistent across sources some may use multi-year estimates. Reporting lags are also common, particularly for mortality and healthcare claims data. 

#### Place

Geography is often the most difficult challenge in public SDoH analytics. Data may be reported at the country, state, county, census tract, ZIP code, or census block group level. Healthcare outcomes may also be reported by facility, service area, or hospital referral region rather than a traditional geographic boundary.

Even when geographic areas are similar, different identifier systems such as GEOIDs, FIPS codes, ZIP codes, and facility identifiers can make integration difficult. You can spend significant effort determining whether two datasets can be joined at a geographic level.

#### Population Metrics

Population metrics are typically expressed as counts, percentages, rates, or prevalence measures. Converting counts into meaningful rates requires accurate population denominators, which may come from different sources and time periods.

To determine the exact geographic coverage and time frames for a metric, you often need to query and test the data. Metadata cannot always be relied upon because descriptions may be incomplete or provided only at a high level. In addition, datasets may contain missing values requiring you to evaluate patterns of missingness.  And testing data is further complicated 

Additional complexity arises from age-adjusted rates and survey weighting.  Two sources may provide a metric called "mortality rate," but one may report crude mortality and the other age-adjusted mortality. Without understanding the methodology, you might incorrectly compare or combine the data.  Understanding the specific source of each metric is important for understanding how the metric was calculated.

Finding the best source for your metric can be difficult as numerous sources can define similar metrics and the metrics can vary by place and time.  Often you will need to determine whether two metrics can be compared, cover the same geography, and are available for the same time period.

### Why Repositories Initiatives Matter
Public repositories are being developed that integrate multiple data sources to improve harmonization of data.  Examples of repositories that integrate SDoH data are Google's[ Data Commons](https://datacommons.org/) and the [Agency for Healthcare Research and Quality](https://www.ahrq.gov/sdoh/data-analytics/sdoh-data.html) (AHRQ).

Data Commons is a broad source: demographics, economics, health, education, and environment for countries down to cities, counties, census tracts, and ZIP Codes.  Data commons provides a common data structure organized as a knowledge graph.  Instead of storing data in isolated data sets, a knowledge graph connects data in a web. It maps out "Entities" (like the city of Chicago) and connects them to "Variables" (like its population, average temperature, or unemployment rate). Because everything is linked, the data access methods understand that "Chicago the city," "Chicago's population," and "Chicago's unemployment" all belong to the same physical place. The major SDoH source include the [American Community Survey (ACS)](https://www.census.gov/programs-surveys/acs/), [CDC PLACES](https://www.cdc.gov/places/about/index.html), and [Feeding America’s Map the Meal Gap](https://www.feedingamerica.org/research/map-the-meal-gap/how-we-got-the-map-data) study. 

The [Agency for Healthcare Research and Quality](https://www.ahrq.gov/sdoh/data-analytics/sdoh-data.html) (AHRQ) provides a healthcare repository that includes a number of SDoH sources. The ARHQ consolidates the sources into a single data structure and includes the **[American Community Survey](https://www.census.gov/programs-surveys/acs/)** the [**CDC Social Vulnerability Index**](https://www.atsdr.cdc.gov/placeandhealth/svi/index.html) and the USDA [**Food Environment Atlas**] 

Repository initiatives address some of the challenges of analyzing public SDoH data. Dimensions ad metrics are organized into a common data structure with consistent naming, units, and documentation. In platforms such as Data Commons, that structure takes the form of a knowledge graph that links entities.
Repositories also help with "places" issues by using consistent identifiers—such as FIPS codes and GEOIDs. Data querying and access is also standardized. Data Commons exposes a standard API for discovering variables and retrieving observations. AHRQ consolidates sources into standard, linkable files with codebooks and geography keys.

### But Repositories Have Limits

Limits of repositories.  Incomplete data, aggregate data instead of detail data, metadata only as good as the source metadata, need to still test exact geographic and time coverage.  Repository initiatives are helping, but you still need tools capable of dynamically exploring and validating real datasets.  Especially important is joining multiple sources.

Repository initiatives help with public data, but they do not eliminate the ork of exploratory data modeling and validation. Data integration platforms import what upstream agencies publish and that coverage is often incomplete. A repository may lag behind the latest source release, or provide only aggregate summaries rather than detail date. Metadata provide by a source can have vague descriptions and availability by time and place may be stated broadly.  

Data integration does not guarantee that two metrics can be compared as-is. Suppose you join CDC PLACES county diabetes prevalence with an ACS county poverty rate for the same state and year. Both may list county FIPS codes and appear to merge, yet many counties can have sparse or missing values for one source in that year. Also, PLACES prevalence is typically modeled for adults and may be age-adjusted, while ACS poverty is derived from household counts over a multi-year window. Each rate uses a different denominator and population definition. 

Repository initiatives solve a number of issues, but you still need tools capable of dynamically exploring and validating datasets. That is especially true when analysis depends on joining multiple sources or combining public repositories with local proprietary data. 
***

### Analytic Assistants
Conversational AI agents that orchestrate data tools are well suited to data integration and data exploration tasks.   A large language model interprets your goal and selects a sequence of steps: search catalogs, call APIs, align identifiers, inspect returned values, and run statistics or maps. The model does not replace judgment, but it can carry out the repetitive integration and validation steps that otherwise slow SDoH projects.

![analytic assistant art.png](image\analytic assistant art.png)
							Original artwork by author, modified using Gemini & ChatGPT_

For example, you might ask: _“For Ohio counties in 2023, find measures of social isolation and unemployment, check that both are available at the county level, and calculate their Pearson correlation.”_ An assistant can search several sources for metrics, note the original source and description of the metrics, fetch values by county FIPS code, drop rows with missing data, compute the correlation, and return a table plus a scatter plot.

The open source project: [SDoH Public Data Assistant](https://github.com/SocialHealthAI/SDoH-Public-Data-Assistant) is a chat application that helps you explore and analyze public data repositories relevant to SDoH.  You ask questions in natural language; a reasoning agent interprets them, discovers indicators across connected sources, fetches observations for places and time periods, and can run statistical analyses—including correlation, regression, and simple forecasts—and produce charts and maps from the results.  The assistant connects to **Google Data Commons**, **Centers for Medicare & Medicaid Services (CMS) datasets**, and **CDC PLACES**. A planned capability is connecting your own database so you can explore local data alongside public repositories and relate the two.

The open-source [SDoH Public Data Assistant](https://github.com/SocialHealthAI/SDoH-Public-Data-Assistant) is a chat application for exploring and analyzing public SDoH repositories. The user asks questions in natural language; a reasoning agent discovers indicators across sources, fetches observations by place and year, and can run correlation, regression, descriptive statistics, simple forecasts, and choropleth maps. A planned capability will let you connect a local database alongside public repositories (not yet implemented).

The assistant searches three repositories in order, then merges results so no single source dominates the list. [Google Data Commons](https://datacommons.org/) is queried first. It offers the broadest coverage of demographic, economic, and health variables in a consistent structure. [Centers for Medicare & Medicaid Services (CMS)](https://data.cms.gov/) datasets add claims and program based health metrics. CMS measures describe the Medicare population (age 65 and older), so they should not be compared to general-population rates. [CDC PLACES](https://www.cdc.gov/places/about/index.html) supplies estimates of chronic disease, health behaviors, disabilities, and health-related social needs. PLACES is often the best source when Data Commons lacks a series, when the question concerns HRSN topics, or when age-adjusted county prevalence is needed for comparison. 

The assistant helps you

* **Normalize terminology across sources**  Map requests (“diabetes rate,” “poverty,” “loneliness”) to repository-specific indicator names and IDs, and flag when two similar measures use different definitions or populations.

* **Query heterogeneous sources**  Reach Data Commons, CMS, CDC PLACES using different API's.

* **Discover variables** Search across sources for candidates that match a topic, geography, and time scope.

* **Describe variables from metadata** — Summarize source, repository, geographic level, and measurement type.

* **Join variables on shared time and place** — Build tables with one row per place and time. Confirm that two indicators are available at the same level (for example, county-to-county) before merging or mapping.

* **Inspect live samples**  Pull actual observations to see which places have values, which years are populated, where data are sparse, and whether reporting periods align across sources.

* **Generate statistics and visualizations** Run descriptive statistics, correlation, regression, or simple forecasts on assembled tables, and produce standard analytic views such as scatter plots and choropleth maps.


#### Indicator discovery

```
What variables are available for diabetes? Include source and repository for each candidate.
```

##### 💬 Final Answer

The assistant searches **Google Data Commons**, **CMS**, and **CDC PLACES** and returns a markdown table with columns such as Name, Source, Repository, `indicator_id`, and `native_id` (for example `Percent_Person_WithDiabetes` from Data Commons).

#### County analysis (Data Commons)

```
For Indiana counties in 2021, build a wide table with poverty rate (Count\_Person\_BelowPovertyLevelInThePast12Months divided by population) and Percent\_Person\_WithDiabetes. Then show a scatter plot using those two columns
```

##### 💬 Final Answer

The agent fetches observations, builds one row per county with separate numeric columns and displays the table and the scatter plot.

![Scatter plot example](documentation/image/scatter.png)

#### Map (Data Commons)

```
show a map of the counties in Indiana for Percent_Person_WithDiabetes, in the year 2021
```

##### 💬 Final Answer

Map ready. The app renders an interactive choropleth in the chat UI.

![Indiana county map example](documentation/image/indiana.png)

#### Multi-source comparison (CDC PLACES + Data Commons)

```
Calculate the Pearson correlation between lack of social and emotional support among adults and unemployment rate for Ohio counties in 2023. Ignore rows with null values.
```

##### 💬 Final Answer

The agent discovers indicators in both repositories, aligns counties on `place_key`, builds a wide table, and returns correlation statistics. This pattern works well when PLACES supplies a measure Data Commons does not publish at county level.




***

### Conclusion

Short and forward-looking.

Main points:

* public SDoH data remains difficult to integrate
* metadata alone is often insufficient
* AI assistants can accelerate exploratory modeling
* harmonization + intelligent agents together are powerful

Then mention:

* future support for custom databases
* semantic mapping frameworks
* community contributions


## Topics that could be useful
## 1. Introduction

### Possible themes

* The growing use of publicly available SDoH datasets
* The promise of AI-assisted public health analytics
* Why analysts still spend enormous time finding, validating, and joining data
* The emergence of AI assistants for data modeling and discovery

### Suggested framing

Introduce the idea that:

> Public SDoH analysis is often less limited by statistics than by data fragmentation, inconsistent metadata, and incompatible geographic structures.

Then position AI assistants as:

> semantic and analytical bridges across fragmented public health ecosystems.

### Mention

* conversational analytics
* AI agents
* public APIs
* dynamic data exploration
* geospatial analytics

You can lightly introduce the [Social Health AI article on AI agents and SDoH](http://socialhealthai.org/ai-react-agent/ai-agents-and-social-determinants-of-health/?utm_source=chatgpt.com) here.

***

# 2. The Reality of Public SDoH Data

This section is foundational.

## 2.1 Fragmentation Across Sources

Discuss:

* CDC Places
* CMS
* Census
* HRSA
* Data Commons
* local/state repositories

Main problems:

* different schemas
* different naming conventions
* different geographic units
* incompatible identifiers
* varying update cadences

Good phrase:

> Public SDoH analysis frequently becomes an exercise in data archaeology.

***

## 2.2 Geographic and Temporal Mismatches

Strong practical examples:

* county vs census tract vs ZIP code vs state
* yearly vs rolling averages
* mismatched reporting periods
* partial geographic coverage

Important point:

> Two metrics may appear compatible in metadata while actually representing different populations or time periods.

This is one of your strongest themes.

***

## 2.3 Metadata Is Often Incomplete

This could become one of the best sections.

Discuss:

* incomplete dictionaries
* vague descriptions
* undocumented null behavior
* unclear geographic availability
* inconsistent year coverage

Strong line:

> In practice, analysts often need to interrogate actual data samples rather than trust metadata alone.

This directly supports your AI assistant narrative.

***

# 3. Repository and Harmonization Initiatives

## 3.1 Why Harmonization Matters

Introduce the broader need for:

* semantic consistency
* reusable identifiers
* linked datasets
* interoperable APIs

Reference ideas from your harmonization notes.

***

## 3.2 The Value of Data Commons

This section should be balanced and thoughtful.

Discuss advantages:

* single API
* common entity identifiers
* linked datasets
* graph relationships
* standardized statistical variables

This is where “semantic glue” language fits naturally.

### Important framing

Avoid overselling.

Something like:

> Data Commons represents one of the most important public efforts toward semantic harmonization of community and SDoH-related datasets.

***

## 3.3 Why Repository Platforms Alone Are Not Enough

This is important and nuanced.

Discuss:

* aggregate-only metrics
* incomplete source coverage
* lagging updates
* missing detail from original datasets
* inability to incorporate local/private datasets
* limitations for custom modeling

Good transition:

> Repository initiatives reduce friction, but they do not eliminate the need for exploratory data modeling and validation.

***

# 4. Why AI Assistants Are Well Suited for SDoH Data Modeling

This is the conceptual core of the article.

## 4.1 AI as Semantic and Analytical Glue

Excellent place to revisit the title theme.

Discuss how AI assistants can:

* bridge inconsistent schemas
* normalize concepts
* infer joins
* map identifiers
* translate terminology
* reconcile geography levels

Strong phrasing:

> AI assistants can operate as semantic middleware between heterogeneous public health datasets.

***

## 4.2 AI Assistants Can Test Data Dynamically

This is a differentiator.

Discuss:

* validating actual years available
* checking geographic coverage
* testing compatible joins
* inspecting sample rows
* discovering missing values
* identifying aggregation mismatches

Very important insight:

> The assistant is not limited to static metadata; it can empirically interrogate live datasets.

That is a powerful and distinctive idea.

***

## 4.3 Conversational Analytics for Public Health

Discuss:

* natural language exploration
* iterative questioning
* rapid hypothesis testing
* correlation analysis
* regression analysis
* visualization generation
* map-based analysis

You can position this as:

> lowering technical barriers while accelerating expert workflows.

***

# 5. The SDoH Public Data Assistant

This becomes the applied section.

Reference:

* [README documentation](https://github.com/SocialHealthAI/SDoH-Public-Data-Assistant/blob/main/README.md?utm_source=chatgpt.com)
* [Architecture documentation](https://github.com/SocialHealthAI/SDoH-Public-Data-Assistant/blob/main/documentation/architecture.md?utm_source=chatgpt.com)

***

## 5.1 High-Level Architecture

Keep this high level for non-engineers.

Suggested topics:

* AI reasoning agent
* tool orchestration
* API integration
* geospatial workflows
* statistical analysis pipeline
* visualization support

You probably do NOT want deep implementation details here.

***

## 5.2 Data Discovery Workflow

Explain:

* Data Commons first
* CMS
* CDC Places
* supplemental APIs
* geospatial data sources
* OpenStreetMap integration

Important idea:

> the assistant dynamically selects and evaluates sources rather than relying on a fixed warehouse.

***

## 5.3 Example Analytical Workflows

This section could include:

* finding correlations between social support and mortality
* comparing insurance coverage vs chronic disease prevalence
* mapping county-level trends
* tract-level visualization
* joining datasets with incompatible identifiers

This is where screenshots/visuals will help.

***

# 6. Demonstration

This should feel practical rather than promotional.

Possible flow:

1. User asks a natural language question

2. Assistant identifies datasets

3. Assistant validates compatible geography/time

4. Assistant joins data

5. Assistant produces:

   * statistics
   * charts
   * maps
   * correlation outputs

This section could become a future standalone blog too.

***

# 7. Limitations and Open Challenges

Very important for credibility.

Discuss:

* incomplete harmonization
* inconsistent source quality
* missing geographic detail
* ecological fallacy risks
* need for domain expertise
* AI hallucination risks
* reproducibility concerns

Strong line:

> AI assistants accelerate exploration, but they do not replace epidemiological rigor or careful interpretation.

***

# 8. Conclusion and Next Steps

Summarize:

* SDoH data remains fragmented
* harmonization initiatives are valuable
* AI assistants can bridge semantic and analytical gaps
* conversational modeling can accelerate public health analytics

Then transition to your roadmap:

* user-defined datasets
* custom database integration
* richer harmonization frameworks
* reusable semantic mappings
* agentic data validation

End with:

* GitHub repo
* future collaboration
* invitation for contributions

You might close with something like:

> The future of public SDoH analytics may depend less on building ever-larger centralized repositories and more on creating intelligent systems capable of dynamically understanding, validating, and integrating heterogeneous public data.

