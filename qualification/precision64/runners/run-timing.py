from pathlib import Path
import hashlib,json,os,subprocess,sys,time,platform
root=Path(__file__).resolve().parent
runtime=os.environ.get('DOTNET_EXE','dotnet')
dll=root/'probe/bin/Release/net10.0/Flight.Session.Tests.dll'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():
    files=list(dll.parent.glob('*'))+[root/'source/data/sol-2207.json',root/'source/data/ships/reference-tug.ship.toml',root/'source/data/ships/reference-tug.flight.json',root/'probe/Benchmark.cs',root/'probe/SpinBenchmark.cs']
    return [{'path':p.relative_to(root).as_posix(),'sha256':digest(p)} for p in sorted(files) if p.is_file()]
mode,power,count,label=sys.argv[1:]
out=root/'timing'/label
receipt=out.parent/(label+'-execution.json')
assert not out.exists() and not receipt.exists()
out.parent.mkdir(parents=True,exist_ok=True)
before=inputs();started=time.time()
with (out.parent/(label+'.log')).open('w') as log:
    proc=subprocess.run([runtime,str(dll),mode,power,count,str(root/'source/data'),str(out)],stdout=log,stderr=subprocess.STDOUT,timeout=900)
after=inputs()
row={'mode':mode,'power':int(power),'count':int(count),'exit':proc.returncode,'architecture':platform.machine(),'started_unix':started,'wall_seconds':time.time()-started,'files_before':before,'files_unchanged':before==after}
receipt.write_text(json.dumps(row,indent=2)+'\n')
print(json.dumps({k:v for k,v in row.items() if k!='files_before'}),flush=True)
assert proc.returncode==0 and before==after
