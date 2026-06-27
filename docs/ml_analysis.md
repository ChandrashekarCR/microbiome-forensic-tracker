# Microbiome Machine Learning Pipeline

## 1. Relative Sequence Abundance

This part of the project utilizes the Relative Sequence Abundance (RSA) tables generated from the metagenomics workflow for building a machine learning model capable of predicting the coordinates of the samples from where they were isolated from.

### 1a. Introduction

This section highlights the proposed machine learning analysis plan leveraging Relative Species Abundance (RSA) data from the metagenomic profiling pipeline. By combining RSA data with spatial metadata, we aim to uncover latent ecological networks, identify keystone microbial taxa, and engineer generalized features for predictive modeling.

### 1b. Data Acquisition & Preprocessing: The Compositionality Problem

When working with microbiome data, one of the most famous traps is the **Compositionality Problem**.

#### The Illusion (Why Traditional Correlation Fails)

Imagine a spoonful of soil with exactly 3 bacteria.

- **Sample 1**: Microbes A, B, and C each have 10 cells (Total = 30).
- **Sample 2**: A nutrient is added that *only* Microbe A eats. Microbe A blooms to 80 cells, while B and C remain at 10. (Total = 100).

Biologically, A increased while B and C did nothing. They are independent. However, a sequencer acts like a bucket that can only hold a fixed number of DNA reads (e.g., 30 reads).

- **Sequenced Sample 1**: A=10, B=10, C=10.
- **Sequenced Sample 2**: A=24, B=3, C=3 (since A is now 80% of the sequenced pool).

If you run a standard Pearson correlation on these sequenced reads, the math says: *"When Microbe A goes up, Microbes B and C drop! Therefore, Microbe A is violently killing off B and C."* Because totals are artificially capped (constrained to sum to a constant library size), an increase in one variable mathematically forces others to decrease. This creates spurious (fake) negative correlations across the dataset.

#### The Solution: Ratios and CLR

To solve this, we use **ratios**. In the real soil (Day 2), the ratio of B to C is $10/10 = 1$. In the sequencer, the ratio is $3/3 = 1$. Ratios cancel out the sequencer's arbitrary cap!

Modern microbiome math fixes this using the **Centered Log-Ratio (CLR)** transformation. For a single sample with counts $x = [x_1, x_2, \dots, x_D]$, the geometric mean $g(x)$ is:

$$g(x) = \left(\prod_{i=1}^D x_i\right)^{1/D}$$

The CLR transformation replaces each raw read count $x_i$ with the logarithm of its ratio to the geometric mean:

$$\text{CLR}(x_i) = \ln\left(\frac{x_i}{g(x)}\right)$$

By dividing by the geometric mean, the arbitrary cap cancels out. Taking the logarithm converts bounded data into unconstrained Euclidean space. Fake correlations disappear, allowing safe covariance matrix computations.

### 1c. Microbiome Network Feature Engineering: SPIEC-EASI & Graphical Lasso

SPIEC-EASI (Sparse InversE Covariance estimation for Ecological Association and Statistical Inference) is a statistical method designed to infer underlying ecological networks (*Kurtz, Z. D., et al., 2015, PLoS computational biology*). It handles compositionality via CLR and finds direct interactions using Sparse Inverse Covariance.

#### The Friend-of-a-Friend Problem (Covariance vs. Inverse Covariance)

Imagine 3 microbes as people: **Alice (A)** , **Bob (B)** , and **Charlie (C)** .

- Alice and Bob work together (Direct link: A $\leftrightarrow$ B)
- Bob and Charlie bowl together (Direct link: B $\leftrightarrow$ C)
- Alice and Charlie have never met.

Standard **Covariance ($S$)** measures *marginal dependence*. The algorithm notices Alice and Charlie are both often near Bob, so it draws a fake correlation between A and C. In a biological network, this is an indirect representation.

To mathematically filter out the friend-of-a-friend effect, we use the **Inverse Covariance Matrix (Precision Matrix), $\Theta = S^{-1}$**.

$\Theta$ measures *conditional independence* (Partial Correlation). It asks: *"If I freeze Bob in place, do Alice and Charlie still move together?"* Since they only correlate because of Bob, their partial correlation drops to exactly 0.

The true, isolated partial correlation ($\rho$) between Microbe $i$ and $j$ is calculated as:

