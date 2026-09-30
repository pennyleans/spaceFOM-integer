"""Acquire held-out JPL body states, then separate model and integration residuals."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import urllib.parse
import urllib.request
from oracle import digest, norm, sub, read_case, rk4_reference, shifted


def fetch_bodies(initial, destination):
    destination.mkdir(parents=True,exist_ok=True)
    acquired=[]
    for body in initial['bodies']:
        target=str(body['id'])
        params={'format':'json','COMMAND':f"'{target}'",'OBJ_DATA':"'YES'",'MAKE_EPHEM':"'YES'",'EPHEM_TYPE':"'VECTORS'",'CENTER':"'500@0'",'START_TIME':"'2207-01-01 00:00:00'",'STOP_TIME':"'2207-01-01 00:01:00'",'STEP_SIZE':"'1 m'",'REF_PLANE':"'ECLIPTIC'",'REF_SYSTEM':"'ICRF'",'OUT_UNITS':"'KM-S'",'VEC_CORR':"'NONE'",'VEC_TABLE':"'2'",'CSV_FORMAT':"'YES'",'TIME_TYPE':"'TDB'"}
        url='https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
        raw_path=destination/f'horizons-{target}.json'
        if raw_path.exists():
            raise FileExistsError('use a fresh destination to retain prior evidence')
        with urllib.request.urlopen(url,timeout=60) as response:
            raw=response.read()
        raw_path.write_bytes(raw)
        decoded=json.loads(raw)
        if decoded.get('signature',{}).get('version')!='1.2':
            raise ValueError('Horizons API version changed; inspect preserved response and documentation before parsing')
        if 'error' in decoded or '$$SOE' not in decoded.get('result',''):
            raise RuntimeError(f'Horizons failed for {target}: {decoded.get("error",decoded.get("result"))}')
        text=decoded['result']
        records=[]
        for line in text.split('$$SOE')[1].split('$$EOE')[0].splitlines():
            if not line.strip():continue
            fields=[x.strip() for x in line.split(',')]
            records.append({'jd_tdb':fields[0],'calendar':fields[1],'p':[str(Decimal(x)*1000) for x in fields[2:5]],'v':[str(Decimal(x)*1000) for x in fields[5:8]]})
        if len(records)!=2 or not records[0]['calendar'].startswith('A.D. 2207-Jan-01 00:00:00') or not records[1]['calendar'].startswith('A.D. 2207-Jan-01 00:01:00'):
            raise ValueError('unexpected held-out sample dates')
        acquired.append({'id':target,'url':url,'params':params,'api_signature':decoded.get('signature'),'raw_sha256':digest(raw_path),'records':records})
        print('acquired',target,flush=True)
    result={'schema':'horizons-heldout-v1','acquired_utc':datetime.now(timezone.utc).isoformat(),'epoch':'2207-01-01T00:00:00 TDB','frame':'solar-system barycentric, ecliptic J2000, ICRF, geometric','times_s':[0,60],'sources':acquired}
    (destination/'acquisition.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def compare(case_dir,acquisition,destination):
    if destination.exists():raise FileExistsError('use a fresh evidence output path')
    initial,samples,times=read_case(case_dir)
    if times[-1]!=60:raise ValueError('held-out comparison requires exactly 60 seconds')
    by_id={b['id']:b for b in acquisition['sources']}
    origin,fine=rk4_reference(initial,[0,60],0.125,residuals=True)
    _,coarse=rk4_reference(initial,[0,60],0.25,residuals=True)
    data=[]
    for i,body in enumerate(initial['bodies']):
        raw=by_id[str(body['id'])]['records']
        hp0=[float(Decimal(b)-Decimal(a)) for a,b in zip(body['p'],raw[0]['p'])]
        hv0=[float(Decimal(b)-Decimal(a)) for a,b in zip(body['v'],raw[0]['v'])]
        hp=[float(Decimal(b)-Decimal(a)-Decimal(v)*60) for a,b,v in zip(body['p'],raw[1]['p'],body['v'])]
        hv=[float(Decimal(b)-Decimal(a)) for a,b in zip(body['v'],raw[1]['v'])]
        fp,fv=fine[-1][6*i:6*i+3],fine[-1][6*i+3:6*i+6]
        cp,cv=coarse[-1][6*i:6*i+3],coarse[-1][6*i+3:6*i+6]
        sim=next(b for b in samples[-1]['bodies'] if str(b['id'])==str(body['id']))
        sp=[float(Decimal(b)-Decimal(a)-Decimal(v)*60) for a,b,v in zip(body['p'],sim['p'],body['v'])]
        sv=[float(Decimal(b)-Decimal(a)) for a,b in zip(body['v'],sim['v'])]
        data.append({'id':str(body['id']),'initial_position_residual_m':norm(hp0),'initial_velocity_residual_m_s':norm(hv0),'point_mass_reference_vs_horizons_position_m':norm(sub(fp,hp)),'point_mass_reference_vs_horizons_velocity_m_s':norm(sub(fv,hv)),'simulation_vs_horizons_position_m':norm(sub(sp,hp)),'simulation_vs_horizons_velocity_m_s':norm(sub(sv,hv)),'simulation_vs_reference_position_m':norm(sub(sp,fp)),'simulation_vs_reference_velocity_m_s':norm(sub(sv,fv)),'reference_refinement_position_m':norm(sub(fp,cp)),'reference_refinement_velocity_m_s':norm(sub(fv,cv))})
    result={'schema':'horizons-model-comparison-v2','classification':'descriptive model discrepancy, not a same-model numerical gate','case':initial['case'],'duration_seconds':60,'held_out':'60-second JPL samples are not used to initialize the simulation or reference','reference_conditioning':'per-body deviations from initial rectilinear paths; decimal subtraction before float conversion','limitations':['Initial fixture rounding and any initial-state discrepancies are reported separately.','JPL ephemerides contain a richer force model than these 11 mutual point masses.','This is not a measurement of 2207 ephemeris prediction uncertainty or absolute physical truth.','No vessel ephemeris exists in Horizons for this fictional vessel.','Reference body arithmetic uses IEEE double; per-body refinement residual exposes its finite-precision floor.'],'bodies':data,'identities':{'initial_sha256':digest(case_dir/'initial.json'),'samples_sha256':digest(case_dir/'samples.jsonl'),'script_sha256':digest(__file__),'oracle_sha256':digest(Path(__file__).with_name('oracle.py'))}}
    destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(data,indent=2))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('case_dir',type=Path)
    p.add_argument('--acquire',type=Path)
    p.add_argument('--acquisition',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    initial=json.loads((a.case_dir/'initial.json').read_text(encoding='utf-8-sig'))
    acquisition=fetch_bodies(initial,a.acquire) if a.acquire else json.loads(a.acquisition.read_text())
    if a.output:compare(a.case_dir,acquisition,a.output)


if __name__=='__main__':main()
