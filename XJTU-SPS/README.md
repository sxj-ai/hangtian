---
size_categories:
- 100M<n<1B
---

### Spacecraft power system dataset for All-in-loop health management: work condition recognition, anomaly detection, fault localization, and forecasting/reconstruction.

### The detailed information can be found at: [https://diyi1999.github.io/XJTU-SPS/](https://diyi1999.github.io/XJTU-SPS/).

> (1) XJTU-SPS for MR Sub-dataset (for Work Mode Recognition Task): Simulate working conditions such as Fast Charge, Shunt, Trickle Charge, Joint, Idle, and Discharge, etc.  
> (2) XJTU-SPS for AD Sub-dataset (for Anomaly Detection Task): Simulate the situations when various anomalies occur during the operation, exceeding 700,000 timestamps.  
> (3) XJTU-SPS for FL or FD Sub-dataset (for Fault Localization / Fault Diagnosis Task): Simulate 17 types of fault scenarios, including partial component or branch open circuit of SA, BCR short circuit, and Bus insulation breakdown, etc.  
> (4) XJTU-SPS for F or R Sub-dataset (for Forecasting or Reconstruction Task): Six sub-files simulate the data of 4, 18, 24, 34, 90, and 94 orbits around the Earth, respectively, with a sampling frequency of 1Hz.

#### As far as we know, it is the first publicly available AIL HM dataset in the field, hope it can be helpful for you. Meanwhile, a simulation model corresponding to this dataset has also been established, which is developed according to the design principles and working mechanisms of real SPS, capable of restoring the operating status and dynamic characteristics of real SPS, further supporting researchers in fields such as digital twins and physics-informed neural networks.

#### if it is helpful for your research, you can cite the following works:

```bibtex
@misc{di2026empoweringallinloophealthmanagement,
title={Empowering All-in-Loop Health Management of Spacecraft Power System in the Mega-Constellation Era via Human-AI Collaboration}, 
author={Yi Di and Zhibin Zhao and Fujin Wang and Xue Liu and Jiafeng Tang and Jiaxin Ren and Zhi Zhai and Xuefeng Chen},
year={2026},
eprint={2601.12667},
archivePrefix={arXiv},
primaryClass={cs.AI},
url={https://arxiv.org/abs/2601.12667}, 
}

@article{DI2025113380,
title = {PhyGNN: Physics guided graph neural network for complex industrial power system modeling},
author = {Yi Di and Fujin Wang and Zhi Zhai and Zhibin Zhao and Xuefeng Chen},
year = {2025},
journal = {Mechanical Systems and Signal Processing},
volume = {240},
pages = {113380},
issn = {0888-3270},
doi = {https://doi.org/10.1016/j.ymssp.2025.113380},
url = {https://www.sciencedirect.com/science/article/pii/S0888327025010817},
keywords = {Physics guided graph neural network, Spacecraft power system, Multivariate time series, Complex industrial system},
}
```