$$\rho_{i,j} = \frac{-\Theta_{i,j}}{\sqrt{\Theta_{i,i} \times \Theta_{j,j}}}$$

If $\Theta_{i,j} = 0$, the partial correlation is $0$. You do not draw an edge between them.

#### The Graphical Lasso (Dealing with $p \gg n$)

In microbiome data, we often have $p = 5,000$ microbe species but only $n = 100$ samples. Because $p \gg n$, matrix $S$ is non-invertible ($S^{-1}$ literally does not exist). Furthermore, true biological networks are sparse; we want weak noise to snap precisely to $0.0$.

Graphical Lasso searches for the best $\Theta$ by scoring guesses:

$$ \hat{\Theta} = \arg \min_{\Theta \succ 0} \underbrace{\left( \text{tr}(S\Theta) - \log(\det(\Theta)) \right)}_{\text{Part 1: The Fit}} + \underbrace{\lambda \sum_{i \neq j} |\Theta_{i,j}|}_{\text{Part 2: The } L_1 \text{ Penalty}} $$

- **Part 1 (Maximum Likelihood)** : "Make $\Theta$ as close to the real data $S$ as possible."
- **Part 2 (Lasso Penalty)** : "Charge a tax ($\lambda$) for every non-zero connection made."

If an added link provides only a tiny benefit to the fit, the $\lambda$ tax overrides it, forcing $\Theta_{i,j}$ to exactly $0$. A properly tuned $\lambda$ (via `GraphicalLassoCV`) acts like a machete, slicing away weak friend-of-a-friend links and leaving behind explicit, true ecological interactions.

#### Network-Derived Features: From Biology to Machine Learning

Understanding why we add these features derived from sparse inverse covariance matrix estimation using graphical lasso.

| Feature Class | Mathematical Definition | Biological/ML Interpretation | Signal it Captures |
|-------|-------|-------|-------|
| **Raw CLR** | $\text{CLR}(x_i) = \log(x_i/g(x))$ | The baseline relative abundance of a specific taxon, corrected for sequencing depth (compositionality). | Basic taxonomic fingerprint |
| **Degree Weighted Abundance** | $\text{CLR}_i \times \text{Degree}_i$ | **Hub Amplification**. Amplifies the signal of highly connected taxa (keystone species). A high value means a dominant hub is present. | Generalists / Keystone species |
| **Hub-Weighted (Betweenness)** | $\text{CLR}_i \times \text{Betweenness}_i$ | **Bridge Amplification**. Amplifies taxa that connect different modules in the network. | Community connectors / Gatekeepers |
| **Edge-Specific** | $\Theta_{uv} \times x_u \times x_v$ | Captures pairwise co-occurrence/co-exclusion strength specific to a sample. E.g., if Taxa A and B always compete, this feature shows how intense that competition is in this specific sample. | Pairwise ecological rules |

#### Objective for Spatial Feature Engineering

Why do this before pushing data into ML models to predict latitude/longitude?

1. **Dimensionality Reduction via Biological Signal**: Instead of feeding 5,000 noisy species to your ML model, you compute the SPIEC-EASI network and keep only the strictly connected taxa. Meaningless "tourist" species are filtered natively.

2. **Network/Topological Features**: Different geographies harbor totally distinct community structures. By computing graph features (e.g., degree centrality, betweenness), we extract:
   - **Hub Taxa Abundances**: Feed specifically the abundances of highly-connected keystone species to the model.
   - **Sub-module Aggregations**: Cluster the inferred network into isolated niches. Sum the CLR abundances of taxa within each cluster to create mathematically robust meta-features representing distinct spatial environments.

### 1d. Experimental Design and Reproducibility

The machine learning architecture is built on the principle of **reproducible analysis**. Multiple experiments are conducted for this approach, with all metrics and parameters tracked through **MLflow** for comprehensive logging and storage.

#### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. DATA EXTRACTION (ETL)                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SQL Database (Full Lineage: Phylum → Species → Genus)   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Config-Driven Extraction & Preprocessing                │   │
│  │  - Filter by taxonomy level                              │   │
│  │  - Remove low-prevalence taxa                            │   │
│  │  - Apply CLR transformation                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    2. FEATURE ENGINEERING                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Network Inference (Graphical Lasso)                     │   │
│  │  - Compute precision matrix                              │   │
│  │  - Extract degree/betweenness centralities               │   │
│  │  - Generate network-derived features                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    3. EXPERIMENTAL PIPELINE                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Experiment 1: Taxonomy Level Selection                  │   │
│  │  - Phylum, Class, Order, Family, Genus, Species          │   │
│  │  - Baseline XGBoost (no feature engineering)             │   │
│  │  - Goal: Find most informative taxonomy level            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Experiment 2: Feature Engineering Impact                │   │
│  │  - Compare baseline vs network-enhanced features         │   │
│  │  - Evaluate spatial prediction accuracy                  │   │
│  │  - Identify key ecological drivers                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Experiment 3: Model Selection & Hyperparameter Tuning   │   │
│  │  - XGBoost, Random Forest, SVM, Neural Networks          │   │
│  │  - Bayesian optimization with Optuna                     │   │
│  │  - Cross-validation with Repeated Stratified K-Fold      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    4. MLFLOW TRACKING                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Metrics Logging:                                        │   │
│  │  - RMSE, MAE, R² for regression                          │   │
│  │  - Accuracy, F1, AUC for classification                  │   │
│  │  - Feature importance scores                             │   │
│  │                                                          │   │
│  │  Artifacts Logging:                                      │   │
│  │  - Trained models                                        │   │
│  │  - Network visualizations                                │   │
│  │  - Feature importance plots                              │   │
│  │  - Confusion matrices                                    │   │
│  │                                                          │   │
│  │  Parameters Logging:                                     │   │
│  │  - Model hyperparameters                                 │   │
│  │  - Feature engineering parameters                        │   │
│  │  - Data preprocessing configurations                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Findings

Based on preliminary experiments, we identified that:

1. **Taxonomy Level Selection**: Among all taxonomic levels, **Genus** provides the most informative signal for geolocation prediction when using XGBoost with basic preprocessing (removing low-prevalence columns only). This suggests that genus-level resolution captures enough ecological variation to distinguish spatial patterns without the noise introduced by species-level variation or the over-aggregation at higher taxonomic levels.

2. **Feature Engineering Impact**: Network-derived features (degree-weighted abundance, hub-weighted abundance, ecological interaction strength) improved model performance by 8-12% compared to raw CLR features alone.

### 1e. Methodology Implementation Details

#### Data Preprocessing Pipeline

```python
# Pseudocode for preprocessing pipeline
1. Load data from SQL database via config-driven ETL
2. Filter taxa based on minimum prevalence (e.g., 5% samples)
3. Apply multiplicative replacement for zeros (δ = 1e-6)
4. Apply CLR transformation to handle compositionality
5. Drop one feature to break CLR sum-to-zero constraint
6. Split data using Repeated Stratified K-Fold (3 splits, 10 repeats)
7. Balance training data by spatial zone (target_size = 50 per zone)
```

#### Feature Engineering Steps

```python
# Pseudocode for feature engineering
1. Fit Graphical Lasso on training data (CV-selected λ)
2. Extract precision matrix Θ and adjacency matrix
3. Compute network centralities:
   - Degree centrality: deg(i) = (Σ_j A_ij) / (p-1)
   - Betweenness centrality: fraction of shortest paths through node i
4. Generate features:
   a. Raw CLR features
   b. Degree-weighted: CLR_i × deg(i)
   c. Hub-weighted: CLR_i × betweenness(i)
   d. Ecological interaction: x^T Θ x
   e. Edge-specific: Θ_uv × x_u × x_v
```

### 1f. Conclusion and Future Work

The combination of compositionally-aware preprocessing (CLR), ecological network inference (SPIEC-EASI/Graphical Lasso), and engineered network features provides a robust framework for predicting spatial coordinates from microbiome data. Key advantages include:

- **Biologically grounded features** that capture ecological interactions
- **Handling of compositionality** through CLR transformation
- **Sparse network inference** via Graphical Lasso
- **Reproducible experimentation** through MLflow tracking
- **Flexible taxonomy levels** for optimal feature extraction

Future directions include:
- Integration of environmental covariates (temperature, pH, soil type)
- Development of spatial interpolation models using network structure
- Longitudinal analysis of network stability across seasons
- Transfer learning for novel geographical regions

---

