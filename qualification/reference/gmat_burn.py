"""NASA GMAT chemical-thruster cross-reference for constant inertial thrust."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
from oracle import digest, norm, sub, read_case, rocket


def run(case_dir,gmat_dir,destination):
    initial,samples,times=read_case(case_dir)
    expected={'mass_kg':'18000','dry_mass_kg':'12000','thrust_n':'1000','exhaust_velocity_m_s':'4500'}
    if any(Decimal(initial['vessel'][k])!=Decimal(v) for k,v in expected.items()) or any(Decimal(x)!=0 for x in initial['vessel']['p']+initial['vessel']['v']) or initial['duration_seconds']!=120 or initial['burn']!={'start_seconds':0,'end_seconds':60,'force_direction':[1,0,0]}:
        raise ValueError('GMAT burn script is intentionally restricted to the declared inertial-burn fixture')
    if destination.exists():raise FileExistsError('use a fresh run directory')
    destination.mkdir(parents=True)
    vessel=initial['vessel']
    report=destination/'states.txt'
    script=destination/'matched.script'
    fuel=Decimal(vessel['mass_kg'])-Decimal(vessel['dry_mass_kg'])
    text=f'''% negligible gravity; inertial constant thrust with linearly depleted propellant.
% a fixed 10000 km x-offset avoids GMAT's zero-radius spacecraft state.
GMAT Earth.Mu = 1e-15;
Create ChemicalTank Fuel;
GMAT Fuel.Volume = 10;
GMAT Fuel.FuelMass = {fuel};
Create ChemicalThruster Engine;
GMAT Engine.CoordinateSystem = EarthMJ2000Eq;
GMAT Engine.ThrustDirection1 = 1;
GMAT Engine.ThrustDirection2 = 0;
GMAT Engine.ThrustDirection3 = 0;
GMAT Engine.Tank = {{Fuel}};
GMAT Engine.DecrementMass = true;
GMAT Engine.C1 = {vessel['thrust_n']};
GMAT Engine.K1 = {vessel['exhaust_velocity_m_s']};
GMAT Engine.GravitationalAccel = 1;
Create Spacecraft Probe;
GMAT Probe.DateFormat = TAIModJulian;
GMAT Probe.Epoch = '21545';
GMAT Probe.CoordinateSystem = EarthMJ2000Eq;
GMAT Probe.DisplayStateType = Cartesian;
GMAT Probe.X = 10000;
GMAT Probe.Y = 0;
GMAT Probe.Z = 0;
GMAT Probe.VX = 0;
GMAT Probe.VY = 0;
GMAT Probe.VZ = 0;
GMAT Probe.DryMass = {vessel['dry_mass_kg']};
GMAT Probe.Tanks = {{Fuel}};
GMAT Probe.Thrusters = {{Engine}};
Create FiniteBurn Burn;
GMAT Burn.Thrusters = {{Engine}};
Create ForceModel Forces;
GMAT Forces.CentralBody = Earth;
GMAT Forces.PrimaryBodies = {{}};
GMAT Forces.PointMasses = {{Earth}};
GMAT Forces.Drag = None;
GMAT Forces.SRP = Off;
GMAT Forces.RelativisticCorrection = Off;
GMAT Forces.ErrorControl = None;
Create Propagator Integrator;
GMAT Integrator.FM = Forces;
GMAT Integrator.Type = RungeKutta89;
GMAT Integrator.InitialStepSize = 1;
GMAT Integrator.MinStep = 0.000001;
GMAT Integrator.MaxStep = 1;
Create ReportFile States;
GMAT States.Filename = '{report.as_posix()}';
GMAT States.Precision = 17;
GMAT States.WriteHeaders = false;
GMAT States.FixedWidth = false;
GMAT States.Delimiter = ',';
GMAT States.Add = {{Probe.ElapsedSecs, Probe.EarthMJ2000Eq.X, Probe.EarthMJ2000Eq.Y, Probe.EarthMJ2000Eq.Z, Probe.EarthMJ2000Eq.VX, Probe.EarthMJ2000Eq.VY, Probe.EarthMJ2000Eq.VZ, Probe.TotalMass}};
BeginMissionSequence;
BeginFiniteBurn Burn(Probe);
Propagate Integrator(Probe) {{Probe.ElapsedSecs = 60}};
EndFiniteBurn Burn(Probe);
Propagate Integrator(Probe) {{Probe.ElapsedSecs = 60}};
'''
    script.write_text(text,encoding='utf-8')
    command=[str(gmat_dir/'bin/GmatConsole.exe'),'--run',str(script),'--logfile',str(destination/'GmatLog.txt')]
    completed=subprocess.run(command,cwd=gmat_dir/'bin',capture_output=True,text=True,timeout=60)
    (destination/'console.txt').write_text(completed.stdout+'\n'+completed.stderr,encoding='utf-8')
    if completed.returncode!=0 or not report.exists() or 'Mission run completed' not in completed.stdout:
        raise RuntimeError('GMAT burn failed; inspect console.txt')
    rows={}
    duplicate_count=0
    max_time_error=0.0
    for line in report.read_text().splitlines():
        raw=[Decimal(x.strip()) for x in line.split(',')]
        t=round(float(raw[0]))
        max_time_error=max(max_time_error,abs(float(raw[0])-t))
        if abs(float(raw[0])-t)>1e-6:raise ValueError('unexpected GMAT report time')
        if t in rows:
            if raw[1:]!=rows[t][1:]:raise ValueError('transition duplicate changed state')
            duplicate_count+=1
        rows[t]=raw
    if set(rows)!=set(range(121)):raise ValueError('GMAT burn did not cover all 121 samples')
    sp_error,sv_error,sm_error,ap_error,av_error,am_error=[],[],[],[],[],[]
    for sample,t in zip(samples,times):
        row=rows[int(t)]
        gp=[float(row[1]*1000-10000000),float(row[2]*1000),float(row[3]*1000)]
        gv=[float(x*1000) for x in row[4:7]]
        ap,av,am=rocket(initial,t)
        sp_error.append(norm(sub([float(x) for x in sample['vessel']['p']],gp)))
        sv_error.append(norm(sub([float(x) for x in sample['vessel']['v']],gv)))
        sm_error.append(float(abs(Decimal(sample['vessel']['mass_kg'])-row[7])))
        ap_error.append(norm(sub(ap,gp)));av_error.append(norm(sub(av,gv)))
        am_error.append(float(abs(am-row[7])))
    metrics={'simulation_vs_gmat_max_position_m':max(sp_error),'simulation_vs_gmat_max_velocity_m_s':max(sv_error),'simulation_vs_gmat_max_mass_kg':max(sm_error),'analytic_vs_gmat_max_position_m':max(ap_error),'analytic_vs_gmat_max_velocity_m_s':max(av_error),'analytic_vs_gmat_max_mass_kg':max(am_error),'max_reported_time_roundoff_s':max_time_error}
    result={'schema':'gmat-finite-burn-v1','case':initial['case'],'gmat_version':'R2026a','scope':'constant inertial thrust 1000 N, exhaust velocity 4500 m/s, 60 s burn and 60 s coast, negligible point-mass gravity','origin_note':'GMAT spacecraft starts at x=10000 km to avoid zero-radius validation. This constant offset is subtracted in decimal. Explicit central GM=1e-6 m^3/s^2 prevents GMAT from silently restoring its default Earth force. Outward motion bounds its 120-second gravity displacement below 7.21e-17 m.','epoch_note':'GMAT epoch 2000; autonomous force law compared by elapsed seconds. The simulation tiny distant source is bounded separately by the analytic receipt.','duration_seconds':120,'sample_count':121,'identical_transition_duplicates':duplicate_count,'metrics':metrics,'thresholds':{'position_m':0.01,'velocity_m_s':0.0001,'mass_kg':1e-9},'pass':max(sp_error)<0.01 and max(sv_error)<0.0001 and max(sm_error)<1e-9,'identities':{'initial_sha256':digest(case_dir/'initial.json'),'samples_sha256':digest(case_dir/'samples.jsonl'),'script_sha256':digest(script),'report_sha256':digest(report),'console_sha256':digest(gmat_dir/'bin/GmatConsole.exe'),'libGmatBase_sha256':digest(gmat_dir/'bin/libGmatBase.dll'),'comparator_sha256':digest(__file__)}}
    (destination/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(metrics,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case_dir',type=Path)
    parser.add_argument('--gmat-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.case_dir,args.gmat_dir,args.output)
