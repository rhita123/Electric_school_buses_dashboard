#  Electric School Bus Dashboard (ESB Dash)

A data-driven dashboard built with **Streamlit** and **Plotly** to analyze the adoption and distribution of **Electric School Buses (ESBs)** across the United States.  
This interactive app allows users to explore policy progress, air quality, and equity indicators — both at **state** and **district** levels.

---

## Key Features

### 1. Policies by State
- Interactive **map** of electrification policies and statewide commitments.  
- Filters for **ACT rule** adoption and number of commitments.  
- Dynamic color scales for ESBs, PM2.5, and social indicators.

###  2. Air & Equity by District
- Visualizes **PM2.5 concentration**, **income levels**, and **student diversity**.  
- Interactive choropleth + scatter chart linking air quality and ESB adoption.  
- Helps identify correlations between pollution exposure and fleet electrification.

###  3. Distribution by State
- Ranked **Top-N bar charts** showing ESB concentration by state.  
- Optional **Pareto line** and **heat map** to visualize distribution intensity.  
- Adjustable filters and share percentages.

###  4. Distribution by District
- District-level analysis with **filters**, **search**, and **Top-N bar charts**.  
- Optional **stacked bar charts** showing fleet mix by fuel type (Diesel, Electric, etc.).  
- Interactive **map view** (using Mapbox) showing committed ESBs by location.

---

## ⚙️ Tech Stack

| Component | Technology |
|------------|-------------|
| **Frontend** | [Streamlit](https://streamlit.io/) |
| **Visualization** | [Plotly Express](https://plotly.com/python/plotly-express/), Mapbox |
| **Data Handling** | Pandas, NumPy |
| **Language** | Python 3.10+ |
| **Dataset** | ESB Adoption Dataset — *June 2025 update* |

---

## Run the Dashboard Locally

###  Clone the repository
```bash
git clone https://github.com/rhita123/esb-dash.git
cd esb-dash
