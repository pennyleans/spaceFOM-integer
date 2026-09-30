"""Matched point-mass NASA GMAT console comparison, without a GUI or core imports."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
from oracle import digest, kepler, norm, relative, sub, read_case


def run(case_dir,gmat_dir,destination):
    initial,samples,times=read_case(case_dir)
    if len(initial['bodies'])!=1 or float(initial['vessel']['thrust_n'])!=0:
        raise ValueError('this external comparator currently supports matched two-body coasts')
    if destination.exists():raise FileExistsError('use a fresh run directory')
    destination.mkdir(parents=True)
    body=initial['bodies'][0]
    central='Luna' if str(body['id']) in ('301','moon') or 'moon' in initial['case'] else 'Earth'
    mu=Decimal(body['gm_m3_s2'])/Decimal(1000000000)
    p=relative(initial['vessel']['p'],body['p'])
    v=relative(initial['vessel']['v'],body['v'])
    report=destination/'states.txt'
    script=destination/'matched.script'
    text=f'''% matched autonomous two-body model; elapsed time only, epoch-independent.
GMAT {central}.Mu = {mu};
Create CoordinateSystem Frame;
GMAT Frame.Origin = {central};
GMAT Frame.Axes = MJ2000Eq;
Create Spacecraft Probe;
GMAT Probe.DateFormat = TAIModJulian;
GMAT Probe.Epoch = '21545';
GMAT Probe.CoordinateSystem = Frame;
GMAT Probe.DisplayStateType = Cartesian;
'''
    for key,value in zip(('X','Y','Z','VX','VY','VZ'),p+v):
        text+=f'GMAT Probe.{key} = {value/1000:.17g};\n'
    text+=f'''Create ForceModel Forces;
GMAT Forces.CentralBody = {central};
GMAT Forces.PrimaryBodies = {{}};
GMAT Forces.PointMasses = {{{central}}};
GMAT Forces.Drag = None;
GMAT Forces.SRP = Off;
GMAT Forces.RelativisticCorrection = Off;
GMAT Forces.ErrorControl = None;
Create Propagator Integrator;
GMAT Integrator.FM = Forces;
GMAT Integrator.Type = RungeKutta89;
GMAT Integrator.InitialStepSize = 1;
GMAT Integrator.Accuracy = 1e-13;
GMAT Integrator.MinStep = 0.000001;
GMAT Integrator.MaxStep = 1;
GMAT Integrator.MaxStepAttempts = 100;
Create ReportFile States;
GMAT States.Filename = '{report.as_posix()}';
GMAT States.Precision = 17;
GMAT States.WriteHeaders = false;
GMAT States.FixedWidth = false;
GMAT States.Delimiter = ',';
GMAT States.Add = {{Probe.ElapsedSecs, Probe.Frame.X, Probe.Frame.Y, Probe.Frame.Z, Probe.Frame.VX, Probe.Frame.VY, Probe.Frame.VZ}};
BeginMissionSequence;
Propagate Integrator(Probe) {{Probe.ElapsedSecs = {int(times[-1])}}};
'''
    script.write_text(text,encoding='utf-8')
    command=[str(gmat_dir/'bin/GmatConsole.exe'),'--run',str(script),'--logfile',str(destination/'GmatLog.txt')]
    result=subprocess.run(command,cwd=gmat_dir/'bin',capture_output=True,text=True,timeout=180)
    (destination/'console.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode!=0 or not report.exists() or 'Mission run completed' not in result.stdout:
        raise RuntimeError(f'GMAT run failed, inspect {destination}/console.txt')
    rows=[[float(x.strip()) for x in line.split(',')] for line in report.read_text().splitlines() if line.strip()]
    if len(rows)!=len(samples):raise ValueError(f'GMAT sample count mismatch {len(rows)} vs {len(samples)}')
    sim_p,sim_v,analytic_p,analytic_v,time_errors=[],[],[],[],[]
    for row,sample,t in zip(rows,samples,times):
        # GMAT reports elapsed time by subtracting binary64 Modified Julian epochs.
        # One microsecond bounds that representation at the selected 2000 epoch.
        if abs(row[0]-t)>1e-6:raise ValueError('GMAT output time does not match sample time')
        time_errors.append(abs(row[0]-t))
        gp,gv=[x*1000 for x in row[1:4]],[x*1000 for x in row[4:7]]
        sp=relative(sample['vessel']['p'],sample['bodies'][0]['p'])
        sv=relative(sample['vessel']['v'],sample['bodies'][0]['v'])
        ap,av=kepler(p,v,float(body['gm_m3_s2']),t)
        sim_p.append(norm(sub(sp,gp)));sim_v.append(norm(sub(sv,gv)))
        analytic_p.append(norm(sub(ap,gp)));analytic_v.append(norm(sub(av,gv)))
    metrics={'simulation_vs_gmat_max_position_m':max(sim_p),'simulation_vs_gmat_max_velocity_m_s':max(sim_v),'analytic_vs_gmat_max_position_m':max(analytic_p),'analytic_vs_gmat_max_velocity_m_s':max(analytic_v),'max_reported_time_roundoff_s':max(time_errors)}
    record={'schema':'gmat-matched-reference-v1','case':initial['case'],'gmat_version':'R2026a','scope':'two-body coast, exact exported relative state and GM, no extra forces','epoch_note':'GMAT uses 2000-01-01 epoch within bundled ephemeris coverage. The autonomous two-body equation is epoch-independent; only elapsed time and relative Cartesian vectors are compared. This is not a 2207 solar-system ephemeris comparison.','sample_count':len(rows),'duration_seconds':times[-1],'metrics':metrics,'position_threshold_m':0.1,'velocity_threshold_m_s':0.0001,'pass':max(sim_p)<0.1 and max(sim_v)<0.0001,'identities':{'initial_sha256':digest(case_dir/'initial.json'),'samples_sha256':digest(case_dir/'samples.jsonl'),'gmat_script_sha256':digest(script),'gmat_report_sha256':digest(report),'console_executable_sha256':digest(gmat_dir/'bin/GmatConsole.exe'),'libGmatBase_sha256':digest(gmat_dir/'bin/libGmatBase.dll'),'libGmatUtil_sha256':digest(gmat_dir/'bin/libGmatUtil.dll'),'startup_sha256':digest(gmat_dir/'bin/gmat_startup_file.txt'),'comparator_sha256':digest(__file__)}}
    (destination/'receipt.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(metrics,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case_dir',type=Path)
    parser.add_argument('--gmat-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.case_dir,args.gmat_dir,args.output)
