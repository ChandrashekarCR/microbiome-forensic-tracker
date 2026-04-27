# Machine Learning

## 1. Relative Sequence Abundance 
This part of the project utlizes the relative sequences abundance (RSA) tables generated from the metagenomics workflow for building a machine learning model capable of predicting the co-ordinates of the samples from where they were isolated from.

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
To solve this, we use **ratios**. In the real soil (Day 2), the ratio of B to C is $10/10 = 1$. In the sequencer, the ratio is $3/3 = 1$. Ratios cancel out the sequencer’s arbitrary cap!

Modern microbiome math fixes this using the **Centered Log-Ratio (CLR)** transformation. For a single sample with counts $x = [x_1, x_2, \dots, x_D]$, the geometric mean $g(x)$ is:
$$g(x) = \left(\prod_{i=1}^D x_i\right)^{1/D}$$

The CLR transformation replaces each raw read count $x_i$ with the logarithm of its ratio to the geometric mean:
$$\text{CLR}(x_i) = \ln\left(\frac{x_i}{g(x)}\right)$$

By dividing by the geometric mean, the arbitrary cap cancels out. Taking the logarithm converts bounded data into unconstrained Euclidean space. Fake correlations disappear, allowing safe covariance matrix computations.

### 1c. Microbiome Network Feature Engineering: SPIEC-EASI & Graphical Lasso

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
In microbiome data, we often have $p = 5,000$ microbe species but only $n = 100$ samples. Because $p \gg n$, matrix $S$ is non-invertible ($S^{-1}$ literally does not exist). Furthermore, true biological networks are sparse; we want weak noise to snap precisely to $0.0$.

Graphical Lasso searches for the best $\Theta$ by scoring guesses:
$$ \hat{\Theta} = \arg \min_{\Theta \succ 0} \underbrace{\left( \text{tr}(S\Theta) - \log(\det(\Theta)) \right)}_{\text{Part 1: The Fit}} + \underbrace{\lambda \sum_{i \neq j} |\Theta_{i,j}|}_{\text{Part 2: The } L_1 \text{ Penalty}} $$

- **Part 1 (Maximum Likelihood)**: "Make $\Theta$ as close to the real data $S$ as possible."
- **Part 2 (Lasso Penalty)**: "Charge a tax ($\lambda$) for every non-zero connection made."

If an added link provides only a tiny benefit to the fit, the $\lambda$ tax overrides it, forcing $\Theta_{i,j}$ to exactly $0$. A properly tuned $\lambda$ (via `GraphicalLassoCV`) acts like a machete, slicing away weak friend-of-a-friend links and leaving behind explicit, true ecological interactions.

#### Objective for Spatial Feature Engineering
Why do this before pushing data into ML models to predict latitude/longitude?

1. **Dimensionality Reduction via Biological Signal**: Instead of feeding 5,000 noisy species to your ML model, you compute the SPIEC-EASI network and keep only the strictly connected taxa. Meaningless "tourist" species are filtered natively.
2. **Network/Topological Features**: Different geographies harbor totally distinct community structures. By computing graph features (e.g., degree centrality, betweenness), we extract:
   - **Hub Taxa Abundances**: Feed specifically the abundances of highly-connected keystone species to the model.
   - **Sub-module Aggregations**: Cluster the inferred network into isolated niches. Sum the CLR abundances of taxa within each cluster to create mathematically robust meta-features representing distinct spatial environments.