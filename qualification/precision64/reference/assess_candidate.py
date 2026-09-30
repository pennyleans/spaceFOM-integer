"""Independent candidate acceptance; imports only the existing hash-pinned oracle."""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PIN='882e2638096a847911be2e4af20cd934a9b343ab33d6393810ff88d6b235f62b'
PHYSICS_KEYS=('case','steps_per_second','duration_seconds','sample_interval_seconds','bodies','vessel','burn','frame','epoch_tdb')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def oracle(path):
    if sha(path)!=PIN:raise ValueError('reference source hash does not match the accepted oracle')
    spec=importlib.util.spec_from_file_location('independent_oracle',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_path(root,name):
    candidates=[p for p in (root/name,root/(name+'-64')) if (p/'initial.json').is_file()]
    if len(candidates)!=1:raise ValueError(f'exactly one case directory required for {name}')
    return candidates[0]


def normalized(initial):
    return {key:initial[key] for key in PHYSICS_KEYS if key in initial}


def assess_physics(args,contract):
    ref=oracle(args.oracle)
    factor=args.factor
    if factor not in (2,4,8,16,32):raise ValueError('selected factor must be 2,4,8,16 or 32')
    cases=dict(contract['nominal_cases'])
    if not args.nominal_only:
        held=contract['held_out'];cases[held['case']]=held
    results=[]
    for name,coverage in cases.items():
        paths=[case_path(root,name) for root in (args.selected_root,args.coarse_root,args.legacy_root)]
        initial=[load(path/'initial.json') for path in paths]
        for item,expected in zip(initial,(factor,factor//2,1)):
            if item['steps_per_second']!=64 or item.get('integration_substeps',1)!=expected:
                raise ValueError(f'{name}: outer tick rate or internal factor mismatch')
            if item['duration_seconds']!=coverage['duration_seconds'] or item['sample_interval_seconds']!=1:
                raise ValueError(f'{name}: case coverage differs from the declared acceptance')
        if not normalized(initial[0])==normalized(initial[1])==normalized(initial[2]):
            raise ValueError(f'{name}: physics inputs differ between factors')
        if name==contract['held_out']['case']:
            if normalized(initial[0])!=normalized(load(HERE/'held-out-initial.json')):
                raise ValueError('held-out initial state was changed')
        records=[ref.assess(path) for path in paths]
        for record in records:
            if record['sample_count']!=coverage['samples']:raise ValueError('sample coverage mismatch')
        selected,coarse,legacy=[r['metrics'] for r in records]
        position=[x['max_position_error_m'] for x in (selected,coarse)]
        velocity=[x['max_velocity_error_m_s'] for x in (selected,coarse)]
        position_ratio=position[0]/position[1] if position[1] else None
        velocity_ratio=velocity[0]/velocity[1] if velocity[1] else None
        below_floor=all(x<1e-5 for x in position) and all(x<1e-8 for x in velocity)
        refinement=below_floor or (position_ratio is not None and velocity_ratio is not None and position_ratio<0.4 and velocity_ratio<0.4)
        orbital=name in ('earth-orbit','moon-orbit',contract['held_out']['case'])
        improvement=(selected['max_position_error_m']<legacy['max_position_error_m'] and selected['max_velocity_error_m_s']<legacy['max_velocity_error_m_s']) if orbital else None
        mass_unchanged=None
        if name=='inertial-burn':
            states=[ref.read_case(path)[1] for path in paths]
            mass_unchanged=all(len(s)==coverage['samples'] for s in states) and all(Decimal(a['vessel']['mass_kg'])==Decimal(b['vessel']['mass_kg'])==Decimal(c['vessel']['mass_kg']) for a,b,c in zip(*states))
        gates={'absolute_limits':all(r['metrics']['pass'] for r in records),'refinement':refinement,'strict_orbital_improvement':improvement,'burn_mass_unchanged':mass_unchanged}
        passed=all(v is not False for v in gates.values())
        results.append({'case':name,'factors':{'selected':factor,'coarser':factor//2,'legacy':1},'gates':gates,'pass':passed,'position_ratio_selected_over_coarser':position_ratio,'velocity_ratio_selected_over_coarser':velocity_ratio,'all_four_errors_below_declared_floors':below_floor,'oracle_receipts':dict(zip(('selected','coarser','legacy'),records))})
    return {'schema':'precision-candidate-physics-v1','selected_factor':factor,'outer_steps_per_second':64,'held_out_included':not args.nominal_only,'physics_pass':all(r['pass'] for r in results),'complete_physics_acceptance':not args.nominal_only and all(r['pass'] for r in results),'timing_status':'not assessed by this subcommand','results':results}


def assess_timing(args,contract):
    data=load(args.benchmarks)
    if data.get('schema')!='precision-benchmark-v1':raise ValueError('unexpected benchmark schema')
    limits=contract['timing'];evaluated=[];identities={};seen=set()
    for run in data['runs']:
        key=(run['platform'],run['integration_substeps'],run['workload_id'])
        if key in seen:raise ValueError('duplicate platform/factor benchmark')
        seen.add(key)
        if key[0] not in limits['required_platforms'] or key[1] not in contract['candidate_internal_substeps'] or key[2] not in limits['required_workloads']:
            raise ValueError('unexpected platform or factor')
        measurements=run['measurements_ms']
        if not measurements or any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in measurements):
            raise ValueError('invalid benchmark duration')
        if key[2] in identities and identities[key[2]]!=run['workload_sha256']:
            raise ValueError('benchmark workload identity differs between runs')
        identities[key[2]]=run['workload_sha256']
        mean=math.fsum(measurements)/len(measurements)
        p99=sorted(measurements)[math.ceil(0.99*len(measurements))-1]
        full=all(run.get(k) is True for k in limits['required_workload_flags'])
        coverage=run['warmup_ticks']>=1024 and len(measurements)>=8192 and run['outer_hz']==64
        passed=full and coverage and mean<=12.5 and p99<=12.5
        evaluated.append({'platform':key[0],'factor':key[1],'workload_id':key[2],'mean_ms':mean,'p99_ms':p99,'measured_ticks':len(measurements),'warmup_ticks':run['warmup_ticks'],'full_workload':full,'coverage_pass':coverage,'mean_headroom_fraction':1-mean/15.625,'p99_headroom_fraction':1-p99/15.625,'timing_pass':passed})
    both=[];missing=[]
    required={(platform,workload) for platform in limits['required_platforms'] for workload in limits['required_workloads']}
    for factor in contract['candidate_internal_substeps']:
        matching=[r for r in evaluated if r['factor']==factor]
        platforms={(r['platform'],r['workload_id']) for r in matching}
        for platform,workload in required:
            if (platform,workload) not in platforms:missing.append({'platform':platform,'factor':factor,'workload_id':workload})
        if platforms==required and all(r['timing_pass'] for r in matching):both.append(factor)
    highest=max(both) if both else None
    incomplete=missing+[{'platform':r['platform'],'factor':r['factor'],'workload_id':r['workload_id'],'reason':'full workload or measured coverage not established'} for r in evaluated if not r['full_workload'] or not r['coverage_pass']]
    higher_unmeasured=[r for r in incomplete if highest is None or r['factor']>highest]
    next_factor=highest*2 if highest is not None and highest<32 else None
    next_rows=[r for r in evaluated if r['factor']==next_factor]
    next_complete={(r['platform'],r['workload_id']) for r in next_rows}==required and all(r['full_workload'] and r['coverage_pass'] for r in next_rows)
    bracket=highest==32 or (highest is not None and next_complete and any(not r['timing_pass'] for r in next_rows))
    return {'schema':'precision-candidate-timing-v1','benchmark_sha256':sha(args.benchmarks),'workload_identities':identities,'runs':evaluated,'both_platforms_and_workloads_passing_factors':both,'highest_measured_timing_pass_factor':highest,'next_higher_factor':next_factor,'selection_bracket_supported':bracket,'higher_factors_without_full_measurement':higher_unmeasured,'globally_highest_measured_claim_supported':highest is not None and not higher_unmeasured,'physics_status':'requires matching independent physics and held-out acceptance; timing alone never qualifies a factor'}


def main():
    parser=argparse.ArgumentParser()
    subparsers=parser.add_subparsers(dest='mode',required=True)
    physics=subparsers.add_parser('physics')
    for key in ('oracle','selected-root','coarse-root','legacy-root'):physics.add_argument('--'+key,type=Path,required=True)
    physics.add_argument('--factor',type=int,required=True)
    physics.add_argument('--nominal-only',action='store_true')
    timing=subparsers.add_parser('timing');timing.add_argument('--benchmarks',type=Path,required=True)
    for subparser in (physics,timing):subparser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('existing evidence is retained; choose a fresh output path')
    contract_path=HERE/'acceptance.json';contract=load(contract_path)
    result=assess_physics(args,contract) if args.mode=='physics' else assess_timing(args,contract)
    result['acceptance_sha256']=sha(contract_path);result['wrapper_sha256']=sha(Path(__file__))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','runs')},indent=2))
    return 0 if args.mode=='timing' or result['physics_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
