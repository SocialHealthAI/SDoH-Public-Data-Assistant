### Repositories List
# 🧠 Key Insight (important for your architecture)

* There is **no universal SDoH API standard yet**

* The closest thing to a standard on the _health side_ is **FHIR (Fast Healthcare Interoperability Resources)**, which is widely used for structured exchange

* Most successful pipelines use:

  * **1–2 harmonized aggregators (Data Commons, CDC APIs)**

  * * **raw domain APIs (Census, World Bank, etc.)**

***

# 🌍 1. Cross-domain / Aggregated Repositories (Best Starting Point)

## 1. Google Data Commons (you already found it)

* Unified knowledge graph of public datasets (Census, World Bank, etc.)

* ✔ API + graph query

* ✔ Harmonized schema

* ✔ Strong for SDoH + health + economics

* ❗ Limited granularity for some niche health indicators

👉 **Closest thing to a “standard interface” today**

***

## 2. CDC Environmental Public Health Tracking Network

* Includes:

  * Environmental exposures

  * Some SDoH-like variables

  * Health outcomes

* ✔ Has API (developer tools mentioned)

* ✔ County-level data

* ✔ Good for spatial ML

***

## 3. NIH / NIAID Data Ecosystem Discovery Portal

* Aggregates millions of biomedical datasets

* ✔ API for metadata + discovery

* ✔ Harmonized metadata layer

👉 Think of this as a **“meta-repository” (data discovery layer)**

***

## 4. HealthData.gov

* U.S. government open data hub

* ✔ Many datasets accessible via Socrata APIs

* ✔ Includes CMS, CDC, HRSA

***

## 5. Community Commons

* Curated SDoH datasets + indicators

* ✔ Some API-like access (less formalized)

* ✔ Strong for community-level indicators

***

# 🇺🇸 2. Core U.S. SDoH Data APIs (High Value)

## 1. U.S. Census Bureau API

* Gold standard for:

  * Income

  * Education

  * Housing

  * Demographics

* ✔ API

* ✔ Fine granularity (tract/block)

👉 Backbone for most SDoH ML pipelines

***

## 2. CDC PLACES API

(you already listed it)

* ✔ Small-area estimates

* ✔ Chronic disease + risk behaviors

* ✔ Zip/county level

***

## 3. County Health Rankings (RWJF)

* ✔ Pre-aggregated SDoH indices

* ❗ Limited API (mostly downloads)

***

## 4. Social Vulnerability Index (SVI) – CDC

* ✔ Composite SDoH index

* ✔ Census tract level

* ✔ Download + some API access

***

## 5. USDA Food Access Research Atlas

* ✔ Food deserts, access

* ✔ SDoH-specific

***

## 6. HUD + EPA datasets

* Housing quality, pollution, environmental justice

* ✔ Often API-enabled via data portals

***

# 🌎 3. Global SDoH / Socioeconomic APIs

## 1. World Bank Open Data API

* ✔ Income, poverty, education, infrastructure

* ✔ Country-level SDoH

***

## 2. WHO Global Health Observatory (GHO)

* ✔ Health + some social determinants

* ✔ API + bulk download

***

## 3. UN Data / UNDP Human Development Reports

* ✔ HDI, inequality indices

* ✔ Structured but API support varies

***

## 4. OECD Data API

* ✔ High-quality socioeconomic indicators

* ✔ Standardized

***

# 🏥 4. Health Indicator Repositories (APIs + Standardized)

## 1. CDC WONDER

* ✔ Mortality, disease stats

* ✔ API (less modern but usable)

***

## 2. CMS APIs

(you already referenced CMS Chronic Conditions)

* ✔ Claims-based prevalence, cost

* ✔ Strong for ML features

***

## 3. Global Burden of Disease (IHME)

* ✔ Disease prevalence, DALYs

* ✔ API + downloads

* ✔ Very ML-friendly

***

## 4. NHANES (CDC)

* ✔ Rich clinical + behavioral + SDoH

* ❗ Not API-first (download datasets)

***

## 5. MEPS (AHRQ)

* ✔ Cost, utilization, access

* ✔ Strong longitudinal structure

***

# 🔌 5. Emerging “Unified Access” Patterns

## 1. FHIR-based APIs

* Used by:

  * EHR vendors

  * Health systems

* Increasingly including:

  * SDoH screening data

👉 Important for **future-proofing your architecture**

***

## 2. Data-as-a-Service Platforms (Hybrid)

Examples:

* LexisNexis SDoH API (commercial)

* Health equity scoring APIs

👉 These often:

* Normalize SDoH

* Provide risk scores

* BUT are not open/public

***

# 🧩 Recommended Architecture (for your ML project)

### Tiered ingestion strategy

**Tier 1 (core harmonized layer)**

* Data Commons

* CDC APIs (PLACES, Tracking)

**Tier 2 (feature enrichment)**

* Census API

* USDA, EPA, HUD

* World Bank (if global)

**Tier 3 (health outcomes)**

* CMS

* CDC WONDER

* IHME
