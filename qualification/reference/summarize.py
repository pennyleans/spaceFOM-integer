"""Collect declared absolute thresholds, coverage, and independent step refinement."""
import argparse
import json
from pathlib import Path
from oracle import digest


def run(source,output):
    if output.exists():raise FileExistsError('use a fresh evidence output path')
    pairs=[]
    for name in ('earth-orbit','moon-orbit','inertial-burn','lunar-fixture'):
        files=[source/f'{name}-{hz}.json' for hz in (64,128)]
        receipts=[json.loads(p.read_text()) for p in files]
        a,b=[r['metrics'] for r in receipts]
        pos=[r['max_position_error_m'] for r in (a,b)]
        vel=[r['max_velocity_error_m_s'] for r in (a,b)]
        pr=pos[1]/pos[0] if pos[0] else None
        vr=vel[1]/vel[0] if vel[0] else None
        floor=all(x<1e-5 for x in pos) and all(x<1e-8 for x in vel)
        gate=floor or (pr is not None and vr is not None and pr<0.4 and vr<0.4)
        pairs.append({'case':name,'rates_hz':[64,128],'position_error_ratio_128_over_64':pr,'velocity_error_ratio_128_over_64':vr,'both_position_and_velocity_below_floor_at_both_rates':floor,'refinement_pass':gate,'absolute_thresholds_pass':a['pass'] and b['pass'],'sample_count':[r['sample_count'] for r in receipts],'duration_seconds':[r['duration_seconds'] for r in receipts],'complete_declared_sample_coverage':all(r['complete_declared_sample_coverage'] for r in receipts),'receipt_sha256':[digest(p) for p in files]})
    result={'schema':'reference-refinement-summary-v1','thresholds':{'ratio_strictly_less_than':0.4,'position_floor_strictly_less_than_m':1e-5,'velocity_floor_strictly_less_than_m_s':1e-8,'exemption':'requires both position and velocity below their floors at both rates'},'pairs':pairs,'all_pass':all(p['refinement_pass'] and p['absolute_thresholds_pass'] and p['complete_declared_sample_coverage'] for p in pairs),'summarizer_sha256':digest(__file__)}
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.source,args.output)
