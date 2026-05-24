## Data Commons

#### Indiana Demo Scenario (Data Commons)

##### Test find-fields-1
**what variables are available for diabetes?  also provide source.**

response: Percent_Person_WithDiabetes, provides source (unlike GPT 5 Mini)

##### Test find-places-years-field-1
is Percent_Person_WithDiabetes available by counties? If so, what years?

response: At county level, years 2020, 2021, 2022

##### Test map-counties
show a map of the counties in Indiana for Percent_Person_WithDiabetes, in the year 2021

response:  good map, properly shaded  (unlike GPT 5 Mini)

##### Test join-say-table-with-compute-correlate
construct a wide table with one row per county where the counties are in the state Indiana and the year is 2021.

Table numeric columns are:
(Count_Person_BelowPovertyLevelInThePast12Months / population) 
Percent_Person_WithDiabetes

Then calculate pearson coefficient between Percent_Person_WithDiabetes and
(Count_Person_BelowPovertyLevelInThePast12Months / population)

Response (works but pretty slow) -
* The Pearson coefficient ≈ 0.785 indicates a strong positive linear association across Indiana counties in 2021: counties with higher percent of adults with diabetes also tend to have higher poverty rates (as measured by Count\_Person\_BelowPovertyLevelInThePast12Months per population).

##### Test join-say-table-with-compute-plot
construct a wide table with one row per county where the counties are in the state Indiana and the year is 2021.

Table numeric columns are:
(Count_Person_BelowPovertyLevelInThePast12Months / population) 
Percent_Person_WithDiabetes

Then provide a scatter plot for Percent_Person_WithDiabetes and
(Count_Person_BelowPovertyLevelInThePast12Months / population)

Response (works but pretty slow) -
import matplotlib.pyplot as plt \\# Data (County labels included for reference) County = \['Crawford County','Elkhart County','Fulton County','Hendricks County','Switzerland County','Wayne County','Blackford County','Gibson County','Hancock County','Orange County','Vanderburgh County','Wabash County','White County','Carroll County','Harrison County','Huntington County','Monroe County','Pike County','Washington County','Wells County','Delaware County','Jasper County','Noble County','St. Joseph County','Benton County','Dearborn County','Floyd County','Lawrence County','Morgan County','Warren County','Fountain County','Montgomery County','Randolph County','Henry County','Newton County','LaGrange County','Martin County','Miami County','Bartholomew County','Dubois County','Clay County','Clinton County','Jackson County','Knox County','Tippecanoe County','Vigo County','Brown County','Lake County','Owen County','Putnam County','Ripley County','Sullivan County','Boone County','Decatur County','Fayette County','Johnson County','Kosciusko County','Ohio County','Scott County','Spencer County','Starke County','Steuben County','Tipton County','Union County','Vermillion County','Warrick County','Posey County','Rush County','Whitley County','Jay County','Franklin County','Grant County','Jefferson County','LaPorte County','Marion County','Porter County','Howard County','Jennings County','Daviess County','Adams County','Allen County','Clark County','Greene County','Hamilton County','Cass County','DeKalb County','Madison County','Marshall County','Parke County','Perry County','Pulaski County','Shelby County'] PovertyPercent = \[18.8,12.9,13.4,6.4,17.1,18.6,15.8,13.5,6.7,17.6,15.6,13.5,12.1,10.4,10.4,12.4,22.8,13.5,14.0,9.3,20.7,10.6,11.1,15.9,12.7,9.3,11.0,15.1,12.0,10.9,12.9,13.7,16.5,17.6,14.3,9.3,14.2,17.6,9.8,9.0,13.6,12.6,15.8,18.0,19.4,22.7,13.0,15.3,13.9,14.4,10.8,19.5,6.7,12.2,16.6,9.0,11.3,11.2,17.7,10.1,17.1,11.7,10.7,13.8,15.0,8.3,11.1,13.4,8.9,16.2,10.5,21.5,14.1,14.5,16.3,11.0,14.2,15.0,15.0,15.0,14.3,12.1,16.7,4.5,14.4,9.8,17.9,10.5,19.2,15.5,14.0,12.0] DiabetesPercent = \[12.2,10.9,10.6,9.0,11.6,11.1,11.8,10.0,8.7,10.9,11.0,10.4,10.0,9.8,9.9,10.1,10.5,10.0,11.1,9.7,11.3,9.9,10.3,11.1,11.5,9.6,9.4,10.0,10.2,9.9,10.6,10.5,10.5,10.5,10.4,10.5,10.2,11.3,10.0,9.7,10.0,10.9,10.9,10.6,10.8,12.1,9.4,12.0,11.3,10.6,9.7,11.9,8.2,9.8,11.2,9.5,9.7,9.7,11.4,9.7,11.0,9.9,9.8,9.8,10.8,8.7,9.2,10.7,9.4,11.1,9.5,11.1,10.2,11.5,12.0,9.8,10.8,10.6,11.0,11.4,11.1,10.3,10.6,8.1,11.7,9.9,11.0,10.4,11.8,9.9,10.8,10.1] \\# x and y values (percentages) x = PovertyPercent y = DiabetesPercent \\# Simple linear regression (least squares) n = len(x) mean\_x = sum(x) / n mean\_y = sum(y) / n num = sum((xi - mean\_x) \* (yi - mean\_y) for xi, yi in zip(x, y)) den = sum((xi - mean\_x) \*\* 2 for xi in x) m = num / den if den != 0 else 0.0 b = mean\_y - m \* mean\_x \\# Regression line endpoints x\_min, x\_max = min(x), max(x) x\_fit = \[x\_min, x\_max] y\_fit = \[m \* xv + b for xv in x\_fit] \\# Plot fig, ax = plt.subplots(figsize=(8,6)) ax.scatter(x, y, color='gray', alpha=0.8, label='Counties', zorder=3) ax.plot(x\_fit, y\_fit, color='red', linewidth=2, label=f'Fit: y = {m:.3f}x + {b:.3f}', zorder=2) ax.set\_xlabel('Count\_Person\_BelowPovertyLevelInThePast12Months / population \[%]') ax.set\_ylabel('Percent\_Person\_WithDiabetes \[%]') ax.set\_title('Diabetes vs Poverty (Indiana counties, 2021)') ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7) ax.legend() \\# To display the plot in a script or notebook, call: \\# plt.show()

