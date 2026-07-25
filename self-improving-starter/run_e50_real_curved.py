"""E50: five-task real-Gemma curved cohort with shape-router exploitation."""
import argparse,hashlib,json,math,random,time
from pathlib import Path
from types import SimpleNamespace
from compare_selection import _atomic_json
from compare_e37_surrogate_generalization import score
from compare_e49_shape_router import choose
from run_e29_gemma_deceptive import MODEL
from run_e35_coarse_niches import parse_y

def main():
 p=argparse.ArgumentParser();p.add_argument('--base-url',default='http://127.0.0.1:12345/v1');p.add_argument('--out',type=Path,default=Path('experiments/E50-real-curved.json'));a=p.parse_args()
 from gemma_agent_lab.backends.base import ChatMessage
 from gemma_agent_lab.backends.openai_compatible import OpenAICompatibleBackend
 backend=OpenAICompatibleBackend(SimpleNamespace(model=MODEL,base_url=a.base_url,api_key_env=None,extra_body={'chat_template_kwargs':{'enable_thinking':False}}))
 setup=random.Random(50);targets=[(setup.randrange(5),setup.randrange(5)) for _ in range(5)];tasks=[];receipts=[]
 for task_index,target in enumerate(targets):
  rng=random.Random(5000+task_index);obs={x:[] for x in range(5)};explored=[]
  for round_index in range(3):
   order=list(range(5));rng.shuffle(order)
   for x in order:
    prior=', '.join(f'y={y}:score={v:.3f}' for y,v in obs[x]) or 'none';prompt=('Return JSON only as {\"y\": integer}. y must be 0 through 4. '+f'Assigned row x={x}. Prior evaluations: [{prior}]. Choose an unevaluated y for an opaque curved objective.')
    seed=rng.randrange(2**63);started=time.monotonic();response=backend.generate([ChatMessage(role='user',content=prompt)],temperature=1.0,top_p=.95,seed=seed,max_tokens=32);text=str(response.text);y=None;error=None
    try:y=parse_y(text)
    except Exception as exc:error=f'{type(exc).__name__}: {exc}'
    value=0. if y is None else score('curved',(x,y),target)
    if y is not None:obs[x].append((y,value));explored.append((x,y))
    u=response.usage;receipts.append({'task':task_index,'seed':seed,'prompt_digest':hashlib.sha256(prompt.encode()).hexdigest(),'response_digest':hashlib.sha256(text.encode()).hexdigest(),'total_tokens':int(u.total_tokens),'latency_seconds':time.monotonic()-started,'parse_ok':y is not None,'error':error})
  policies={name:list(explored) for name in ('shape_router','linear','random')};control=random.Random(9500+task_index)
  for x in range(5):
   unseen=[y for y in range(5) if y not in {z for z,_ in obs[x]}]
   for name in policies:
    y,_=choose(name if name!='shape_router' else 'shape_router',obs[x],unseen,control);policies[name].append((x,y))
  summaries={name:{'target_hit':target in points,'best_score':max(score('curved',p,target) for p in points),'evaluations':len(points)} for name,points in policies.items()}
  tasks.append({'task':task_index,'target':list(target),'target_in_exploration':target in explored,'observations':{str(x):obs[x] for x in obs},'summaries':summaries});print(task_index,target,summaries)
 backend.close();report={'schema_version':1,'experiment_id':'E50-real-curved','claim_boundary':'five precommitted real-model curved tasks with shared exploration and matched exploitation counterfactuals','model':MODEL,'targets':[list(t) for t in targets],'tasks':tasks,'gemma_calls':len(receipts),'valid_response_rate':sum(r['parse_ok'] for r in receipts)/len(receipts),'receipts':receipts};report['report_digest']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode()).hexdigest();_atomic_json(a.out,report)
if __name__=='__main__':main()
