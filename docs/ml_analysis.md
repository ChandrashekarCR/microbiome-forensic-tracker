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

### 1c. Microbiome Network Feature Engineering: SPIEC-EASI, Graphical Lasso & Graph Signal Processing

SPIEC-EASI (Sparse InversE Covariance estimation for Ecological Association and Statistical Inference) is a statistical method designed to infer underlying ecological networks (*Kurtz, Z. D., et al., 2015, PLoS computational biology*). It handles compositionality via CLR and finds direct interactions using Sparse Inverse Covariance.

#### The Friend-of-a-Friend Problem (Covariance vs. Inverse Covariance)

Imagine 3 microbes as people: **Alice (A)**, **Bob (B)**, and **Charlie (C)**.

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

In microbiome data, we often have many more taxa $p$ than samples $n$. Because $p$ can approach or exceed $n$, the sample covariance matrix $S$ is poorly conditioned or non-invertible ($S^{-1}$ may not exist or may be numerically unstable). Furthermore, true biological networks are sparse; we want weak noise to snap precisely to $0.0$.

Graphical Lasso searches for the best $\Theta$ by scoring guesses:

$$ \hat{\Theta} = \arg \min_{\Theta \succ 0} \underbrace{\left( \text{tr}(S\Theta) - \log(\det(\Theta)) \right)}_{\text{Part 1: The Fit}} + \underbrace{\lambda \sum_{i \neq j} |\Theta_{i,j}|}_{\text{Part 2: The } L_1 \text{ Penalty}} $$

- **Part 1 (Maximum Likelihood)**: "Make $\Theta$ as close to the real data $S$ as possible."
- **Part 2 (Lasso Penalty)**: "Charge a tax ($\lambda$) for every non-zero connection made."

If an added link provides only a tiny benefit to the fit, the $\lambda$ tax overrides it, forcing $\Theta_{i,j}$ to exactly $0$. A properly tuned $\lambda$ (via `GraphicalLassoCV`) acts like a machete, slicing away weak friend-of-a-friend links and leaving behind explicit, true ecological interactions.

**Robustness note:** at our sample sizes, `GraphicalLassoCV` can occasionally fail to converge on a given cross-validation fold (near-singular covariance). The current implementation catches this and falls back to an empty network (`L = I`, zero affinity, no communities, no spectral columns) for that fold rather than crashing the run. This keeps experiments running, but it means a fold that falls back silently produces near-CLR-only features under the hood. **The number of folds that hit this fallback should be logged and reported** — if it happens on a large fraction of folds, an apparent "no improvement from network features" result may actually be "no network was fit for most folds," which is a different finding entirely.

#### Why Naive Per-Taxon Weighting Fails (and why we moved past it)

An earlier version of this pipeline engineered features by multiplying each taxon's CLR abundance by its own network centrality score:

$$\text{DegreeWeighted}_i = \text{CLR}_i \times \text{Degree}_i \qquad \text{HubWeighted}_i = \text{CLR}_i \times \text{Betweenness}_i$$

The intent was to amplify the signal of ecologically important ("hub" or "bridge") taxa. This does not work, for a provable reason: $\text{Degree}_i$ and $\text{Betweenness}_i$ are **fixed scalars per taxon**, constant across every sample. Multiplying a column by a positive constant is an order-preserving (monotonic) rescaling of that column. For any model whose decision rule depends only on feature *order* within a column — which includes every tree-based learner (Random Forest, Extra Trees, XGBoost) — a split on $\text{CLR}_i > t$ and a split on $\text{DegreeWeighted}_i > t \cdot \text{Degree}_i$ are identical splits. The engineered column carries **zero information beyond the raw CLR column already in the model**. Worse, for any taxon with centrality exactly $0$ (a disconnected/isolated node — common in a sparse Graphical Lasso network), the engineered column collapses to a constant $0$, actively discarding that taxon's signal rather than adding to it.

This is why the pipeline moved from *per-taxon* network weighting to **network-topology features that are genuine multi-taxon functions** — quantities that cannot be reduced to a rescaling of any single existing column, described below.

#### The Ecological Network as a Graph Signal

Once Graphical Lasso gives us a sparse network, we treat each sample's CLR abundance vector $x \in \mathbb{R}^p$ as a **signal defined over the network's nodes** (this is the framework of Graph Signal Processing — Shuman et al., 2013). Instead of asking "how much of taxon $i$ is present," we ask "how does the abundance pattern behave *with respect to the network's shape*" — is it smooth (ecologically-linked taxa move together) or rough (linked taxa diverge)? This question is only answerable with both the abundance data *and* the network topology simultaneously, which is exactly the property traditional single-taxon or diversity-index features cannot provide.