##### Test join-say-simple-with-compute-plot
show a scatter plot for (Count_Person_BelowPovertyLevelInThePast12Months / population) 
Percent_Person_WithDiabetes by counties in the state of Indiana for the year 2021

Response - worked!

#### CMS Demo
CMS age group is 65+ so comparable metrics from other sources must be age adjusted.
See studies on relatioinship between geography and opioid script rates.

show a map for states in the US for "Medicare Part D Opioid Prescribing Rates - by Geography" for year 2023

show a map of zip codes 45202, 45214, 45219, 45220, 45225 for "Medicare Part D Opioid Prescribing Rates - by Geography" for year 2023

#### Map Tests

##### Test map-cities-county boundary
show map of the cities/villages in Clermont County for DCID: Count_Person_BelowPovertyLevelInThePast12Months in year 2023.  show the boundary outline of Clermont county and provide labels for cities/villages.

Response - (works but slow)

##### And CDC Places Zip
show a map of zip codes 45202, 45214, 45219, 45220, 45225 for "Lack of social and emotional support among adults” for year 2023

##### and CDC Places Census Tracts
centered on Cincinnati

show a map of census tracts for tracks 39061000100 39061000200 39061000300 39061000400 39061000500 39061000600 39061000700 39061000800 39061000900 39061001000 39061001100 39061001200 39061001300 39061001400 39061001500 39061001600 39061001700 39061001800 39061001900 39061002000 39061002100 39061002200 39061002300 39061002400 39061002500 39061002600 39061002700 39061002800 39061002900 39061003000

for "Lack of social and emotional support among adults” for year 202

#### Regression
provide regression analysis where (Count\_Person\_BelowPovertyLevelInThePast12Months / population) is the dependent variable and Percent\_Person\_WithDiabetes is the independent variable for counties in the state of Indiana for the year 2021


#### Multiple Source Join Test
Not a good demo as populations are different

show a scatter plot for "Medicare Part D Opioid Prescribing Rates - by Geography" and the percent of households without health insurance calculated by ("Households Without Health Insurance"/"Households") for counties in the state of Ohio for year 2023.  Ignore rows with null entries.

Good demo on CDC Places and Data Commons.  Moderate positive correlation.

calculate the Pearson correlation coefficient for "Lack of social and emotional support among adults” and the 'Unemployment rate' for counties in the state of Ohio for year 2023. Ignore rows with null entries.
