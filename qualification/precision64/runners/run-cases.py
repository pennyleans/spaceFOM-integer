from pathlib import Path
import concurrent.futures,os,hashlib,json,platform,subprocess,sys,time
root=Path(__file__).resolve().parent
runtime=os.environ.get('DOTNET_EXE','dotnet')
dll=root/'probe/bin/Release/net10.0/Flight.Session.Tests.dll'
power=int(sys.argv[1]);label=sys.argv[2]
cases=sys.argv[3:] or ['earth-orbit','moon-orbit','inertial-burn','lunar-fixture']
output=root/'results'/label
output.mkdir(parents=True,exist_ok=True)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dll.parent.iterdir() if p.is_file()}
def run(name):
    start=time.monotonic()
    with (output/(name+'.log')).open('w') as log:
        p=subprocess.run([runtime,str(dll),'case',name,str(power),str(root/'source/data'),str(output/name)],stdout=log,stderr=subprocess.STDOUT,timeout=2400)
    row={'case':name,'power':power,'exit':p.returncode,'wall_seconds':time.monotonic()-start}
    print(json.dumps(row),flush=True)
    return row
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,cases))
path=output/('execution-'+str(power)+'-'+cases[0]+'.json')
assert not path.exists()
unchanged=manifest=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dll.parent.iterdir() if p.is_file()}
path.write_text(json.dumps({'architecture':platform.machine(),'executables':manifest,'unchanged':unchanged,'rows':rows},indent=2)+'\n')
assert unchanged and all(r['exit']==0 for r in rows)
