## Data Commons Assistant

The **Data Commons Assistant** is a chat application that helps analysts explore and analyze Google Data Commons. It uses a reasoning agent to interpret natural language queries, which can include selecting schema information and observations from Google Data Commons.  The assistant can perform statistical analyses such as correlation, regression and forecasts, and generate visualizations using charts.

### Quickstart
To start the assistant with minimal setup:

1. **Install prerequisites:** Docker and Git.

2. **Clone this repository:**
```
   git clone https://github.com/SocialHealthAI/Data-Commons-Assistant.git
   cd (path to) Data-Commons-Asssistant
```
3. **Set your keys:** Edit the `.env` file and add your `OPENAI_API_KEY` and 'DC_API_KEY'.  Get your Data Commons (DC) API key at: https://apikeys.datacommons.org

4. **Start the containers:**
```
   docker-compose up

5. **Start the Assistant**
```
   http://localhost:8052
```