**Step 1 — Weighted affinity graph.** From the partial correlation matrix $\rho$, keep only edges above a noise threshold:

$$A_{ij} = \begin{cases} |\rho_{ij}| & \text{if } |\rho_{ij}| \ge \text{edge\_threshold} \\ 0 & \text{otherwise} \end{cases}$$

**Step 2 — Normalized graph Laplacian.** With degree $d_i = \sum_j A_{ij}$ and $D = \text{diag}(d_1, \dots, d_p)$:

$$L = I - D^{-1/2} A D^{-1/2}$$

$L$ is symmetric positive semi-definite with eigenvalues $\lambda_1 \le \dots \le \lambda_p$, all in $[0, 2]$. This is the graph analogue of the second-derivative (Laplacian) operator from continuous calculus — it measures local "roughness" of a signal across the graph.

**Step 3 — Eigendecomposition (the graph's "frequencies").** $L = U \Lambda U^\top$, where the columns of $U$ are orthonormal eigenvectors $u_1, \dots, u_p$ — the **graph Fourier modes**. Low-eigenvalue modes are *smooth*: they vary slowly across ecologically connected taxa (whole neighborhoods rising or falling together). High-eigenvalue modes are *rough*: they oscillate sharply between connected taxa. Eigenvalues near $0$ correspond to trivial constant modes on each connected component and are discarded; the next $K$ smallest nontrivial eigenvalues give the most information-dense basis.

##### Feature A — Graph spectral coordinates

$$\hat{x}_k = u_k^\top x, \qquad k = 1, \dots, K$$

This is the **graph Fourier transform** of the sample: a change of basis where, instead of "how much of taxon $i$," each coordinate measures "how much does this sample's community pattern align with ecological pattern $k$." It is the network-topology analogue of a PCA projection, except the basis is defined by the *learned ecological structure*, not by the variance of the data itself.

##### Feature B — Global Laplacian energy (network coherence / smoothness)

$$x^\top L x = \frac{1}{2}\sum_{i,j} A_{ij}\left(\frac{x_i}{\sqrt{d_i}} - \frac{x_j}{\sqrt{d_j}}\right)^2$$

This quadratic form sums, over every edge in the network, the squared difference in (degree-normalized) abundance between the two connected taxa. Normalizing by the signal's own energy gives a bounded, sample-level score:

$$R(x) = \frac{x^\top L x}{x^\top x} = \frac{\sum_k \lambda_k\, \hat{x}_k^2}{\sum_k \hat{x}_k^2} \in [0, 2]$$

$R(x)$ is a weighted average of the graph's eigenvalues, weighted by how much of the sample's signal lands in each mode.

- **Low $R(x)$**: ecologically-linked taxa have coherent, similar abundances in this sample — the community "agrees with" the learned network structure.
- **High $R(x)$**: linked taxa diverge sharply — the sample's community is discordant with the expected co-occurrence pattern.

*Analogy:* picture the network as a terrain and each sample's abundances as a heat map painted over it. Low energy = heat is smoothly distributed across each neighborhood. High energy = neighboring points have wildly different temperatures despite being adjacent — a locally "stressed" or unusual configuration. This single number cannot be computed from abundances alone; it requires the graph.

##### Feature C — Community-specific Laplacian energy

Louvain community detection (Blondel et al., 2008) partitions the network into modules $C_1, \dots, C_m$ by maximizing modularity:

$$Q = \frac{1}{2m}\sum_{i,j}\left[A_{ij} - \frac{d_i d_j}{2m}\right]\delta(c_i, c_j)$$

where $c_i$ is the community assignment of node $i$ and $\delta$ is $1$ if $i,j$ are in the same community. Communities with fewer than `min_community_size` taxa are dropped (too small to be a meaningful module, and prone to instability). For each retained community $C_k$, restrict the sample and the Laplacian to that module's taxa and compute the same energy locally:

$$E_k(x) = \frac{x_{C_k}^\top L_{C_k}\, x_{C_k}}{\left\lVert x_{C_k}\right\rVert^2}, \qquad L_{C_k} = L[\text{idx}_k, \text{idx}_k]$$

This yields one coherence score per detected microbial guild: "how internally consistent is this sample's abundance pattern within guild $k$." A sample where one particular guild is unusually discordant, while the rest of the network is coherent, is a spatially-specific signature that a single global score would average away.

#### Feature Summary

| Feature Class | Mathematical Definition | Signal it Captures | Status |
|---|---|---|---|
| Raw CLR | $\text{CLR}(x_i) = \log(x_i/g(x))$ | Baseline taxon-level abundance, compositionality-corrected | Active (always included) |
| ~~Degree/Hub-Weighted~~ | ~~$\text{CLR}_i \times \text{Degree}_i$~~ | ~~Keystone/bridge amplification~~ | **Deprecated** — provably inert for tree models, see above |
| ~~Edge-Specific~~ | ~~$\Theta_{uv}\, x_u\, x_v$~~ | ~~Pairwise co-occurrence strength~~ | **Superseded** by community energy (more stable at $n\approx 200$) |
| Graph Spectral Coordinates | $\hat{x}_k = u_k^\top x$ | Alignment with dominant network-wide co-abundance patterns | Active |
| Global Laplacian Energy | $R(x) = x^\top L x / x^\top x$ | Whole-network coherence/discordance of the sample | Active |
| Community Laplacian Energy | $E_k(x) = x_{C_k}^\top L_{C_k} x_{C_k} / \lVert x_{C_k}\rVert^2$ | Per-guild coherence/discordance of the sample | Active |

#### Known Limitations (for the limitations section)

- **Silent GraphicalLassoCV fallback**: as noted above, a failed fold degrades to an empty network without altering the pipeline's control flow. Log `graph_failed_` occurrences per experiment run.
- **Isolated-node contamination risk**: if a taxon has degree $0$ after thresholding, the current eigendecomposition (run on the full $p \times p$ Laplacian rather than the induced subgraph of connected taxa) can assign it a spurious eigenvalue of exactly $1$ with an indicator eigenvector — meaning that spectral coordinate is numerically identical to that taxon's raw CLR value, despite the transformer's design intent of returning network-only, non-individual-taxon features. Recommended fix: compute the spectral basis only on the induced subgraph of non-isolated nodes and zero-pad back to full dimension.
- **Sample size vs. dimensionality**: at $n \approx 200$ samples and $p \approx 128$ taxa, `GraphicalLassoCV` is in a low-sample regime where the inferred network can vary meaningfully across folds/thresholds. Where possible, fit the unsupervised network step (which requires no labels) on a larger, leakage-safe pool of samples, and reuse the identical fitted network across CV folds.

#### Objective for Spatial Feature Engineering

Why do this before pushing data into ML models to predict latitude/longitude?

1. **Dimensionality reduction via biological signal**: rather than feeding hundreds of noisy species directly to the model, the spectral basis and community structure condense correlated, co-varying taxa into a small number of network-native summary scores.
2. **Information genuinely unavailable to abundance-only features**: coherence/discordance with respect to a learned network cannot be computed from any single taxon or from traditional diversity indices (e.g. Shannon, Simpson), which use only the abundance vector and never the inferred interaction structure. This is the basis for the claim that network features capture information traditional features miss — it is true by construction, not only empirically.
3. **Guild-level spatial signatures**: different geographies may be associated with distinct patterns of *ecological coherence within a guild*, not just differences in raw abundance — a form of signal only a topology-aware feature can expose.

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
│  │  - Remove low-prevalence taxa                             │   │
│  │  - Apply CLR transformation                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    2. FEATURE ENGINEERING                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Network Inference (Graphical Lasso) + Graph Signal        │   │
│  │  Processing                                                │   │
│  │  - Compute precision matrix → partial correlations         │   │
│  │  - Build weighted affinity graph + normalized Laplacian    │   │
│  │  - Eigendecompose: graph spectral coordinates              │   │
│  │  - Global Laplacian energy (whole-network coherence)       │   │
│  │  - Louvain communities → per-community Laplacian energy    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    3. EXPERIMENTAL PIPELINE                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Experiment 1: Taxonomy Level Selection                  │   │
│  │  - Phylum, Class, Order, Family, Genus, Species          │   │
│  │  - Baseline XGBoost/ExtraTrees (no feature engineering)  │   │
│  │  - Goal: Find most informative taxonomy level             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Experiment 2: Feature Engineering Impact                │   │
│  │  - Compare baseline vs. graph-signal-processing features  │   │
│  │  - Ablate use_spectral / use_global_graph / use_community  │   │
│  │  - Paired significance test (Wilcoxon, same CV folds)      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Experiment 3: Model Selection & Hyperparameter Tuning   │   │
│  │  - XGBoost, Random Forest, Extra Trees, SVM, NN            │   │
│  │  - Bayesian optimization with Optuna                     │   │
│  │  - Cross-validation with Repeated Stratified K-Fold        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    4. MLFLOW TRACKING                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Metrics Logging:                                        │   │
│  │  - Mean/median/max distance error, in-radius %            │   │
│  │  - Feature importance scores                              │   │
│  │                                                            │   │
│  │  Artifacts Logging:                                       │   │
│  │  - Trained models                                         │   │
│  │  - Network visualizations                                 │   │
│  │  - Feature importance plots                                │   │
│  │                                                            │   │
│  │  Parameters Logging:                                      │   │
│  │  - Model hyperparameters                                  │   │
│  │  - Feature engineering parameters (incl. edge_threshold,   │   │
│  │    n_spectral_features, min_community_size)                │   │
│  │  - Data preprocessing configurations                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Findings

1. **Taxonomy Level Selection**: Among all taxonomic levels, **Genus** provided the most informative signal for geolocation prediction when using XGBoost with basic preprocessing (removing low-prevalence columns only). This suggests that genus-level resolution captures enough ecological variation to distinguish spatial patterns without the noise introduced by species-level variation or the over-aggregation at higher taxonomic levels.

2. **Feature Engineering Impact — under active revision**: an earlier iteration using per-taxon degree/hub-weighted features reported a performance improvement; that result should be treated as unreliable, since those features are provably uninformative for tree-based models (see "Why Naive Per-Taxon Weighting Fails" above) and the apparent gain was likely an artifact of a different comparison setup rather than genuine network signal. The pipeline has since moved to graph-signal-processing features (spectral coordinates, global and community-specific Laplacian energy). Current preliminary Extra Trees results show mean/median/max error within a small margin of the CLR-only baseline; a configuration bug where `edge_threshold` was not being correctly propagated through the pipeline (see Section 1e) has recently been fixed, and a properly threshold-swept, statistically-tested comparison (paired Wilcoxon signed-rank across identical CV folds) is in progress. **This section will be updated with final, verified numbers before submission.**

### 1e. Methodology Implementation Details

#### Data Preprocessing Pipeline

```python
# Pseudocode for preprocessing pipeline
1. Load data from SQL database via config-driven ETL
2. Filter taxa based on minimum prevalence (e.g., 5% samples)
3. Apply multiplicative replacement for zeros (δ = 1e-6)
4. Apply CLR transformation to handle compositionality
5. Split data using Repeated Stratified K-Fold (3 splits, 10 repeats)
```

#### Feature Engineering Steps

```python
# Pseudocode for feature engineering (current pipeline)
1. Fit GraphicalLassoCV on CLR-transformed TRAINING data only
   (never on validation/test/blind-holdout samples)
2. Extract precision matrix Θ; convert to partial correlations:
       ρ_ij = -Θ_ij / sqrt(Θ_ii · Θ_jj)
3. Build weighted affinity graph:
       A_ij = |ρ_ij|  if |ρ_ij| >= edge_threshold, else 0
4. Build normalized graph Laplacian:
       D = diag(row sums of A)
       L = I - D^(-1/2) A D^(-1/2)
5. Eigendecompose L = U Λ U^T; discard near-zero trivial eigenvalues
   (one per connected component); keep the K smallest nontrivial
   eigenvectors as the spectral basis U_K
6. Detect Louvain communities on the weighted graph (modularity
   maximization); drop communities smaller than min_community_size
7. For every sample's CLR vector x, compute (each independently
   togglable via use_spectral / use_global_graph / use_community):
       a. Spectral coordinates:          x̂ = U_K^T x
       b. Global Laplacian energy:       R(x)  = x^T L x / ||x||^2
       c. Per-community Laplacian energy: E_k(x) = x_Ck^T L_Ck x_Ck / ||x_Ck||^2
8. Concatenate CLR features with all enabled engineered features
```

### 1f. Conclusion and Future Work

The combination of compositionally-aware preprocessing (CLR), ecological network inference (SPIEC-EASI/Graphical Lasso), and graph-signal-processing features (spectral coordinates, global and community-specific Laplacian energy) provides a framework for predicting spatial coordinates from microbiome data whose central claim — that network features capture information ordinary abundance features cannot — is grounded mathematically, not only empirically: the Laplacian energy terms are provably undefinable without both the abundance data and the learned network topology. Key advantages include:

- **Biologically grounded features** that capture ecological coherence, not just abundance
- **Handling of compositionality** through CLR transformation
- **Sparse network inference** via Graphical Lasso, with a documented, provable reason for rejecting the earlier per-taxon-weighting approach
- **Reproducible experimentation** through MLflow tracking, including logging of network-fitting failures per fold
- **Flexible taxonomy levels** for optimal feature extraction

Future directions include:
- Fixing the isolated-node spectral leak noted above, to keep the "network-only" feature guarantee strictly true
- Fitting the unsupervised network step on a larger, leakage-safe sample pool (e.g. synthetic or combined data, provided it does not touch the blind holdout) to stabilize `GraphicalLassoCV` at low $n/p$ ratios
- Paired statistical testing (Wilcoxon signed-rank on identical CV folds) as the standard reporting format for any baseline-vs-feature-engineered comparison
- Integration of environmental covariates (temperature, pH, soil type)
- Transfer learning for novel geographical regions

---