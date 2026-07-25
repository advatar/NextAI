"""E51: reject real-model cohorts that cannot identify the proposed improvement."""
import hashlib,json
from pathlib import Path
from compare_selection import _atomic_json

def main():
 source=json.loads(Path('experiments/E50-real-curved.json').read_text());tasks=source['tasks']
 saturation=sum(t['target_in_exploration'] for t in tasks)/len(tasks)
 disagreements=sum(t['summaries']['shape_router']!=t['summaries']['linear'] for t in tasks)
 criteria={'maximum_exploration_target_rate':.2,'minimum_shape_vs_linear_disagreements':3,'minimum_tasks':5}
 checks={'exploration_target_rate':saturation,'shape_vs_linear_disagreements':disagreements,'tasks':len(tasks)}
 admitted=saturation<=criteria['maximum_exploration_target_rate'] and disagreements>=criteria['minimum_shape_vs_linear_disagreements'] and len(tasks)>=criteria['minimum_tasks']
 report={'schema_version':1,'experiment_id':'E51-benchmark-admission','claim_boundary':'informativeness audit only; no capability claim','source_experiment':'E50-real-curved','criteria':criteria,'observed':checks,'admitted':admitted,'decision':'reject and redesign cohort' if not admitted else 'admit'}
 report['report_digest']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode()).hexdigest();_atomic_json(Path('experiments/E51-benchmark-admission.json'),report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
