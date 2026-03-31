"""
This script is just used to check for the resource usage by the rules in snakemake, so that
they can be updated to ensure maximum efficiency.
"""
# Import libraries
import pandas as pd
import re

# Read the efficient report
df = pd.read_csv("/home/chandru/binp51/logs/efficiency_report_master.csv")
df = df.dropna(axis=1)
df['JobID'] = df['JobID'].astype(int)
job_ids = list(df['JobID'])

rule_sample = []
with open('/home/chandru/binp51/logs/snakemake_master.log','r') as f:
    for line in f:
        for job_id in job_ids:
            match = re.search(str(job_id),line)
            if match is not None:
                rule = line.split("/")[-3]
                sample = line.split("/")[-2]
                rule_sample.append((rule,sample))

df['rule'] = [rule[0] for rule in rule_sample]

rule_report_df = df.groupby(['rule'],as_index=False).agg(
    {'Elapsed_sec':'max',
     'CPU Efficiency (%)':'max',
     'Memory Usage (%)': 'max',
     'MaxRSS_MB':'max',
     'RequestedMem_MB':'max',
     'NNodes':'max',
     'NCPUS':'max'}
)

rule_report_df = rule_report_df.rename(columns={'Elapsed_sec':'elapsed_sec',
                                                'MaxRSS_MB':'peak_memory_usage',
                                                'RequestedMem_MB':'requested_memory_mb',
                                                'NNodes':'nodes',
                                                'NCPUS':'ncpus',
                                                "CPU Efficiency (%)":'max_cpu_efficiency_perc',
                                                "Memory Usage (%)":"memory_usage_perc"})

print(rule_report_df)